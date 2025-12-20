import discord
from discord.ext import commands
from datetime import datetime

class CustomHelpCommand(commands.HelpCommand):
    """Кастомная команда помощи с красивым embed"""

    async def send_bot_help(self, mapping):
        """Отправляет общую справку по всем командам"""
        embed = discord.Embed(
            title="📖 Справка по командам бота",
            description="Список всех доступных команд",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        # Группируем команды по категориям (cogs)
        for cog, cmds in mapping.items():
            # Фильтруем команды, которые может видеть пользователь
            filtered = await self.filter_commands(cmds, sort=True)
            if filtered:
                cog_name = getattr(cog, "qualified_name", "Другие команды")

                # Формируем список команд
                command_list = []
                for cmd in filtered:
                    command_list.append(f"`{self.context.prefix}{cmd.name}` - {cmd.short_doc or 'Нет описания'}")

                if command_list:
                    embed.add_field(
                        name=cog_name,
                        value="\n".join(command_list),
                        inline=False
                    )

        embed.set_footer(text=f"Используйте {self.context.prefix}help <команда> для подробной информации")

        channel = self.get_destination()
        await channel.send(embed=embed)

    async def send_command_help(self, command):
        """Отправляет справку по конкретной команде"""
        embed = discord.Embed(
            title=f"Команда: {self.context.prefix}{command.name}",
            description=command.help or "Нет описания",
            color=discord.Color.blue()
        )

        if command.aliases:
            embed.add_field(
                name="Альтернативные названия",
                value=", ".join(f"`{alias}`" for alias in command.aliases),
                inline=False
            )

        # Показываем использование команды
        usage = f"{self.context.prefix}{command.name}"
        if command.signature:
            usage += f" {command.signature}"

        embed.add_field(
            name="Использование",
            value=f"`{usage}`",
            inline=False
        )

        channel = self.get_destination()
        await channel.send(embed=embed)

    async def send_error_message(self, error):
        """Отправляет сообщение об ошибке"""
        embed = discord.Embed(
            title="❌ Ошибка",
            description=error,
            color=discord.Color.red()
        )
        channel = self.get_destination()
        await channel.send(embed=embed)

class Help(commands.Cog):
    """Команды помощи"""

    def __init__(self, bot):
        self.bot = bot
        self._original_help_command = bot.help_command
        bot.help_command = CustomHelpCommand()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._original_help_command

async def setup(bot):
    await bot.add_cog(Help(bot))
