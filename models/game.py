"""
Game state dataclasses for Word Chain Bot.
These classes manage the in-memory state of active games.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Set
import discord

from config import GameMode, GameStatus


@dataclass
class PlayerInfo:
    """Information about a player in a game."""
    user_id: int
    username: str
    display_name: str
    turn_order: int = 0
    is_eliminated: bool = False
    elimination_order: Optional[int] = None
    words_played: int = 0
    invalid_attempts: int = 0
    
    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "turn_order": self.turn_order,
            "is_eliminated": self.is_eliminated,
            "elimination_order": self.elimination_order,
            "words_played": self.words_played,
            "invalid_attempts": self.invalid_attempts,
        }


@dataclass
class WordChainGame:
    """
    Manages the state of an active Word Chain game.
    
    This class tracks all game state in memory for fast access during gameplay.
    Database persistence happens at key moments (word played, player eliminated, game end).
    """
    session_id: int
    guild_id: int
    channel_id: int
    creator_id: int
    
    game_mode: str = GameMode.NORMAL
    timer_seconds: int = 30
    status: str = GameStatus.WAITING
    
    # Players in the game (user_id -> PlayerInfo)
    players: Dict[int, PlayerInfo] = field(default_factory=dict)
    
    # Turn management
    turn_order_list: List[int] = field(default_factory=list)  # List of user_ids in turn order
    current_turn_index: int = 0
    
    # Chain tracking
    current_chain_number: int = 1
    chain_resets: int = 0
    
    # Words tracking for current chain
    current_chain_words: List[str] = field(default_factory=list)
    used_words_in_session: Set[str] = field(default_factory=set)  # All words used in session
    last_word: Optional[str] = None
    
    # Timing
    turn_start_time: Optional[datetime] = None
    timer_message_id: Optional[int] = None
    
    # Elimination tracking
    elimination_count: int = 0
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    
    @property
    def letters_to_match(self) -> int:
        """Number of letters the next word must start with."""
        return 2 if self.game_mode == GameMode.HARD else 1
    
    @property
    def required_start(self) -> Optional[str]:
        """The letters the next word must start with (from last word)."""
        if not self.last_word:
            return None
        return self.last_word[-self.letters_to_match:].lower()
    
    @property
    def current_player_id(self) -> Optional[int]:
        """Get the user_id of the current player."""
        if not self.turn_order_list:
            return None
        active_players = [p for p in self.turn_order_list if not self.players[p].is_eliminated]
        if not active_players:
            return None
        # Wrap around the index
        return active_players[self.current_turn_index % len(active_players)]
    
    @property
    def active_players(self) -> List[PlayerInfo]:
        """List of players who haven't been eliminated."""
        return [p for p in self.players.values() if not p.is_eliminated]
    
    @property
    def active_player_count(self) -> int:
        """Number of players still in the game."""
        return len(self.active_players)
    
    @property
    def is_game_over(self) -> bool:
        """Check if only one player remains."""
        return self.active_player_count <= 1 and self.status == GameStatus.ACTIVE
    
    @property
    def winner(self) -> Optional[PlayerInfo]:
        """Get the winner (last player standing)."""
        if self.active_player_count == 1:
            return self.active_players[0]
        return None
    
    def add_player(self, user: discord.User | discord.Member) -> PlayerInfo:
        """Add a player to the game."""
        player = PlayerInfo(
            user_id=user.id,
            username=user.name,
            display_name=user.display_name,
            turn_order=len(self.players),
        )
        self.players[user.id] = player
        self.turn_order_list.append(user.id)
        return player
    
    def remove_player(self, user_id: int) -> Optional[PlayerInfo]:
        """Remove a player from the game (only in waiting state)."""
        if user_id in self.players:
            player = self.players.pop(user_id)
            self.turn_order_list.remove(user_id)
            # Re-assign turn orders
            for i, pid in enumerate(self.turn_order_list):
                self.players[pid].turn_order = i
            return player
        return None
    
    def eliminate_player(self, user_id: int) -> Optional[PlayerInfo]:
        """Eliminate a player from the game."""
        if user_id in self.players:
            player = self.players[user_id]
            player.is_eliminated = True
            self.elimination_count += 1
            player.elimination_order = self.elimination_count
            return player
        return None
    
    def start_game(self) -> None:
        """Start the game."""
        self.status = GameStatus.ACTIVE
        self.started_at = datetime.utcnow()
        self.current_turn_index = 0
        self.turn_start_time = datetime.utcnow()
    
    def next_turn(self) -> Optional[int]:
        """Move to the next player's turn. Returns the new current player id."""
        active_players = [p for p in self.turn_order_list if not self.players[p].is_eliminated]
        if len(active_players) <= 1:
            return None
        self.current_turn_index = (self.current_turn_index + 1) % len(active_players)
        self.turn_start_time = datetime.utcnow()
        return self.current_player_id
    
    def reset_chain(self) -> None:
        """Reset the chain (happens after elimination)."""
        self.chain_resets += 1
        self.current_chain_number += 1
        self.current_chain_words = []
        self.last_word = None
    
    def add_word(self, word: str, user_id: int) -> None:
        """Add a word to the current chain."""
        word_lower = word.lower()
        self.current_chain_words.append(word_lower)
        self.used_words_in_session.add(word_lower)
        self.last_word = word_lower
        
        if user_id in self.players:
            self.players[user_id].words_played += 1
    
    def is_word_used(self, word: str) -> bool:
        """Check if a word has already been used in this session."""
        return word.lower() in self.used_words_in_session
    
    def matches_required_start(self, word: str) -> bool:
        """Check if a word starts with the required letters."""
        if not self.required_start:
            return True  # First word of chain can be anything
        return word.lower().startswith(self.required_start)
    
    def get_turn_order_display(self) -> str:
        """Get a formatted string showing turn order."""
        lines = []
        for i, user_id in enumerate(self.turn_order_list):
            player = self.players[user_id]
            if player.is_eliminated:
                lines.append(f"~~{i+1}. {player.display_name}~~ (loại)")
            elif user_id == self.current_player_id:
                lines.append(f"**{i+1}. {player.display_name}** ← lượt hiện tại")
            else:
                lines.append(f"{i+1}. {player.display_name}")
        return "\n".join(lines)
    
    def to_dict(self) -> dict:
        """Convert game state to dictionary for debugging/logging."""
        return {
            "session_id": self.session_id,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "creator_id": self.creator_id,
            "game_mode": self.game_mode,
            "timer_seconds": self.timer_seconds,
            "status": self.status,
            "players": {k: v.to_dict() for k, v in self.players.items()},
            "current_player_id": self.current_player_id,
            "current_chain_number": self.current_chain_number,
            "chain_resets": self.chain_resets,
            "last_word": self.last_word,
            "used_words_count": len(self.used_words_in_session),
        }
