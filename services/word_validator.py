"""
Word Validator Service using Free Dictionary API.
Free dictionary API - no API key required.
https://dictionaryapi.dev/
"""
import logging
import aiohttp
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import SETTINGS, LOGGER_NAME_GAME
from models.db_models import WordCache

logger = logging.getLogger(LOGGER_NAME_GAME)

# Free Dictionary API - completely free, no API key, no rate limits
DICTIONARY_API_URL = "https://api.dictionaryapi.dev/api/v2/entries/en"

# Common plural suffixes for detection
PLURAL_SUFFIXES = ['ies', 'es', 's']
IRREGULAR_PLURALS = {
    'children', 'men', 'women', 'feet', 'teeth', 'geese', 'mice', 'lice',
    'people', 'oxen', 'sheep', 'deer', 'fish', 'species', 'aircraft',
    'series', 'means', 'pants', 'scissors', 'glasses', 'trousers'
}


@dataclass
class WordValidationResult:
    """Result of word validation."""
    word: str
    is_valid: bool
    is_plural: bool = False
    word_type: Optional[str] = None
    reason: Optional[str] = None
    from_cache: bool = False
    
    @property
    def is_acceptable(self) -> bool:
        """Word is acceptable if valid and not plural."""
        return self.is_valid and not self.is_plural


