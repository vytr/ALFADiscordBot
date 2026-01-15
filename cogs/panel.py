import discord
from discord.ext import commands
from datetime import datetime


class PanelView(discord.ui.View):
    """Главная панель управления ботом"""
    
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot
    
    @discord.ui.button(
        label="📈 Статистика",
        style=discord.ButtonStyle.blurple,
        custom_id="stats_button",
        row=0
    )
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Переход в раздел статистики"""
        await interaction.response.send_message(
            "🚧 Раздел статистики в разработке...",
            ephemeral=True
        )
    
    @discord.ui.button(
        label="👥 Whitelist",
        style=discord.ButtonStyle.green,
        custom_id="whitelist_button",
        row=0
    )
    async def whitelist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Переход в раздел whitelist"""
        # Проверка прав: только администраторы
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "⛔ Управление whitelist доступно только администраторам!",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(
            "🚧 Раздел whitelist в разработке...",
            ephemeral=True
        )
    
    @discord.ui.button(
        label="📊 Опросы",
        style=discord.ButtonStyle.gray,
        custom_id="polls_button",
        row=1
    )
    async def polls_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Переход в раздел опросов"""
        await interaction.response.send_message(
            "🚧 Раздел опросов в разработке...",
            ephemeral=True
        )
    
    @discord.ui.button(
        label="⚠️ Предупреждения",
        style=discord.ButtonStyle.red,
        custom_id="warnings_button",
        row=1
    )
    async def warnings_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Переход в раздел предупреждений"""
        # Проверка прав: администратор или whitelist
        if not interaction.user.guild_permissions.administrator:
            if not self.bot.db.is_whitelisted(interaction.guild.id, interaction.user.id):
                await interaction.response.send_message(
                    "⛔ Система предупреждений доступна только администраторам и whitelisted пользователям!",
                    ephemeral=True
                )
                return
        
        await interaction.response.send_message(
            "🚧 Раздел предупреждений в разработке...",
            ephemeral=True
        )


class Panel(commands.Cog):
    """Интерактивная панель управления ботом"""
    
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(
        name="panel",
        description="🎛️ Панель управления ALFA Bot"
    )
    async def panel(self, interaction: discord.Interaction):
        """Открыть главную панель управления"""
        
        # Проверка прав: администратор или в whitelist
        if not interaction.user.guild_permissions.administrator:
            if not self.bot.db.is_whitelisted(interaction.guild.id, interaction.user.id):
                await interaction.response.send_message(
                    "❌ У вас нет прав для использования панели управления!\n"
                    "Панель доступна только администраторам и пользователям в whitelist.",
                    ephemeral=True
                )
                return
        
        # Создаем embed главной панели
        embed = discord.Embed(
            title="🎛️ ALFA Bot Control Panel",
            description=(
                "Добро пожаловать в панель управления!\n"
                "Выберите нужный раздел с помощью кнопок ниже.\n\n"
                "**Доступные разделы:**\n"
                "📈 **Статистика** — просмотр активности пользователей\n"
                "👥 **Whitelist** — управление доступом к командам\n"
                "📊 **Опросы** — создание и управление опросами\n"
                "⚠️ **Предупреждения** — система выговоров"
            ),
            color=0x5865F2,
            timestamp=datetime.utcnow()
        )
        
        # Информация о пользователе
        embed.add_field(
            name="👤 Ваш статус",
            value=(
                f"**Пользователь:** {interaction.user.mention}\n"
                f"**Права:** {'👑 Администратор' if interaction.user.guild_permissions.administrator else '✅ Whitelist'}"
            ),
            inline=True
        )
        
        # Информация о сервере
        embed.add_field(
            name="🏠 Сервер",
            value=(
                f"**Название:** {interaction.guild.name}\n"
                f"**Участников:** {interaction.guild.member_count}"
            ),
            inline=True
        )
        
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        embed.set_footer(
            text=f"Запросил: {interaction.user.name}",
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        
        # Отправляем панель
        await interaction.response.send_message(
            embed=embed,
            view=PanelView(self.bot),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Panel(bot))