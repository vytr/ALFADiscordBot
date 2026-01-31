import discord
from discord.ext import commands
from datetime import datetime
from utils import is_admin_or_whitelisted, t

class CustomHelpCommand(commands.HelpCommand):
    """Кастомная команда помощи с красивым embed"""

    async def send_bot_help(self, mapping):
        """Отправляет общую справку по всем командам"""
        # Проверяем права пользователя
        ctx = self.context
        guild_id = ctx.guild.id

        # Проверка на администратора
        if not ctx.author.guild_permissions.administrator:
            # Проверка на whitelist
            db = ctx.bot.db
            if not db.is_whitelisted(ctx.guild.id, ctx.author.id):
                # Если нет прав - игнорируем команду (не отвечаем)
                return

        # Удаляем сообщение пользователя
        await ctx.message.delete()

        embed = discord.Embed(
            title=t('help_title', guild_id=guild_id),
            description=t('help_description', guild_id=guild_id),
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        # Группируем команды по категориям (cogs)
        for cog, cmds in mapping.items():
            # Фильтруем команды, которые может видеть пользователь
            filtered = await self.filter_commands(cmds, sort=True)
            if filtered:
                cog_name = getattr(cog, "qualified_name", t('help_other_commands', guild_id=guild_id))

                # Формируем список команд
                command_list = []
                for cmd in filtered:
                    command_list.append(f"`{self.context.prefix}{cmd.name}` - {cmd.short_doc or t('help_no_description', guild_id=guild_id)}")

                if command_list:
                    embed.add_field(
                        name=cog_name,
                        value="\n".join(command_list),
                        inline=False
                    )

        embed.set_footer(text=t('help_footer', guild_id=guild_id, prefix=self.context.prefix))

        channel = self.get_destination()
        await channel.send(embed=embed)

    async def send_command_help(self, command):
        """Отправляет справку по конкретной команде"""
        # Проверяем права пользователя
        ctx = self.context
        guild_id = ctx.guild.id

        # Проверка на администратора
        if not ctx.author.guild_permissions.administrator:
            # Проверка на whitelist
            db = ctx.bot.db
            if not db.is_whitelisted(ctx.guild.id, ctx.author.id):
                # Если нет прав - игнорируем команду (не отвечаем)
                return

        # Удаляем сообщение пользователя
        await ctx.message.delete()

        embed = discord.Embed(
            title=t('help_command_title', guild_id=guild_id, prefix=self.context.prefix, command=command.name),
            description=command.help or t('help_no_description', guild_id=guild_id),
            color=discord.Color.blue()
        )

        if command.aliases:
            embed.add_field(
                name=t('help_aliases', guild_id=guild_id),
                value=", ".join(f"`{alias}`" for alias in command.aliases),
                inline=False
            )

        # Показываем использование команды
        usage = f"{self.context.prefix}{command.name}"
        if command.signature:
            usage += f" {command.signature}"

        embed.add_field(
            name=t('help_usage', guild_id=guild_id),
            value=f"`{usage}`",
            inline=False
        )

        channel = self.get_destination()
        await channel.send(embed=embed)

    async def send_error_message(self, error):
        """Отправляет сообщение об ошибке"""
        # Note: We can't easily get guild_id here since error might not have context
        embed = discord.Embed(
            title=t('help_error_title'),
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
