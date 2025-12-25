"""
SQLAlchemy database models for Word Chain Bot.
Defines the database schema using async SQLAlchemy ORM.
"""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    BigInteger,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class GameSession(Base):
    """
    Represents a game session (party).
    
    A game session is created when a user starts a new word chain game.
    Other users can join until the creator starts the game.
    """
    __tablename__ = "game_sessions"
    
    session_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    creator_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    
    game_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    timer_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="waiting")
    
    chain_resets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    winner_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # Relationships
    participants: Mapped[List["GameParticipant"]] = relationship(
        "GameParticipant",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    words: Mapped[List["SessionWord"]] = relationship(
        "SessionWord",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class GameParticipant(Base):
    """
    Represents a player in a game session.
    
    Tracks each player's status, turn order, and statistics within a session.
    """
    __tablename__ = "game_participants"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("game_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    
    turn_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_eliminated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    elimination_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    words_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    eliminated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    session: Mapped["GameSession"] = relationship("GameSession", back_populates="participants")
    
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="unique_participant_per_session"),
    )


class SessionWord(Base):
    """
    Tracks all words played in a game session.
    
    Each word belongs to a specific chain (chain_number).
    When a player is eliminated, a new chain starts with chain_number incremented.
    """
    __tablename__ = "session_words"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("game_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    chain_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    word_order: Mapped[int] = mapped_column(Integer, nullable=False)
    
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    
    played_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    
    # Relationships
    session: Mapped["GameSession"] = relationship("GameSession", back_populates="words")


class WordCache(Base):
    """
    Cache for AI word validation results.
    
    Stores validated words to avoid repeated API calls.
    """
    __tablename__ = "word_cache"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_plural: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    word_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ai_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    validated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    
    __table_args__ = (
        UniqueConstraint("word", "language", name="unique_word_per_language"),
    )


class PlayerStats(Base):
    """
    Aggregated statistics for players.
    
    Tracks overall performance across all games in a guild.
    """
    __tablename__ = "player_stats"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    
    games_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    games_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_words: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    longest_word: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    total_timeouts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_invalid_words: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    current_win_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_win_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    __table_args__ = (
        UniqueConstraint("user_id", "guild_id", name="unique_user_per_guild"),
    )
