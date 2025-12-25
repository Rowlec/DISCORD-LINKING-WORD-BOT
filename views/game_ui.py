"""
Game UI components for Word Chain Bot.
Provides embeds for game state and timer display.
"""
import discord
from datetime import datetime
from typing import Optional

from config import (
    GameMode,
    GameStatus,
    TIMER_EMOJI_SAFE,
    TIMER_EMOJI_WARNING,
    TIMER_EMOJI_DANGER,
    TIMER_EMOJI_EMPTY,
)
from models.game import WordChainGame


class GameEmbed:
    """Factory for creating game-related embeds."""
    
    @staticmethod
    def game_started(game: WordChainGame) -> discord.Embed:
        """Create embed for game start announcement."""
        mode_name = "Thường (1 chữ cái)" if game.game_mode == GameMode.NORMAL else "Khó (2 chữ cái)"
        
        embed = discord.Embed(
            title="🎮 Word Chain - Game Bắt Đầu!",
            description=(
                f"**Chế độ:** {mode_name}\n"
                f"**Thời gian mỗi lượt:** {game.timer_seconds} giây\n"
                f"**Số người chơi:** {len(game.players)}\n\n"
                "📝 **Luật chơi:**\n"
                f"• Nhập từ bắt đầu bằng {game.letters_to_match} chữ cái cuối của từ trước\n"
                "• Không dùng từ đã sử dụng\n"
                "• Không dùng từ số nhiều\n"
                "• Hết giờ = bị loại\n"
                "• Từ sai chỉ bị cảnh báo, không bị loại\n\n"
                "🏆 Người cuối cùng còn lại sẽ thắng!"
            ),
            color=discord.Color.green()
        )
        
        # Player order
        player_list = game.get_turn_order_display()
        embed.add_field(
            name="👥 Thứ tự chơi",
            value=player_list,
            inline=False
        )
        
        current_player = game.players.get(game.current_player_id)
        if current_player:
            embed.add_field(
                name="▶️ Lượt đầu tiên",
                value=f"<@{current_player.user_id}> hãy nhập một từ bất kỳ!",
                inline=False
            )
        
        return embed
    
    @staticmethod
    def word_accepted(
        word: str,
        player_name: str,
        next_start: str,
        words_in_chain: int
    ) -> discord.Embed:
        """Create embed for accepted word."""
        embed = discord.Embed(
            title="✅ Từ hợp lệ!",
            description=(
                f"**{player_name}** đã nhập: **{word}**\n\n"
                f"📎 Chuỗi hiện tại: **{words_in_chain}** từ\n"
                f"➡️ Từ tiếp theo phải bắt đầu bằng: **{next_start.upper()}**"
            ),
            color=discord.Color.green()
        )
        return embed
    
    @staticmethod
    def word_invalid(
        word: str,
        player_name: str,
        reason: str
    ) -> discord.Embed:
        """Create embed for invalid word (warning only)."""
        embed = discord.Embed(
            title="⚠️ Từ không hợp lệ!",
            description=(
                f"**{player_name}** đã nhập: **{word}**\n\n"
                f"❌ Lý do: {reason}\n\n"
                "💡 Hãy thử lại với từ khác!"
            ),
            color=discord.Color.orange()
        )
        return embed
    
    @staticmethod
    def word_already_used(word: str, player_name: str) -> discord.Embed:
        """Create embed for already used word."""
        embed = discord.Embed(
            title="⚠️ Từ đã được sử dụng!",
            description=(
                f"**{player_name}** đã nhập: **{word}**\n\n"
                f"❌ Từ này đã được dùng trong game rồi!\n\n"
                "💡 Hãy nghĩ từ khác!"
            ),
            color=discord.Color.orange()
        )
        return embed
    
    @staticmethod
    def wrong_start(
        word: str,
        player_name: str,
        expected_start: str
    ) -> discord.Embed:
        """Create embed for word with wrong starting letters."""
        embed = discord.Embed(
            title="⚠️ Sai chữ cái đầu!",
            description=(
                f"**{player_name}** đã nhập: **{word}**\n\n"
                f"❌ Từ phải bắt đầu bằng: **{expected_start.upper()}**\n\n"
                "💡 Hãy thử lại!"
            ),
            color=discord.Color.orange()
        )
        return embed
    
    @staticmethod
    def plural_word(word: str, player_name: str) -> discord.Embed:
        """Create embed for plural word rejection."""
        embed = discord.Embed(
            title="⚠️ Không chấp nhận từ số nhiều!",
            description=(
                f"**{player_name}** đã nhập: **{word}**\n\n"
                f"❌ Từ này là dạng số nhiều và không được chấp nhận!\n\n"
                "💡 Hãy dùng dạng số ít của từ!"
            ),
            color=discord.Color.orange()
        )
        return embed
    
    @staticmethod
    def player_eliminated(
        player_name: str,
        reason: str,
        remaining: int
    ) -> discord.Embed:
        """Create embed for player elimination."""
        embed = discord.Embed(
            title="💀 Người chơi bị loại!",
            description=(
                f"**{player_name}** đã bị loại!\n\n"
                f"📋 Lý do: {reason}\n"
                f"👥 Còn lại: **{remaining}** người\n\n"
                "🔄 Chuỗi từ đã được reset - người tiếp theo có thể bắt đầu với bất kỳ từ nào!"
            ),
            color=discord.Color.red()
        )
        return embed
    
    @staticmethod
    def player_forfeit(player_name: str, remaining: int) -> discord.Embed:
        """Create embed for player forfeit."""
        embed = discord.Embed(
            title="🏳️ Người chơi bỏ cuộc!",
            description=(
                f"**{player_name}** đã bỏ cuộc!\n\n"
                f"👥 Còn lại: **{remaining}** người\n\n"
                "🔄 Chuỗi từ đã được reset!"
            ),
            color=discord.Color.dark_gray()
        )
        return embed
    
    @staticmethod
    def game_winner(
        winner_name: str,
        winner_id: int,
        total_words: int,
        chain_resets: int,
        duration_minutes: int
    ) -> discord.Embed:
        """Create embed for game winner."""
        embed = discord.Embed(
            title="🏆 KẾT THÚC - Có người chiến thắng!",
            description=(
                f"🎉 Chúc mừng <@{winner_id}>!\n\n"
                f"**{winner_name}** là người cuối cùng còn lại và giành chiến thắng!"
            ),
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="📊 Thống kê game",
            value=(
                f"📝 Tổng số từ: **{total_words}**\n"
                f"🔄 Số lần reset chuỗi: **{chain_resets}**\n"
                f"⏱️ Thời gian: **{duration_minutes}** phút"
            ),
            inline=False
        )
        
        return embed
    
    @staticmethod
    def game_cancelled(reason: str = "Chủ party đã hủy") -> discord.Embed:
        """Create embed for cancelled game."""
        embed = discord.Embed(
            title="❌ Game đã bị hủy",
            description=f"Lý do: {reason}",
            color=discord.Color.dark_gray()
        )
        return embed


