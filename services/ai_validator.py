"""
AI Word Validator Service for Word Chain Bot.
Uses OpenAI or Anthropic API to validate words.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import SETTINGS, LOGGER_NAME_AI, DEFAULT_LANGUAGE
from models.db_models import WordCache

logger = logging.getLogger(LOGGER_NAME_AI)


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


class AIWordValidator:
    """
    Validates words using AI (OpenAI or Anthropic).
    Includes caching to reduce API calls.
    """
    
    def __init__(self):
        self.provider = SETTINGS.ai_provider.lower()
        self.model = SETTINGS.ai_model
        self._client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the AI client based on provider."""
        if self.provider == "openai":
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=SETTINGS.openai_api_key)
                logger.info(f"OpenAI client initialized with model: {self.model}")
            except ImportError:
                logger.error("OpenAI package not installed. Run: pip install openai")
                raise
        elif self.provider == "anthropic":
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=SETTINGS.anthropic_api_key)
                logger.info(f"Anthropic client initialized with model: {self.model}")
            except ImportError:
                logger.error("Anthropic package not installed. Run: pip install anthropic")
                raise
        else:
            raise ValueError(f"Unknown AI provider: {self.provider}")
    
    async def validate_word(
        self,
        word: str,
        session: AsyncSession,
        language: str = DEFAULT_LANGUAGE
    ) -> WordValidationResult:
        """
        Validate a word using AI with caching.
        
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
        
        # Validate with AI
        logger.info(f"Validating word with AI: {word_lower}")
        result = await self._validate_with_ai(word_lower, language)
        
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
    
    async def _validate_with_ai(self, word: str, language: str) -> WordValidationResult:
        """Call AI API to validate the word."""
        
        language_name = {
            "en": "English",
            "vi": "Vietnamese",
            "es": "Spanish",
            "fr": "French",
            "de": "German"
        }.get(language, "English")
        
        prompt = f"""You are a word validation expert for a word chain game. Analyze the following word and provide validation information.

Word: "{word}"
Language: {language_name}

Please determine:
1. Is this a valid {language_name} word? (exists in standard dictionaries)
2. Is this word a plural form? (e.g., "cats" is plural of "cat", "children" is plural of "child")
3. What type of word is it? (noun, verb, adjective, adverb, etc.)

IMPORTANT RULES:
- Proper nouns are NOT valid (names of people, places, brands)
- Abbreviations are NOT valid
- Slang words are NOT valid
- Plural forms should be identified as plural (is_plural: true)
- Only standard dictionary words are valid

Respond in JSON format exactly like this:
{{
    "is_valid": true/false,
    "is_plural": true/false,
    "word_type": "noun/verb/adjective/etc or null",
    "reason": "Brief explanation"
}}"""

        try:
            if self.provider == "openai":
                response = await self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a word validation assistant. Always respond with valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=200
                )
                response_text = response.choices[0].message.content
                
            elif self.provider == "anthropic":
                response = await self._client.messages.create(
                    model=self.model,
                    max_tokens=200,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                response_text = response.content[0].text
            
            # Parse JSON response
            return self._parse_ai_response(word, response_text)
            
        except Exception as e:
            logger.error(f"AI validation error for '{word}': {e}")
            # Return as invalid on error (fail safe)
            return WordValidationResult(
                word=word,
                is_valid=False,
                reason=f"Validation error: {str(e)}"
            )
    
    def _parse_ai_response(self, word: str, response_text: str) -> WordValidationResult:
        """Parse AI response into WordValidationResult."""
        import json
        
        try:
            # Try to extract JSON from response
            # Sometimes AI wraps JSON in markdown code blocks
            text = response_text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            data = json.loads(text)
            
            return WordValidationResult(
                word=word,
                is_valid=data.get("is_valid", False),
                is_plural=data.get("is_plural", False),
                word_type=data.get("word_type"),
                reason=data.get("reason")
            )
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse AI response: {response_text}")
            # Attempt to extract boolean from text as fallback
            text_lower = response_text.lower()
            is_valid = "is_valid\": true" in text_lower or "\"is_valid\":true" in text_lower
            
            return WordValidationResult(
                word=word,
                is_valid=is_valid,
                reason=f"Parse error, inferred from response: {response_text[:100]}"
            )


# Global validator instance
word_validator = AIWordValidator()
