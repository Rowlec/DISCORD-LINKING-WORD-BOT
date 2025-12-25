"""
Word Handler Cog for Word Chain Bot.
Handles message events for word submissions during active games.
"""
import logging
import re
from datetime import datetime

import discord
from discord.ext import commands

from config import SETTINGS, LOGGER_NAME_GAME, GameStatus
from database import async_session_factory
from models.game import WordChainGame
from services.game_manager import game_manager
from services.ai_validator import word_validator
from views.game_ui import GameEmbed
from utils.timer import timer_manager

logger = logging.getLogger(LOGGER_NAME_GAME)


class WordHandler(commands.Cog):
    """Cog for handling word submissions in active games."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle incoming messages for word submissions."""
        # Ignore bots
        if message.author.bot:
            return
        
        # Check if there's an active game in this channel
        game = game_manager.get_game(message.channel.id)
        if not game or game.status != GameStatus.ACTIVE:
            return
        
        # Check if it's this player's turn
        if message.author.id != game.current_player_id:
            return
        
        # Check if the message looks like a word (single word, letters only)
        word = message.content.strip().lower()
        if not word or not re.match(r'^[a-zA-Zàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]+$', word, re.IGNORECASE):
            # Not a valid word format, ignore
            return
        
        # Process the word
        await self._process_word(message, game, word)
    
    async def _process_word(
        self,
        message: discord.Message,
        game: WordChainGame,
        word: str
    ):
        """Process a word submission."""
        player = game.players.get(message.author.id)
        if not player:
            return
        
        channel = message.channel
        
        # Stop the timer while processing
        await timer_manager.stop_timer(channel.id)
        
        # Check 1: Word already used in this session
        if game.is_word_used(word):
            embed = GameEmbed.word_already_used(word, player.display_name)
            await channel.send(embed=embed)
            await game_manager.record_invalid_attempt(channel.id, message.author.id)
            # Restart timer for same player
            await self._start_turn_timer(game, channel)
            return
        
        # Check 2: Word starts with correct letters
        if not game.matches_required_start(word):
            embed = GameEmbed.wrong_start(
                word,
                player.display_name,
                game.required_start or "?"
            )
            await channel.send(embed=embed)
            await game_manager.record_invalid_attempt(channel.id, message.author.id)
            # Restart timer for same player
            await self._start_turn_timer(game, channel)
            return
        
        # Check 3: Validate word with AI
        async with async_session_factory() as session:
            validation = await word_validator.validate_word(word, session)
        
        # Check if plural
        if validation.is_plural:
            embed = GameEmbed.plural_word(word, player.display_name)
            await channel.send(embed=embed)
            await game_manager.record_invalid_attempt(channel.id, message.author.id)
            # Restart timer for same player
            await self._start_turn_timer(game, channel)
            return
        
        # Check if invalid word
        if not validation.is_valid:
            reason = validation.reason or "Từ không có trong từ điển"
            embed = GameEmbed.word_invalid(word, player.display_name, reason)
            await channel.send(embed=embed)
            await game_manager.record_invalid_attempt(channel.id, message.author.id)
            # Restart timer for same player
            await self._start_turn_timer(game, channel)
            return
        
        # Word is valid! Record it
        await game_manager.record_word(channel.id, word, message.author.id)
        
        # Update longest word stat if applicable
        await self._update_longest_word(message.author.id, message.guild.id, word)
        
        # Add reaction to the message
        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass
        
        # Calculate next start letters
        next_start = word[-game.letters_to_match:].upper()
        
        # Send accepted word embed
        embed = GameEmbed.word_accepted(
            word,
            player.display_name,
            next_start,
            len(game.current_chain_words)
        )
        await channel.send(embed=embed)
        
        # Move to next turn
        next_player_id = game.next_turn()
        
        if next_player_id:
            # Start timer for next player
            await self._start_turn_timer(game, channel)
        else:
            # Game should end (only one player left)
            await self._end_game(game, channel)
    
    async def _update_longest_word(self, user_id: int, guild_id: int, word: str):
        """Update player's longest word stat if this word is longer."""
        from sqlalchemy import select, update
        from models.db_models import PlayerStats
        
        async with async_session_factory() as session:
            stmt = select(PlayerStats).where(
                PlayerStats.user_id == user_id,
                PlayerStats.guild_id == guild_id
            )
            result = await session.execute(stmt)
            stats = result.scalar_one_or_none()
            
            if stats:
                if not stats.longest_word or len(word) > len(stats.longest_word):
                    stats.longest_word = word
                    await session.commit()
    
    async def _start_turn_timer(self, game: WordChainGame, channel: discord.TextChannel):
        """Start the turn timer for the current player."""
        async def on_timeout(user_id: int):
            await self._handle_timeout(game, channel, user_id)
        
        await timer_manager.create_timer(game, channel, on_timeout)
    
    async def _handle_timeout(
        self,
        game: WordChainGame,
        channel: discord.TextChannel,
        user_id: int
    ):
        """Handle player timeout."""
        player = await game_manager.eliminate_player(channel.id, user_id, reason="timeout")
        if not player:
            return
        
        # Send elimination embed
        embed = GameEmbed.player_eliminated(
            player.display_name,
            "Hết thời gian ⏰",
            game.active_player_count
        )
        await channel.send(embed=embed)
        
        # Check if game should end
        if game.is_game_over:
            await self._end_game(game, channel)
        else:
            # Move to next player and start timer
            game.next_turn()
            await self._start_turn_timer(game, channel)
    
    async def _handle_forfeit(
        self,
        game: WordChainGame,
        channel: discord.TextChannel,
        user_id: int
    ):
        """Handle player forfeit."""
        # Stop timer first
        await timer_manager.stop_timer(channel.id)
        
        player = await game_manager.forfeit_player(channel.id, user_id)
        if not player:
            return
        
        # Send forfeit embed
        embed = GameEmbed.player_forfeit(
            player.display_name,
            game.active_player_count
        )
        await channel.send(embed=embed)
        
        # Check if game should end
        if game.is_game_over:
            await self._end_game(game, channel)
        else:
            # If it was this player's turn, move to next
            if game.current_player_id == user_id or user_id in [p.user_id for p in game.active_players]:
                game.next_turn()
            await self._start_turn_timer(game, channel)
    
    async def _end_game(self, game: WordChainGame, channel: discord.TextChannel):
        """End the game and announce winner."""
        # Stop timer
        await timer_manager.stop_timer(channel.id)
        
        winner = game.winner
        winner_id = winner.user_id if winner else None
        
        # Calculate duration
        duration = 0
        if game.started_at:
            duration = int((datetime.utcnow() - game.started_at).total_seconds() / 60)
        
        # Total words across all chains
        total_words = len(game.used_words_in_session)
        
        # End game in manager
        await game_manager.end_game(channel.id, winner_id)
        
        # Send winner embed
        if winner:
            embed = GameEmbed.game_winner(
                winner.display_name,
                winner.user_id,
                total_words,
                game.chain_resets,
                duration
            )
            await channel.send(embed=embed)
        else:
            # No winner (all players left?)
            embed = GameEmbed.game_cancelled("Không còn người chơi")
            await channel.send(embed=embed)
    
    async def _cancel_game(self, game: WordChainGame, channel: discord.TextChannel):
        """Cancel the game."""
        # Stop timer
        await timer_manager.stop_timer(channel.id)
        
        # Cancel in manager
        await game_manager.cancel_game(channel.id)
    
    # Event listeners for game lifecycle
    
    @commands.Cog.listener()
    async def on_game_started(self, game: WordChainGame, channel: discord.TextChannel):
        """Handle game start event."""
        logger.info(f"Game started event: session={game.session_id}")
        await self._start_turn_timer(game, channel)
    
    @commands.Cog.listener()
    async def on_player_forfeit(
        self,
        game: WordChainGame,
        channel: discord.TextChannel,
        user_id: int
    ):
        """Handle player forfeit event."""
        logger.info(f"Player forfeit event: user={user_id}, session={game.session_id}")
        await self._handle_forfeit(game, channel, user_id)
    
    @commands.Cog.listener()
    async def on_game_cancel(self, game: WordChainGame, channel: discord.TextChannel):
        """Handle game cancel event."""
        logger.info(f"Game cancel event: session={game.session_id}")
        await self._cancel_game(game, channel)


async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    await bot.add_cog(WordHandler(bot))
