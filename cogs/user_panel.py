import discord
from discord.ext import commands
from datetime import datetime

class UserPanelView(discord.ui.View):
    """View для пользовательской панели"""
    
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot
    
    @discord.ui.button(label="🏓 Ping", style=discord.ButtonStyle.green, custom_id="ping_button")
    async def ping_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Кнопка для проверки пинга"""
        # Вычисляем задержку
        latency_ms = round(self.bot.latency * 1000)
        
        # Определяем цвет и статус в зависимости от задержки
        if latency_ms < 100:
            color = 0x2ECC71  # Зеленый
            status = "Отлично! 🟢"
            emoji = "⚡"
        elif latency_ms < 200:
            color = 0xF1C40F  # Желтый
            status = "Хорошо 🟡"
            emoji = "✅"
        elif latency_ms < 300:
            color = 0xE67E22  # Оранжевый
            status = "Средне 🟠"
            emoji = "⚠️"
        else:
            color = 0xE74C3C  # Красный
            status = "Плохо 🔴"
            emoji = "❌"
        
        # Создаем embed с результатом
        embed = discord.Embed(
            title=f"{emoji} Пинг бота",
            description=f"**Задержка:** {latency_ms} мс\n**Статус:** {status}",
            color=color,
            timestamp=datetime.utcnow()
        )
        
        # Добавляем дополнительную информацию
        embed.add_field(
            name="📊 Интерпретация",
            value=(
                "🟢 < 100 мс - Отличная связь\n"
                "🟡 100-200 мс - Хорошая связь\n"
                "🟠 200-300 мс - Средняя связь\n"
                "🔴 > 300 мс - Плохая связь"
            ),
            inline=False
        )
        
        embed.set_footer(
            text=f"Запросил: {interaction.user.name}",
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class UserPanel(commands.Cog):
    """Пользовательская панель - доступна всем участникам сервера"""
    
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(
        name="user_panel",
        description="👤 Пользовательская панель (доступна всем участникам)"
    )
    async def user_panel(self, interaction: discord.Interaction):
        """Панель для всех пользователей - без ограничений по правам"""
        
        # Создаем приветственный embed
        embed = discord.Embed(
            title="👤 Пользовательская панель",
            description=(
                "Добро пожаловать в пользовательскую панель!\n\n"
                "Эта панель доступна **всем участникам сервера** без исключения.\n"
                "Здесь вы можете проверить различную информацию о боте."
            ),
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )
        
        # Добавляем информацию о доступных функциях
        embed.add_field(
            name="🏓 Ping",
            value="Проверить задержку бота и качество соединения",
            inline=False
        )
        
        # Информация о пользователе
        embed.add_field(
            name="ℹ️ Ваша информация",
            value=(
                f"**Пользователь:** {interaction.user.mention}\n"
                f"**ID:** `{interaction.user.id}`\n"
                f"**Роли:** {len(interaction.user.roles) - 1}"  # -1 чтобы не считать @everyone
            ),
            inline=False
        )
        
        # Информация о сервере
        embed.add_field(
            name="🏠 Сервер",
            value=(
                f"**Название:** {interaction.guild.name}\n"
                f"**Участников:** {interaction.guild.member_count}\n"
                f"**ID:** `{interaction.guild.id}`"
            ),
            inline=False
        )
        
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(
            text=f"Запросил: {interaction.user.name}",
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        
        # Создаем View с кнопкой
        view = UserPanelView(self.bot)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(UserPanel(bot))
    print("✅ Загружен: UserPanel (пользовательская панель)")