class WordValidator:
    """
    Validates words using Wiktionary API.
    Includes caching to reduce API calls.
    """
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        logger.info("Word validator initialized using Free Dictionary API")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session
    
    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def validate_word(
        self,
        word: str,
        session: AsyncSession,
        language: str = "en"
    ) -> WordValidationResult:
        """
        Validate a word using Wiktionary API with caching.
        
        Args:
            word: The word to validate
            session: Database session for cache lookup/storage
            language: Language code (default: "en")
            
        Returns:
            WordValidationResult with validation details
        """
        word_lower = word.lower().strip()
        
        # Check cache first
        cached_result = await self._check_cache(word_lower, language, session)
        if cached_result:
            logger.debug(f"Cache hit for word: {word_lower}")
            return cached_result
        
        # Validate with Free Dictionary API
        logger.info(f"Validating word with Dictionary API: {word_lower}")
        result = await self._validate_with_dictionary(word_lower)
        
        # Store in cache
        await self._store_in_cache(word_lower, language, result, session)
        
        return result
    
    async def _check_cache(
        self,
        word: str,
        language: str,
        session: AsyncSession
    ) -> Optional[WordValidationResult]:
        """Check if word exists in cache and is not expired."""
        cache_expiry = datetime.utcnow() - timedelta(days=SETTINGS.word_cache_expiry_days)
        
        stmt = select(WordCache).where(
            WordCache.word == word,
            WordCache.language == language,
            WordCache.validated_at >= cache_expiry
        )
        
        result = await session.execute(stmt)
        cached = result.scalar_one_or_none()
        
        if cached:
            return WordValidationResult(
                word=word,
                is_valid=cached.is_valid,
                is_plural=cached.is_plural,
                word_type=cached.word_type,
                reason=cached.ai_reason,
                from_cache=True
            )
        
        return None
    
    async def _store_in_cache(
        self,
        word: str,
        language: str,
        result: WordValidationResult,
        session: AsyncSession
    ) -> None:
        """Store validation result in cache."""
        # Check if already exists (upsert logic)
        stmt = select(WordCache).where(
            WordCache.word == word,
            WordCache.language == language
        )
        existing = await session.execute(stmt)
        cached = existing.scalar_one_or_none()
        
        if cached:
            # Update existing
            cached.is_valid = result.is_valid
            cached.is_plural = result.is_plural
            cached.word_type = result.word_type
            cached.ai_reason = result.reason
            cached.validated_at = datetime.utcnow()
        else:
            # Create new
            cache_entry = WordCache(
                word=word,
                language=language,
                is_valid=result.is_valid,
                is_plural=result.is_plural,
                word_type=result.word_type,
                ai_reason=result.reason
            )
            session.add(cache_entry)
        
        try:
            await session.commit()
        except Exception as e:
            logger.warning(f"Failed to cache word '{word}': {e}")
            await session.rollback()
    
    async def _validate_with_dictionary(self, word: str) -> WordValidationResult:
        """Call Free Dictionary API to validate the word."""
        try:
            http_session = await self._get_session()
            url = f"{DICTIONARY_API_URL}/{word}"
            
            async with http_session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Parse the response to get word type and check for plural
                    word_type, is_plural = self._parse_dictionary_response(data, word)
                    
                    return WordValidationResult(
                        word=word,
                        is_valid=True,
                        is_plural=is_plural,
                        word_type=word_type,
                        reason=None
                    )
                elif response.status == 404:
                    # Word not found in dictionary
                    return WordValidationResult(
                        word=word,
                        is_valid=False,
                        reason=f"The word '{word}' is not found in standard English dictionaries."
                    )
                else:
                    # API error - fail safe, reject word
                    logger.warning(f"Dictionary API returned status {response.status} for word '{word}'")
                    return WordValidationResult(
                        word=word,
                        is_valid=False,
                        reason=f"Could not verify word (API error {response.status})"
                    )
                    
        except aiohttp.ClientError as e:
            logger.error(f"Dictionary API connection error for '{word}': {e}")
            return WordValidationResult(
                word=word,
                is_valid=False,
                reason="Could not connect to dictionary service. Please try again."
            )
        except Exception as e:
            logger.error(f"Dictionary validation error for '{word}': {e}")
            return WordValidationResult(
                word=word,
                is_valid=False,
                reason=f"Validation error: {str(e)}"
            )
    
    def _parse_dictionary_response(self, data: list, word: str) -> tuple[Optional[str], bool]:
        """
        Parse Free Dictionary API response to extract word type and detect plural.
        
        Returns:
            Tuple of (word_type, is_plural)
        """
        word_type = None
        is_plural = False
        
        try:
            # Free Dictionary API returns a list of entries
            if not data or not isinstance(data, list):
                return None, False
            
            first_entry = data[0]
            meanings = first_entry.get("meanings", [])
            
            for meaning in meanings:
                part_of_speech = meaning.get("partOfSpeech", "")
                
                # Set word type from first entry
                if not word_type and part_of_speech:
                    word_type = part_of_speech.lower()
                
                # Check definitions for plural indicators
                definitions = meaning.get("definitions", [])
                for defn in definitions:
                    definition_text = defn.get("definition", "").lower()
                    
                    # Check if it's marked as plural form
                    if "plural of" in definition_text or "plural form" in definition_text:
                        is_plural = True
                        break
                
                if is_plural:
                    break
            
            # Additional heuristic: check common plural patterns if not detected
            if not is_plural and word_type == "noun":
                is_plural = self._is_likely_plural(word)
                
        except Exception as e:
            logger.debug(f"Error parsing Dictionary API response: {e}")
        
        return word_type, is_plural
    
    def _is_likely_plural(self, word: str) -> bool:
        """
        Heuristic check if word is likely a plural form.
        Only used as fallback when Wiktionary doesn't explicitly mark it.
        """
        word_lower = word.lower()
        
        # Check irregular plurals
        if word_lower in IRREGULAR_PLURALS:
            return True
        
        # Words ending in common plural suffixes
        # But be careful - not all words ending in 's' are plural!
        # We only use this as a hint, not definitive
        
        # Skip common non-plural words ending in 's'
        non_plural_s_words = {
            'bus', 'gas', 'yes', 'this', 'his', 'is', 'was', 'has',
            'plus', 'thus', 'us', 'campus', 'virus', 'bonus', 'focus',
            'radius', 'genius', 'status', 'census', 'nexus', 'thesis',
            'analysis', 'basis', 'crisis', 'oasis', 'emphasis', 'synopsis'
        }
        
        if word_lower in non_plural_s_words:
            return False
        
        return False  # Be conservative - don't assume plural
    
    async def batch_validate(
        self,
        words: List[str],
        session: AsyncSession,
        language: str = "en"
    ) -> List[WordValidationResult]:
        """Validate multiple words (useful for pre-caching)."""
        results = []
        for word in words:
            result = await self.validate_word(word, session, language)
            results.append(result)
        return results


# Global word validator instance
word_validator = WordValidator()
