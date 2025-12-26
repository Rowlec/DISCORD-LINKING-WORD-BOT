"""
Party Setup Views for Word Chain Bot.
Provides Discord UI components for game creation and party management.
"""
import discord
from discord import ui
from typing import Optional, Callable, Awaitable, TYPE_CHECKING

from config import SETTINGS, GameMode, TIMER_OPTIONS

if TYPE_CHECKING:
    from models.game import WordChainGame


class GameModeSelect(ui.Select):
    """Dropdown for selecting game mode."""
    
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Chế độ Thường",
                description="Từ tiếp theo bắt đầu bằng 1 chữ cái cuối",
                value=GameMode.NORMAL,
                emoji="🟢",
                default=True
            ),
            discord.SelectOption(
                label="Chế độ Khó",
                description="Từ tiếp theo bắt đầu bằng 2 chữ cái cuối",
                value=GameMode.HARD,
                emoji="🔴"
            ),
        ]
        super().__init__(
            placeholder="Chọn chế độ chơi...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="game_mode_select"
        )
    
    async def callback(self, interaction: discord.Interaction):
        # The view will handle the callback
        await interaction.response.defer()


class TimerSelect(ui.Select):
    """Dropdown for selecting turn timer duration."""
    
    def __init__(self):
        options = [
            discord.SelectOption(
                label=f"{seconds} giây",
                description=f"Mỗi lượt có {seconds} giây để trả lời",
                value=str(seconds),
                emoji="⏱️",
                default=(seconds == SETTINGS.default_timer_seconds)
            )
            for seconds in TIMER_OPTIONS
        ]
        super().__init__(
            placeholder="Chọn thời gian mỗi lượt...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="timer_select"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()


class PartySetupView(ui.View):
    """
    View for setting up a game party.
    
    Shows game options, current players, and control buttons.
    Now syncs directly with GameManager for consistent state.
    """
    
    def __init__(
        self,
        creator_id: int,
        game: "WordChainGame",
        on_start: Optional[Callable[[], Awaitable[None]]] = None,
        on_cancel: Optional[Callable[[], Awaitable[None]]] = None,
        on_join: Optional[Callable[[discord.User], Awaitable[bool]]] = None,
        on_leave: Optional[Callable[[int], Awaitable[bool]]] = None,
        timeout: float = 300.0  # 5 minutes
    ):
        super().__init__(timeout=timeout)
        self.creator_id = creator_id
        self.game = game  # Reference to actual game state
        self.on_start = on_start
        self.on_cancel = on_cancel
        self.on_join = on_join
        self.on_leave = on_leave
        
        # Add select menus
        self.mode_select = GameModeSelect()
        self.timer_select = TimerSelect()
        self.add_item(self.mode_select)
        self.add_item(self.timer_select)
    
    @property
    def can_start(self) -> bool:
        """Check if game can be started."""
        return len(self.game.players) >= SETTINGS.min_players
    
    def get_selected_mode(self) -> str:
        """Get the selected game mode."""
        if self.mode_select.values:
            return self.mode_select.values[0]
        return GameMode.NORMAL
    
    def get_selected_timer(self) -> int:
        """Get the selected timer duration."""
        if self.timer_select.values:
            return int(self.timer_select.values[0])
        return SETTINGS.default_timer_seconds
    
    @ui.button(
        label="Tham gia",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="join_game"
    )
    async def join_button(self, interaction: discord.Interaction, button: ui.Button):
        """Handle join button click."""
        user = interaction.user
        
        if user.id in self.game.players:
            await interaction.response.send_message(
                "❌ Bạn đã ở trong party rồi!",
                ephemeral=True
            )
            return
        
        if len(self.game.players) >= SETTINGS.max_players:
            await interaction.response.send_message(
                f"❌ Party đã đầy! (tối đa {SETTINGS.max_players} người)",
                ephemeral=True
            )
            return
        
        # Call the join callback to sync with GameManager
        if self.on_join:
            success = await self.on_join(user)
            if not success:
                await interaction.response.send_message(
                    "❌ Không thể tham gia party!",
                    ephemeral=True
                )
                return
        
        await interaction.response.send_message(
            f"✅ {user.display_name} đã tham gia party!",
            ephemeral=False
        )
        
        # Update the original message
        await interaction.message.edit(embed=self.create_embed(), view=self)
    
    @ui.button(
        label="Rời đi",
        style=discord.ButtonStyle.secondary,
        emoji="🚪",
        custom_id="leave_game"
    )
    async def leave_button(self, interaction: discord.Interaction, button: ui.Button):
        """Handle leave button click."""
        user = interaction.user
        
        if user.id == self.creator_id:
            await interaction.response.send_message(
                "❌ Chủ party không thể rời! Hãy hủy party nếu muốn kết thúc.",
                ephemeral=True
            )
            return
        
        if user.id not in self.game.players:
            await interaction.response.send_message(
                "❌ Bạn không ở trong party!",
                ephemeral=True
            )
            return
        
        # Call the leave callback to sync with GameManager
        if self.on_leave:
            success = await self.on_leave(user.id)
            if not success:
                await interaction.response.send_message(
                    "❌ Không thể rời party!",
                    ephemeral=True
                )
                return
        
        await interaction.response.send_message(
            f"👋 {user.display_name} đã rời party.",
            ephemeral=False
        )
        
        # Update the original message
        await interaction.message.edit(embed=self.create_embed(), view=self)
    
    @ui.button(
        label="Bắt đầu",
        style=discord.ButtonStyle.primary,
        emoji="🎮",
        custom_id="start_game",
        row=2
    )
    async def start_button(self, interaction: discord.Interaction, button: ui.Button):
        """Handle start button click."""
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message(
                "❌ Chỉ chủ party mới có thể bắt đầu game!",
                ephemeral=True
            )
            return
        
        if not self.can_start:
            await interaction.response.send_message(
                f"❌ Cần ít nhất {SETTINGS.min_players} người để bắt đầu!",
                ephemeral=True
            )
            return
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(view=self)
        
        if self.on_start:
            await self.on_start()
        
        self.stop()
    
    @ui.button(
        label="Hủy",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="cancel_game",
        row=2
    )
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        """Handle cancel button click."""
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message(
                "❌ Chỉ chủ party mới có thể hủy game!",
                ephemeral=True
            )
            return
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(
            content="❌ Party đã bị hủy.",
            embed=None,
            view=None
        )
        
        if self.on_cancel:
            await self.on_cancel()
        
        self.stop()
    
    def create_embed(self) -> discord.Embed:
        """Create the party setup embed."""
        mode_name = "Thường (1 chữ)" if self.game.game_mode == GameMode.NORMAL else "Khó (2 chữ)"
        timer = self.game.timer_seconds
        
        embed = discord.Embed(
            title="🎯 Word Chain - Tạo Party",
            description=(
                "Nhấn **Tham gia** để vào party!\n"
                f"Cần ít nhất **{SETTINGS.min_players}** người để bắt đầu."
            ),
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="⚙️ Cài đặt",
            value=f"**Chế độ:** {mode_name}\n**Thời gian:** {timer} giây/lượt",
            inline=True
        )
        
        # Get players from game state
        player_list = "\n".join(
            f"{'👑 ' if uid == self.creator_id else ''}{i+1}. {self.game.players[uid].display_name}"
            for i, uid in enumerate(self.game.turn_order_list)
        ) or "*Chưa có ai*"
        
        embed.add_field(
            name=f"👥 Người chơi ({len(self.game.players)}/{SETTINGS.max_players})",
            value=player_list,
            inline=True
        )
        
        status = "✅ Sẵn sàng!" if self.can_start else f"⏳ Đợi thêm {SETTINGS.min_players - len(self.game.players)} người..."
        embed.set_footer(text=status)
        
        return embed
    
    async def on_timeout(self):
        """Handle view timeout."""
        if self.on_cancel:
            await self.on_cancel()
