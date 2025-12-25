"""
Game Commands Cog for Word Chain Bot.
Handles all slash commands related to game management.
"""
import logging
from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select, func, desc

from config import SETTINGS, LOGGER_NAME_GAME, GameMode, GameStatus, TIMER_OPTIONS
from database import async_session_factory
from models.db_models import PlayerStats, GameSession
from models.game import WordChainGame
from services.game_manager import game_manager
from services.ai_validator import word_validator
from views.party_setup import PartySetupView
from views.game_ui import GameEmbed

logger = logging.getLogger(LOGGER_NAME_GAME)


class GameCommands(commands.Cog):
    """Cog containing all game-related slash commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    wordchain = app_commands.Group(
        name="wordchain",
        description="Word Chain game commands"
    )
    
    @wordchain.command(name="create", description="Tạo một party Word Chain mới")
    @app_commands.describe(
        mode="Chế độ chơi (normal: 1 chữ, hard: 2 chữ)",
        timer="Thời gian mỗi lượt (giây)"
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Thường (1 chữ cái)", value=GameMode.NORMAL),
            app_commands.Choice(name="Khó (2 chữ cái)", value=GameMode.HARD),
        ],
        timer=[
            app_commands.Choice(name=f"{t} giây", value=t) for t in TIMER_OPTIONS
        ]
    )
    async def create_game(
        self,
        interaction: discord.Interaction,
        mode: str = GameMode.NORMAL,
        timer: int = 30
    ):
        """Create a new Word Chain game party."""
        # Check if there's already an active game in this channel
        if game_manager.has_active_game(interaction.channel_id):
            await interaction.response.send_message(
                "❌ Đã có game đang diễn ra trong kênh này! "
                "Hãy đợi game kết thúc hoặc sử dụng `/wordchain cancel` để hủy.",
                ephemeral=True
            )
            return
        
        # Check if user is already in a game in this guild
        existing_game = game_manager.get_user_active_game(
            interaction.user.id, interaction.guild_id
        )
        if existing_game:
            await interaction.response.send_message(
                f"❌ Bạn đang trong một game khác! "
                f"Hãy hoàn thành hoặc rời game đó trước.",
                ephemeral=True
            )
            return
        
        # Create the game
        game = await game_manager.create_game(
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            creator=interaction.user,
            game_mode=mode,
            timer_seconds=timer
        )
        
        # Create party setup view
        async def on_start():
            await self._start_game(interaction.channel, game)
        
        async def on_cancel():
            await game_manager.cancel_game(interaction.channel_id)
        
        view = PartySetupView(
            creator_id=interaction.user.id,
            on_start=on_start,
            on_cancel=on_cancel
        )
        view.players = [interaction.user]
        view.selected_mode = mode
        view.selected_timer = timer
        
        embed = view.create_embed()
        await interaction.response.send_message(embed=embed, view=view)
    
    async def _start_game(self, channel: discord.TextChannel, game: WordChainGame):
        """Start the game after party setup."""
        # Start the game in game manager
        success = await game_manager.start_game(channel.id)
        if not success:
            await channel.send("❌ Không thể bắt đầu game. Có lỗi xảy ra.")
            return
        
        # Send game started embed
        embed = GameEmbed.game_started(game)
        await channel.send(embed=embed)
        
        # Start the turn timer (handled by word_handler cog)
        # The word_handler will detect the game is active and start timing
        self.bot.dispatch("game_started", game, channel)
    
    @wordchain.command(name="join", description="Tham gia party Word Chain")
    async def join_game(self, interaction: discord.Interaction):
        """Join an existing Word Chain party."""
        game = game_manager.get_game(interaction.channel_id)
        
        if not game:
            await interaction.response.send_message(
                "❌ Không có party nào trong kênh này! "
                "Sử dụng `/wordchain create` để tạo mới.",
                ephemeral=True
            )
            return
        
        if game.status != GameStatus.WAITING:
            await interaction.response.send_message(
                "❌ Game đã bắt đầu! Không thể tham gia lúc này.",
                ephemeral=True
            )
            return
        
        if interaction.user.id in game.players:
            await interaction.response.send_message(
                "❌ Bạn đã ở trong party rồi!",
                ephemeral=True
            )
            return
        
        if len(game.players) >= SETTINGS.max_players:
            await interaction.response.send_message(
                f"❌ Party đã đầy! (tối đa {SETTINGS.max_players} người)",
                ephemeral=True
            )
            return
        
        player = await game_manager.join_game(interaction.channel_id, interaction.user)
        if player:
            await interaction.response.send_message(
                f"✅ **{interaction.user.display_name}** đã tham gia party! "
                f"({len(game.players)}/{SETTINGS.max_players})"
            )
        else:
            await interaction.response.send_message(
                "❌ Không thể tham gia party.",
                ephemeral=True
            )
    
    @wordchain.command(name="leave", description="Rời khỏi party (chỉ khi chưa bắt đầu)")
    async def leave_game(self, interaction: discord.Interaction):
        """Leave a Word Chain party before it starts."""
        game = game_manager.get_game(interaction.channel_id)
        
        if not game:
            await interaction.response.send_message(
                "❌ Không có party nào trong kênh này!",
                ephemeral=True
            )
            return
        
        if game.status != GameStatus.WAITING:
            await interaction.response.send_message(
                "❌ Game đã bắt đầu! Sử dụng `/wordchain forfeit` để bỏ cuộc.",
                ephemeral=True
            )
            return
        
        if interaction.user.id == game.creator_id:
            await interaction.response.send_message(
                "❌ Chủ party không thể rời! Hãy dùng `/wordchain cancel` để hủy.",
                ephemeral=True
            )
            return
        
        if interaction.user.id not in game.players:
            await interaction.response.send_message(
                "❌ Bạn không ở trong party!",
                ephemeral=True
            )
            return
        
        success = await game_manager.leave_game(interaction.channel_id, interaction.user.id)
        if success:
            await interaction.response.send_message(
                f"👋 **{interaction.user.display_name}** đã rời party."
            )
        else:
            await interaction.response.send_message(
                "❌ Không thể rời party.",
                ephemeral=True
            )
    
    @wordchain.command(name="forfeit", description="Bỏ cuộc (khi game đang chơi)")
    async def forfeit_game(self, interaction: discord.Interaction):
        """Forfeit and leave an ongoing game."""
        game = game_manager.get_game(interaction.channel_id)
        
        if not game:
            await interaction.response.send_message(
                "❌ Không có game nào trong kênh này!",
                ephemeral=True
            )
            return
        
        if game.status != GameStatus.ACTIVE:
            await interaction.response.send_message(
                "❌ Game chưa bắt đầu!",
                ephemeral=True
            )
            return
        
        if interaction.user.id not in game.players:
            await interaction.response.send_message(
                "❌ Bạn không ở trong game này!",
                ephemeral=True
            )
            return
        
        player = game.players[interaction.user.id]
        if player.is_eliminated:
            await interaction.response.send_message(
                "❌ Bạn đã bị loại rồi!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        # Forfeit the player
        self.bot.dispatch(
            "player_forfeit",
            game,
            interaction.channel,
            interaction.user.id
        )
    
    @wordchain.command(name="cancel", description="Hủy party (chỉ chủ party)")
    async def cancel_game(self, interaction: discord.Interaction):
        """Cancel the game (creator only)."""
        game = game_manager.get_game(interaction.channel_id)
        
        if not game:
            await interaction.response.send_message(
                "❌ Không có party nào trong kênh này!",
                ephemeral=True
            )
            return
        
        if interaction.user.id != game.creator_id:
            await interaction.response.send_message(
                "❌ Chỉ chủ party mới có thể hủy!",
                ephemeral=True
            )
            return
        
        # Cancel the game
        self.bot.dispatch("game_cancel", game, interaction.channel)
        
        await interaction.response.send_message(
            embed=GameEmbed.game_cancelled("Chủ party đã hủy")
        )
    
    @wordchain.command(name="status", description="Xem trạng thái game hiện tại")
    async def game_status(self, interaction: discord.Interaction):
        """View current game status."""
        game = game_manager.get_game(interaction.channel_id)
        
        if not game:
            await interaction.response.send_message(
                "❌ Không có game nào trong kênh này!",
                ephemeral=True
            )
            return
        
        mode_name = "Thường (1 chữ)" if game.game_mode == GameMode.NORMAL else "Khó (2 chữ)"
        status_text = {
            GameStatus.WAITING: "⏳ Đang chờ",
            GameStatus.ACTIVE: "🎮 Đang chơi",
            GameStatus.FINISHED: "✅ Đã kết thúc"
        }.get(game.status, "???")
        
        embed = discord.Embed(
            title="📊 Trạng thái Game",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Trạng thái", value=status_text, inline=True)
        embed.add_field(name="Chế độ", value=mode_name, inline=True)
        embed.add_field(name="Timer", value=f"{game.timer_seconds}s", inline=True)
        
        if game.status == GameStatus.ACTIVE:
            embed.add_field(
                name="Từ hiện tại",
                value=game.last_word or "*Chưa có*",
                inline=True
            )
            embed.add_field(
                name="Chuỗi",
                value=f"{len(game.current_chain_words)} từ",
                inline=True
            )
            current_player = game.players.get(game.current_player_id)
            if current_player:
                embed.add_field(
                    name="Lượt của",
                    value=current_player.display_name,
                    inline=True
                )
        
        embed.add_field(
            name="Người chơi",
            value=game.get_turn_order_display(),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @wordchain.command(name="stats", description="Xem thống kê của bạn")
    @app_commands.describe(user="Người muốn xem stats (để trống = bản thân)")
    async def player_stats(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None
    ):
        """View player statistics."""
        target_user = user or interaction.user
        
        async with async_session_factory() as session:
            stmt = select(PlayerStats).where(
                PlayerStats.user_id == target_user.id,
                PlayerStats.guild_id == interaction.guild_id
            )
            result = await session.execute(stmt)
            stats = result.scalar_one_or_none()
        
        if not stats:
            await interaction.response.send_message(
                f"📊 **{target_user.display_name}** chưa chơi game nào trong server này!",
                ephemeral=True
            )
            return
        
        win_rate = (stats.games_won / stats.games_played * 100) if stats.games_played > 0 else 0
        
        embed = discord.Embed(
            title=f"📊 Thống kê - {target_user.display_name}",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="🎮 Games đã chơi", value=str(stats.games_played), inline=True)
        embed.add_field(name="🏆 Thắng", value=str(stats.games_won), inline=True)
        embed.add_field(name="📈 Tỉ lệ thắng", value=f"{win_rate:.1f}%", inline=True)
        
        embed.add_field(name="📝 Tổng từ", value=str(stats.total_words), inline=True)
        embed.add_field(name="⏰ Timeout", value=str(stats.total_timeouts), inline=True)
        embed.add_field(name="❌ Từ sai", value=str(stats.total_invalid_words), inline=True)
        
        embed.add_field(name="🔥 Streak hiện tại", value=str(stats.current_win_streak), inline=True)
        embed.add_field(name="⭐ Best streak", value=str(stats.best_win_streak), inline=True)
        
        if stats.longest_word:
            embed.add_field(name="📏 Từ dài nhất", value=stats.longest_word, inline=True)
        
        await interaction.response.send_message(embed=embed)
    
    @wordchain.command(name="leaderboard", description="Xem bảng xếp hạng")
    @app_commands.describe(sort_by="Sắp xếp theo tiêu chí nào")
    @app_commands.choices(sort_by=[
        app_commands.Choice(name="Số trận thắng", value="wins"),
        app_commands.Choice(name="Tổng số từ", value="words"),
        app_commands.Choice(name="Tỉ lệ thắng", value="winrate"),
        app_commands.Choice(name="Best streak", value="streak"),
    ])
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        sort_by: str = "wins"
    ):
        """View server leaderboard."""
        async with async_session_factory() as session:
            # Build query based on sort criteria
            if sort_by == "wins":
                order_col = PlayerStats.games_won.desc()
                value_col = "games_won"
                title = "🏆 Bảng xếp hạng - Số trận thắng"
            elif sort_by == "words":
                order_col = PlayerStats.total_words.desc()
                value_col = "total_words"
                title = "📝 Bảng xếp hạng - Tổng số từ"
            elif sort_by == "winrate":
                # Calculate win rate
                order_col = (PlayerStats.games_won * 100 / PlayerStats.games_played).desc()
                value_col = "winrate"
                title = "📈 Bảng xếp hạng - Tỉ lệ thắng"
            else:  # streak
                order_col = PlayerStats.best_win_streak.desc()
                value_col = "best_win_streak"
                title = "🔥 Bảng xếp hạng - Best Streak"
            
            stmt = (
                select(PlayerStats)
                .where(
                    PlayerStats.guild_id == interaction.guild_id,
                    PlayerStats.games_played > 0
                )
                .order_by(order_col)
                .limit(10)
            )
            
            result = await session.execute(stmt)
            stats_list = result.scalars().all()
        
        if not stats_list:
            await interaction.response.send_message(
                "📊 Chưa có dữ liệu thống kê trong server này!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(title=title, color=discord.Color.gold())
        
        lines = []
        for i, stats in enumerate(stats_list, 1):
            try:
                user = await self.bot.fetch_user(stats.user_id)
                name = user.display_name
            except:
                name = f"User {stats.user_id}"
            
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            
            if value_col == "games_won":
                value = f"{stats.games_won} thắng"
            elif value_col == "total_words":
                value = f"{stats.total_words} từ"
            elif value_col == "winrate":
                rate = (stats.games_won / stats.games_played * 100) if stats.games_played > 0 else 0
                value = f"{rate:.1f}%"
            else:
                value = f"{stats.best_win_streak} streak"
            
            lines.append(f"{medal} **{name}** - {value}")
        
        embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed)
    
    @wordchain.command(name="rules", description="Xem luật chơi")
    async def rules(self, interaction: discord.Interaction):
        """Display game rules."""
        embed = discord.Embed(
            title="📜 Luật chơi Word Chain",
            description="Game nối từ với AI kiểm tra từ vựng!",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🎯 Mục tiêu",
            value="Là người cuối cùng còn lại trong game!",
            inline=False
        )
        
        embed.add_field(
            name="📝 Cách chơi",
            value=(
                "• Nhập từ bắt đầu bằng (các) chữ cái cuối của từ trước\n"
                "• **Chế độ Thường:** 1 chữ cái cuối\n"
                "• **Chế độ Khó:** 2 chữ cái cuối"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚠️ Luật từ",
            value=(
                "• Từ phải có trong từ điển\n"
                "• **Không** dùng từ số nhiều (cats ❌, cat ✅)\n"
                "• **Không** dùng từ đã được sử dụng\n"
                "• **Không** dùng tên riêng, viết tắt"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💀 Bị loại khi",
            value=(
                "• Hết thời gian (timeout)\n"
                "• Từ sai chỉ bị cảnh báo, KHÔNG bị loại!"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔄 Reset chuỗi",
            value="Khi có người bị loại, chuỗi reset và người tiếp theo được nhập từ bất kỳ.",
            inline=False
        )
        
        embed.add_field(
            name="🎮 Commands",
            value=(
                "`/wordchain create` - Tạo party\n"
                "`/wordchain join` - Tham gia\n"
                "`/wordchain leave` - Rời party\n"
                "`/wordchain forfeit` - Bỏ cuộc\n"
                "`/wordchain cancel` - Hủy party\n"
                "`/wordchain status` - Xem trạng thái\n"
                "`/wordchain stats` - Xem thống kê\n"
                "`/wordchain leaderboard` - Bảng xếp hạng\n"
                "`/wordchain check` - Kiểm tra từ"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @wordchain.command(name="check", description="Kiểm tra một từ có hợp lệ không")
    @app_commands.describe(word="Từ cần kiểm tra")
    async def check_word(self, interaction: discord.Interaction, word: str):
        """Check if a word is valid."""
        await interaction.response.defer(ephemeral=True)
        
        async with async_session_factory() as session:
            result = await word_validator.validate_word(word, session)
        
        if result.is_acceptable:
            emoji = "✅"
            status = "Hợp lệ"
            color = discord.Color.green()
        elif result.is_valid and result.is_plural:
            emoji = "⚠️"
            status = "Số nhiều (không chấp nhận)"
            color = discord.Color.orange()
        else:
            emoji = "❌"
            status = "Không hợp lệ"
            color = discord.Color.red()
        
        embed = discord.Embed(
            title=f"{emoji} Kiểm tra từ: {word}",
            color=color
        )
        
        embed.add_field(name="Trạng thái", value=status, inline=True)
        
        if result.word_type:
            embed.add_field(name="Loại từ", value=result.word_type, inline=True)
        
        if result.reason:
            embed.add_field(name="Chi tiết", value=result.reason, inline=False)
        
        if result.from_cache:
            embed.set_footer(text="📦 Từ cache")
        
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    await bot.add_cog(GameCommands(bot))
