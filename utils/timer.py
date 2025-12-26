"""
Turn Timer utility for Word Chain Bot.
Manages turn countdown and visual updates.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Callable, Awaitable

import discord

from config import SETTINGS, LOGGER_NAME_GAME
from models.game import WordChainGame
from views.game_ui import TimerEmbed

logger = logging.getLogger(LOGGER_NAME_GAME)


class TurnTimer:
    """
    Manages turn timer with visual countdown updates.
    
    Features:
    - Periodic embed updates showing remaining time
    - Callback on timeout
    - Cancellation support
    """
    
    def __init__(
        self,
        game: WordChainGame,
        channel: discord.TextChannel,
        on_timeout: Callable[[int], Awaitable[None]],  # user_id
        update_interval: int = None
    ):
        self.game = game
        self.channel = channel
        self.on_timeout = on_timeout
        self.update_interval = update_interval or SETTINGS.timer_update_interval
        
        self._task: Optional[asyncio.Task] = None
        self._timer_message: Optional[discord.Message] = None
        self._cancelled = False
        self._current_player_id: Optional[int] = None
    
    async def start(self) -> None:
        """Start the timer for the current player."""
        self._cancelled = False
        self._current_player_id = self.game.current_player_id
        
        if not self._current_player_id:
            logger.warning("No current player to start timer for")
            return
        
        # Reset turn start time
        self.game.turn_start_time = datetime.utcnow()
        
        # Mention the current player
        await self.channel.send(f"<@{self._current_player_id}> đến lượt của bạn! ⏰")
        
        # Create initial timer message
        embed = TimerEmbed.create(self.game, self.game.timer_seconds)
        self._timer_message = await self.channel.send(embed=embed)
        self.game.timer_message_id = self._timer_message.id
        
        # Start countdown task
        self._task = asyncio.create_task(self._countdown())
    
    async def stop(self) -> None:
        """Stop the timer without triggering timeout."""
        self._cancelled = True
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        # Delete timer message
        if self._timer_message:
            try:
                await self._timer_message.delete()
            except discord.NotFound:
                pass
            self._timer_message = None
    
    async def reset(self) -> None:
        """Reset timer for the next player."""
        await self.stop()
        await self.start()
    
    async def _countdown(self) -> None:
        """Main countdown loop."""
        seconds_remaining = self.game.timer_seconds
        
        try:
            while seconds_remaining > 0 and not self._cancelled:
                # Wait for update interval or remaining time, whichever is shorter
                wait_time = min(self.update_interval, seconds_remaining)
                await asyncio.sleep(wait_time)
                
                if self._cancelled:
                    break
                
                seconds_remaining -= wait_time
                
                # Update timer message
                if self._timer_message and seconds_remaining > 0:
                    try:
                        embed = TimerEmbed.create(self.game, seconds_remaining)
                        await self._timer_message.edit(embed=embed)
                    except discord.NotFound:
                        # Message was deleted, recreate it
                        embed = TimerEmbed.create(self.game, seconds_remaining)
                        self._timer_message = await self.channel.send(embed=embed)
                    except discord.HTTPException as e:
                        logger.warning(f"Failed to update timer message: {e}")
            
            # Timeout occurred
            if not self._cancelled and self._current_player_id:
                # Send timeout message
                player = self.game.players.get(self._current_player_id)
                if player:
                    timeout_embed = TimerEmbed.timeout(player.display_name)
                    await self.channel.send(embed=timeout_embed)
                
                # Delete timer message
                if self._timer_message:
                    try:
                        await self._timer_message.delete()
                    except discord.NotFound:
                        pass
                
                # Trigger timeout callback
                await self.on_timeout(self._current_player_id)
                
        except asyncio.CancelledError:
            logger.debug("Timer task cancelled")
            raise
        except Exception as e:
            logger.error(f"Timer error: {e}")
    
    @property
    def is_running(self) -> bool:
        """Check if timer is currently running."""
        return self._task is not None and not self._task.done()


class TimerManager:
    """
    Manages multiple turn timers across different games.
    """
    
    def __init__(self):
        self._timers: dict[int, TurnTimer] = {}  # channel_id -> TurnTimer
    
    def get_timer(self, channel_id: int) -> Optional[TurnTimer]:
        """Get timer for a channel."""
        return self._timers.get(channel_id)
    
    async def create_timer(
        self,
        game: WordChainGame,
        channel: discord.TextChannel,
        on_timeout: Callable[[int], Awaitable[None]]
    ) -> TurnTimer:
        """Create and start a new timer."""
        # Stop existing timer if any
        await self.stop_timer(game.channel_id)
        
        timer = TurnTimer(game, channel, on_timeout)
        self._timers[game.channel_id] = timer
        await timer.start()
        
        return timer
    
    async def stop_timer(self, channel_id: int) -> None:
        """Stop and remove timer for a channel."""
        timer = self._timers.pop(channel_id, None)
        if timer:
            await timer.stop()
    
    async def reset_timer(self, channel_id: int) -> None:
        """Reset timer for next turn."""
        timer = self._timers.get(channel_id)
        if timer:
            await timer.reset()
    
    async def stop_all(self) -> None:
        """Stop all active timers."""
        for timer in list(self._timers.values()):
            await timer.stop()
        self._timers.clear()


# Global timer manager instance
timer_manager = TimerManager()
