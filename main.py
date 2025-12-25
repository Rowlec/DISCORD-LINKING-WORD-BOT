"""
Word Chain Discord Bot - Main Entry Point

A Discord bot for playing word chain games with AI-powered word validation.
Features:
- Party-based game system (2-10 players)
- AI word validation (OpenAI/Anthropic)
- Visual turn timers
- Elimination on timeout only
- Multiple game modes (Normal/Hard)
- Statistics and leaderboards
"""
import asyncio
import logging
import sys
from pathlib import Path

import discord
from discord.ext import commands

from config import SETTINGS, LOGGER_NAME_MAIN, LOGGER_NAME_GAME, LOGGER_NAME_AI, LOGGER_NAME_DB
from database import init_database, close_database

# Setup logging
def setup_logging():
    """Configure logging for the bot."""
    log_level = logging.DEBUG if SETTINGS.dev_mode else logging.INFO
    
    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    # File handler
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(
        log_dir / "bot.log",
        encoding="utf-8",
        mode="a"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Setup loggers
    for logger_name in [LOGGER_NAME_MAIN, LOGGER_NAME_GAME, LOGGER_NAME_AI, LOGGER_NAME_DB]:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
    
    # Discord.py logger
    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(logging.WARNING)
    discord_logger.addHandler(console_handler)
    
    return logging.getLogger(LOGGER_NAME_MAIN)


class WordChainBot(commands.Bot):
    """Main bot class for Word Chain Discord Bot."""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # Required for reading messages
        intents.guilds = True
        intents.members = True
        
        super().__init__(
            command_prefix="!",  # Prefix for legacy commands (not used)
            intents=intents,
            help_command=None,  # Disable default help
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name="/wordchain create"
            )
        )
        
        self.logger = logging.getLogger(LOGGER_NAME_MAIN)
    
    async def setup_hook(self):
        """Called when the bot is starting up."""
        self.logger.info("Setting up bot...")
        
        # Initialize database
        await init_database()
        
        # Load cogs
        cogs = [
            "cogs.game_commands",
            "cogs.word_handler",
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                self.logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                self.logger.error(f"Failed to load cog {cog}: {e}")
                raise
        
        # Sync slash commands
        self.logger.info("Syncing slash commands...")
        try:
            synced = await self.tree.sync()
            self.logger.info(f"Synced {len(synced)} slash commands")
        except Exception as e:
            self.logger.error(f"Failed to sync commands: {e}")
    
    async def on_ready(self):
        """Called when the bot is ready."""
        self.logger.info(f"Bot is ready!")
        self.logger.info(f"Logged in as: {self.user.name} (ID: {self.user.id})")
        self.logger.info(f"Connected to {len(self.guilds)} guilds")
        self.logger.info(f"Using AI provider: {SETTINGS.ai_provider}")
        self.logger.info(f"Dev mode: {SETTINGS.dev_mode}")
    
    async def on_guild_join(self, guild: discord.Guild):
        """Called when the bot joins a new guild."""
        self.logger.info(f"Joined guild: {guild.name} (ID: {guild.id})")
    
    async def on_guild_remove(self, guild: discord.Guild):
        """Called when the bot is removed from a guild."""
        self.logger.info(f"Left guild: {guild.name} (ID: {guild.id})")
    
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Global error handler for commands."""
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore command not found
        
        self.logger.error(f"Command error: {error}")
    
    async def close(self):
        """Clean up before shutting down."""
        self.logger.info("Shutting down bot...")
        
        # Stop all active timers
        from utils.timer import timer_manager
        await timer_manager.stop_all()
        
        # Close database
        await close_database()
        
        await super().close()


async def main():
    """Main entry point."""
    # Setup logging
    logger = setup_logging()
    logger.info("Starting Word Chain Bot...")
    
    # Validate configuration
    if not SETTINGS.discord_token:
        logger.error("DISCORD_TOKEN not set! Please set it in .env file.")
        sys.exit(1)
    
    if SETTINGS.ai_provider == "openai" and not SETTINGS.openai_api_key:
        logger.error("OPENAI_API_KEY not set! Please set it in .env file.")
        sys.exit(1)
    
    if SETTINGS.ai_provider == "anthropic" and not SETTINGS.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY not set! Please set it in .env file.")
        sys.exit(1)
    
    # Create and run bot
    bot = WordChainBot()
    
    try:
        async with bot:
            await bot.start(SETTINGS.discord_token)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise
    finally:
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
