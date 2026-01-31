import discord
from discord.ext import commands
from datetime import datetime
from utils import is_admin_or_whitelisted, t, get_guild_locale, set_guild_locale, get_available_locales, AVAILABLE_LOCALES
import io
import random

class Basic(commands.Cog):
    """Базовые команды для бота"""

    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.command(name='gb_ping')
    @is_admin_or_whitelisted()
    async def ping(self, ctx):
        """Проверка задержки бота"""
        print("ping call")
        await ctx.message.delete()
        latency = round(self.bot.latency * 1000)
        await ctx.send(t('pong_latency', guild_id=ctx.guild.id, latency=latency))

    @commands.command(name='gb_info')
    @is_admin_or_whitelisted()
    async def info(self, ctx):
        """Информация о боте"""
        await ctx.message.delete()
        guild_id = ctx.guild.id
        embed = discord.Embed(
            title=t('bot_info_title', guild_id=guild_id),
            description=t('bot_info_description', guild_id=guild_id),
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name=t('servers', guild_id=guild_id), value=len(self.bot.guilds), inline=True)
        embed.add_field(name=t('users', guild_id=guild_id), value=len(self.bot.users), inline=True)
        embed.add_field(name=t('discordpy_version', guild_id=guild_id), value=discord.__version__, inline=True)

        embed.set_footer(text=t('requested_by', guild_id=guild_id, user=ctx.author), icon_url=ctx.author.display_avatar.url)

        await ctx.send(embed=embed)

    @commands.command(name='gb_hello')
    @is_admin_or_whitelisted()
    async def hello(self, ctx):
        """Поздороваться с ботом"""
        await ctx.message.delete()
        await ctx.send(t('hello_message', guild_id=ctx.guild.id, user=ctx.author.mention))

    @commands.command(name='gb_say')
    @is_admin_or_whitelisted()
    async def say(self, ctx, *, message: str):
        print("say call")
        """Заставить бота повторить сообщение"""
        await ctx.message.delete()
        await ctx.send(message)

    @commands.command(name='gb_duel')
    async def duel(self, ctx, opponent: discord.Member):
        guild_id = ctx.guild.id
        if opponent == ctx.author:
            await ctx.send(t('duel_self_error', guild_id=guild_id))
            return

        await ctx.send(t('duel_challenge', guild_id=guild_id, challenger=ctx.author.mention, opponent=opponent.mention))

        # Генерируем случайные силы для обоих участников
        player1_power = random.randint(1, 100)
        player2_power = random.randint(1, 100)

        await ctx.send(t('duel_power', guild_id=guild_id, user=ctx.author.mention, power=player1_power))
        await ctx.send(t('duel_power', guild_id=guild_id, user=opponent.mention, power=player2_power))

        # Определяем победителя
        if player1_power > player2_power:
            await ctx.send(t('duel_winner', guild_id=guild_id, winner=ctx.author.mention))
        elif player1_power < player2_power:
            await ctx.send(t('duel_winner', guild_id=guild_id, winner=opponent.mention))
        else:
            await ctx.send(t('duel_draw', guild_id=guild_id))

    @commands.command(name='gb_language')
    @commands.has_permissions(administrator=True)
    async def set_language(self, ctx, locale: str = None):
        """Изменить язык бота для этого сервера. Формат: !gb_language <код>"""
        guild_id = ctx.guild.id
        current_locale = get_guild_locale(guild_id)
        available = get_available_locales()

        # Если язык не указан - показываем текущий и доступные
        if locale is None:
            embed = discord.Embed(
                title=t('language_title', guild_id=guild_id),
                description=t('language_current', guild_id=guild_id, language=available.get(current_locale, current_locale)),
                color=discord.Color.blue()
            )

            available_list = "\n".join([f"`{code}` — {name}" for code, name in available.items()])
            embed.add_field(
                name=t('language_available', guild_id=guild_id),
                value=available_list,
                inline=False
            )
            embed.set_footer(text=t('language_usage', guild_id=guild_id))

            await ctx.send(embed=embed)
            return

        # Проверяем валидность языка
        locale = locale.lower()
        if locale not in available:
            available_str = ", ".join([f"`{code}`" for code in available.keys()])
            await ctx.send(t('language_invalid', guild_id=guild_id, locale=locale, available=available_str))
            return

        # Устанавливаем новый язык
        if set_guild_locale(guild_id, locale):
            # Отвечаем уже на новом языке
            await ctx.send(t('language_changed', guild_id=guild_id, language=available.get(locale, locale)))
        else:
            await ctx.send("❌ Error setting language")

async def setup(bot):
    await bot.add_cog(Basic(bot))
