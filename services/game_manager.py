"""
Game Manager Service for Word Chain Bot.
Handles game lifecycle, state management, and database persistence.
"""
import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, List

import discord
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import SETTINGS, LOGGER_NAME_GAME, GameStatus, GameMode
from database import async_session_factory
from models.db_models import GameSession, GameParticipant, SessionWord, PlayerStats
from models.game import WordChainGame, PlayerInfo

logger = logging.getLogger(LOGGER_NAME_GAME)


class GameManager:
    """
    Manages all active games and their state.
    Provides methods for game lifecycle operations.
    """
    
    def __init__(self):
        # Active games in memory: channel_id -> WordChainGame
        self._active_games: Dict[int, WordChainGame] = {}
        # Timer tasks: channel_id -> asyncio.Task
        self._timer_tasks: Dict[int, asyncio.Task] = {}
    
    def get_game(self, channel_id: int) -> Optional[WordChainGame]:
        """Get an active game by channel ID."""
        return self._active_games.get(channel_id)
    
    def has_active_game(self, channel_id: int) -> bool:
        """Check if a channel has an active game."""
        return channel_id in self._active_games
    
    def get_user_active_game(self, user_id: int, guild_id: int) -> Optional[WordChainGame]:
        """Find a game that a user is currently in within a guild."""
        for game in self._active_games.values():
            if game.guild_id == guild_id and user_id in game.players:
                return game
        return None
    
    async def create_game(
        self,
        guild_id: int,
        channel_id: int,
        creator: discord.User | discord.Member,
        game_mode: str = GameMode.NORMAL,
        timer_seconds: int = 30
    ) -> WordChainGame:
        """
        Create a new game session.
        
        Args:
            guild_id: Discord guild ID
            channel_id: Discord channel ID
            creator: User who created the game
            game_mode: "normal" or "hard"
            timer_seconds: Turn timer in seconds
            
        Returns:
            WordChainGame instance
        """
        async with async_session_factory() as session:
            # Create database record
            db_session = GameSession(
                guild_id=guild_id,
                channel_id=channel_id,
                creator_id=creator.id,
                game_mode=game_mode,
                timer_seconds=timer_seconds,
                status=GameStatus.WAITING
            )
            session.add(db_session)
            await session.commit()
            await session.refresh(db_session)
            
            # Create in-memory game state
            game = WordChainGame(
                session_id=db_session.session_id,
                guild_id=guild_id,
                channel_id=channel_id,
                creator_id=creator.id,
                game_mode=game_mode,
                timer_seconds=timer_seconds,
                status=GameStatus.WAITING
            )
            
            # Add creator as first participant
            game.add_player(creator)
            
            # Add to database
            participant = GameParticipant(
                session_id=db_session.session_id,
                user_id=creator.id,
                turn_order=0
            )
            session.add(participant)
            await session.commit()
            
            # Store in memory
            self._active_games[channel_id] = game
            
            logger.info(
                f"Game created: session_id={game.session_id}, "
                f"channel={channel_id}, creator={creator.id}, mode={game_mode}"
            )
            
            return game
    
    async def join_game(
        self,
        channel_id: int,
        user: discord.User | discord.Member
    ) -> Optional[PlayerInfo]:
        """
        Add a player to an existing game.
        
        Returns:
            PlayerInfo if successful, None if game not found or full
        """
        game = self.get_game(channel_id)
        if not game:
            return None
        
        if game.status != GameStatus.WAITING:
            return None
        
        if user.id in game.players:
            return None  # Already in game
        
        if len(game.players) >= SETTINGS.max_players:
            return None  # Game full
        
        # Add to in-memory state
        player = game.add_player(user)
        
        # Add to database
        async with async_session_factory() as session:
            participant = GameParticipant(
                session_id=game.session_id,
                user_id=user.id,
                turn_order=player.turn_order
            )
            session.add(participant)
            await session.commit()
        
        logger.info(f"Player joined: user={user.id}, session={game.session_id}")
        return player
    
    async def leave_game(
        self,
        channel_id: int,
        user_id: int
    ) -> bool:
        """
        Remove a player from a game (only in waiting state).
        
        Returns:
            True if successful, False otherwise
        """
        game = self.get_game(channel_id)
        if not game or game.status != GameStatus.WAITING:
            return False
        
        if user_id not in game.players:
            return False
        
        # Remove from in-memory state
        game.remove_player(user_id)
        
        # Remove from database
        async with async_session_factory() as session:
            await session.execute(
                GameParticipant.__table__.delete().where(
                    GameParticipant.session_id == game.session_id,
                    GameParticipant.user_id == user_id
                )
            )
            await session.commit()
        
        logger.info(f"Player left: user={user_id}, session={game.session_id}")
        return True
    
    async def start_game(self, channel_id: int) -> bool:
        """
        Start a game that's in waiting state.
        
        Returns:
            True if successful, False otherwise
        """
        game = self.get_game(channel_id)
        if not game or game.status != GameStatus.WAITING:
            return False
        
        if len(game.players) < SETTINGS.min_players:
            return False
        
        # Update in-memory state
        game.start_game()
        
        # Update database
        async with async_session_factory() as session:
            await session.execute(
                update(GameSession)
                .where(GameSession.session_id == game.session_id)
                .values(status=GameStatus.ACTIVE, started_at=datetime.utcnow())
            )
            await session.commit()
        
        logger.info(f"Game started: session={game.session_id}, players={len(game.players)}")
        return True
    
    async def record_word(
        self,
        channel_id: int,
        word: str,
        user_id: int
    ) -> bool:
        """
        Record a word played in the game.
        
        Returns:
            True if successful, False otherwise
        """
        game = self.get_game(channel_id)
        if not game or game.status != GameStatus.ACTIVE:
            return False
        
        # Add to in-memory state
        game.add_word(word, user_id)
        
        # Add to database
        async with async_session_factory() as session:
            session_word = SessionWord(
                session_id=game.session_id,
                chain_number=game.current_chain_number,
                word_order=len(game.current_chain_words),
                word=word.lower(),
                user_id=user_id
            )
            session.add(session_word)
            
            # Update participant word count
            await session.execute(
                update(GameParticipant)
                .where(
                    GameParticipant.session_id == game.session_id,
                    GameParticipant.user_id == user_id
                )
                .values(words_played=GameParticipant.words_played + 1)
            )
            
            await session.commit()
        
        logger.debug(f"Word recorded: '{word}' by user={user_id}, session={game.session_id}")
        return True
    
    async def eliminate_player(
        self,
        channel_id: int,
        user_id: int,
        reason: str = "timeout"
    ) -> Optional[PlayerInfo]:
        """
        Eliminate a player from the game.
        
        Returns:
            PlayerInfo of eliminated player, None if not found
        """
        game = self.get_game(channel_id)
        if not game or game.status != GameStatus.ACTIVE:
            return None
        
        player = game.eliminate_player(user_id)
        if not player:
            return None
        
        # Reset chain after elimination
        game.reset_chain()
        
        # Update database
        async with async_session_factory() as session:
            await session.execute(
                update(GameParticipant)
                .where(
                    GameParticipant.session_id == game.session_id,
                    GameParticipant.user_id == user_id
                )
                .values(
                    is_eliminated=True,
                    elimination_order=player.elimination_order,
                    eliminated_at=datetime.utcnow()
                )
            )
            
            # Update chain resets count
            await session.execute(
                update(GameSession)
                .where(GameSession.session_id == game.session_id)
                .values(chain_resets=game.chain_resets)
            )
            
            await session.commit()
        
        logger.info(
            f"Player eliminated: user={user_id}, session={game.session_id}, reason={reason}"
        )
        return player
    
    async def end_game(
        self,
        channel_id: int,
        winner_id: Optional[int] = None
    ) -> Optional[WordChainGame]:
        """
        End a game and clean up resources.
        
        Returns:
            The ended game, None if not found
        """
        game = self._active_games.pop(channel_id, None)
        if not game:
            return None
        
        # Cancel timer task if exists
        timer_task = self._timer_tasks.pop(channel_id, None)
        if timer_task:
            timer_task.cancel()
        
        # Determine winner
        if winner_id is None and game.winner:
            winner_id = game.winner.user_id
        
        game.status = GameStatus.FINISHED
        
        # Update database
        async with async_session_factory() as session:
            await session.execute(
                update(GameSession)
                .where(GameSession.session_id == game.session_id)
                .values(
                    status=GameStatus.FINISHED,
                    finished_at=datetime.utcnow(),
                    winner_id=winner_id
                )
            )
            await session.commit()
            
            # Update player stats
            await self._update_player_stats(session, game, winner_id)
        
        logger.info(f"Game ended: session={game.session_id}, winner={winner_id}")
        return game
    
    async def cancel_game(self, channel_id: int) -> Optional[WordChainGame]:
        """
        Cancel a game that hasn't started yet.
        
        Returns:
            The cancelled game, None if not found
        """
        game = self._active_games.pop(channel_id, None)
        if not game:
            return None
        
        # Cancel timer task if exists
        timer_task = self._timer_tasks.pop(channel_id, None)
        if timer_task:
            timer_task.cancel()
        
        # Delete from database (cascade will delete participants)
        async with async_session_factory() as session:
            db_game = await session.get(GameSession, game.session_id)
            if db_game:
                await session.delete(db_game)
                await session.commit()
        
        logger.info(f"Game cancelled: session={game.session_id}")
        return game
    
    async def forfeit_player(
        self,
        channel_id: int,
        user_id: int
    ) -> Optional[PlayerInfo]:
        """
        Handle player forfeit (voluntary elimination).
        
        Returns:
            PlayerInfo of forfeited player, None if not found
        """
        return await self.eliminate_player(channel_id, user_id, reason="forfeit")
    
    async def record_invalid_attempt(
        self,
        channel_id: int,
        user_id: int
    ) -> bool:
        """Record an invalid word attempt for a player."""
        game = self.get_game(channel_id)
        if not game or user_id not in game.players:
            return False
        
        game.players[user_id].invalid_attempts += 1
        
        # Update database
        async with async_session_factory() as session:
            await session.execute(
                update(GameParticipant)
                .where(
                    GameParticipant.session_id == game.session_id,
                    GameParticipant.user_id == user_id
                )
                .values(invalid_attempts=GameParticipant.invalid_attempts + 1)
            )
            await session.commit()
        
        return True
    
    async def _update_player_stats(
        self,
        session: AsyncSession,
        game: WordChainGame,
        winner_id: Optional[int]
    ) -> None:
        """Update player statistics after a game ends."""
        for player in game.players.values():
            # Get or create stats record
            stmt = select(PlayerStats).where(
                PlayerStats.user_id == player.user_id,
                PlayerStats.guild_id == game.guild_id
            )
            result = await session.execute(stmt)
            stats = result.scalar_one_or_none()
            
            if not stats:
                stats = PlayerStats(
                    user_id=player.user_id,
                    guild_id=game.guild_id
                )
                session.add(stats)
            
            # Update stats
            stats.games_played += 1
            stats.total_words += player.words_played
            stats.total_invalid_words += player.invalid_attempts
            
            if player.is_eliminated:
                stats.total_timeouts += 1
                stats.current_win_streak = 0
            
            if player.user_id == winner_id:
                stats.games_won += 1
                stats.current_win_streak += 1
                if stats.current_win_streak > stats.best_win_streak:
                    stats.best_win_streak = stats.current_win_streak
        
        await session.commit()
    
    def set_timer_task(self, channel_id: int, task: asyncio.Task) -> None:
        """Store a timer task for a game."""
        # Cancel existing task if any
        existing = self._timer_tasks.get(channel_id)
        if existing:
            existing.cancel()
        self._timer_tasks[channel_id] = task
    
    def cancel_timer_task(self, channel_id: int) -> None:
        """Cancel and remove timer task for a game."""
        task = self._timer_tasks.pop(channel_id, None)
        if task:
            task.cancel()


# Global game manager instance
game_manager = GameManager()
