"""
Configuration settings for the Word Chain Discord Bot.
Loads environment variables and defines constants.
"""
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Discord Bot Token
    discord_token: str = Field(default=None, validation_alias="DISCORD_TOKEN")
    
    # AI Provider Settings
    ai_provider: str = Field(default="openai", validation_alias="AI_PROVIDER")  # "openai" or "anthropic"
    openai_api_key: Optional[str] = Field(default=None, validation_alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    ai_model: str = Field(default="gpt-4o-mini", validation_alias="AI_MODEL")
    
    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///word_chain_bot.db",
        validation_alias="DATABASE_URL"
    )
    
    # Game Settings
    default_timer_seconds: int = Field(default=30, validation_alias="DEFAULT_TIMER_SECONDS")
    min_players: int = Field(default=2, validation_alias="MIN_PLAYERS")
    max_players: int = Field(default=10, validation_alias="MAX_PLAYERS")
    
    # Timer update interval (seconds)
    timer_update_interval: int = Field(default=3, validation_alias="TIMER_UPDATE_INTERVAL")
    
    # Cache settings
    word_cache_expiry_days: int = Field(default=30, validation_alias="WORD_CACHE_EXPIRY_DAYS")
    
    # Development mode
    dev_mode: bool = Field(default=False, validation_alias="DEV_MODE")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Global settings instance
SETTINGS = Settings()

# Game Mode Constants
class GameMode:
    NORMAL = "normal"
    HARD = "hard"

# Timer Options (seconds)
TIMER_OPTIONS = [30, 45, 60]

# Game Status
class GameStatus:
    WAITING = "waiting"
    ACTIVE = "active"
    FINISHED = "finished"

# Timer Visual States
TIMER_EMOJI_SAFE = "🟢"
TIMER_EMOJI_WARNING = "🟡"
TIMER_EMOJI_DANGER = "🔴"
TIMER_EMOJI_EMPTY = "⚪"

# Logger names
LOGGER_NAME_MAIN = "__main__"
LOGGER_NAME_GAME = "__game__"
LOGGER_NAME_AI = "__ai_validator__"
LOGGER_NAME_DB = "__database__"

# Supported Languages
SUPPORTED_LANGUAGES = {
    "en": "English",
    "vi": "Vietnamese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}

DEFAULT_LANGUAGE = "en"