class TimerEmbed:
    """Factory for creating timer display embeds."""
    
    @staticmethod
    def create(
        game: WordChainGame,
        seconds_remaining: int,
    ) -> discord.Embed:
        """
        Create a timer embed with visual progress bar.
        
        Args:
            game: Current game state
            seconds_remaining: Seconds left in current turn
        """
        current_player = game.players.get(game.current_player_id)
        if not current_player:
            return discord.Embed(title="⏱️ Timer", color=discord.Color.gray())
        
        # Calculate progress bar
        total_seconds = game.timer_seconds
        progress = seconds_remaining / total_seconds
        
        # Determine color and emojis based on time remaining
        if progress > 0.5:
            color = discord.Color.green()
            bar_emoji = TIMER_EMOJI_SAFE
        elif progress > 0.25:
            color = discord.Color.yellow()
            bar_emoji = TIMER_EMOJI_WARNING
        else:
            color = discord.Color.red()
            bar_emoji = TIMER_EMOJI_DANGER
        
        # Create visual progress bar (10 segments)
        filled = int(progress * 10)
        empty = 10 - filled
        progress_bar = bar_emoji * filled + TIMER_EMOJI_EMPTY * empty
        
        # Build embed
        embed = discord.Embed(
            title=f"⏱️ Lượt của {current_player.display_name}",
            color=color
        )
        
        # Timer display
        embed.add_field(
            name=f"⏳ Còn {seconds_remaining} giây",
            value=progress_bar,
            inline=False
        )
        
        # What they need to type
        if game.last_word:
            next_start = game.required_start.upper() if game.required_start else "?"
            embed.add_field(
                name="📝 Từ trước",
                value=f"**{game.last_word}**",
                inline=True
            )
            embed.add_field(
                name="➡️ Phải bắt đầu bằng",
                value=f"**{next_start}**",
                inline=True
            )
        else:
            embed.add_field(
                name="🆕 Bắt đầu chuỗi mới!",
                value="Nhập bất kỳ từ nào để bắt đầu",
                inline=False
            )
        
        # Chain info
        embed.add_field(
            name="📎 Chuỗi hiện tại",
            value=f"{len(game.current_chain_words)} từ",
            inline=True
        )
        
        return embed
    
    @staticmethod
    def timeout(player_name: str) -> discord.Embed:
        """Create embed for timeout."""
        embed = discord.Embed(
            title="⏰ HẾT GIỜ!",
            description=f"**{player_name}** đã hết thời gian!",
            color=discord.Color.red()
        )
        return embed
