import discord
from discord.ext import commands
from datetime import datetime
from utils import is_admin_or_whitelisted
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
        await ctx.send(f'🏓 Понг! Задержка: {latency}ms')

    @commands.command(name='gb_info')
    @is_admin_or_whitelisted()
    async def info(self, ctx):
        """Информация о боте"""
        await ctx.message.delete()
        embed = discord.Embed(
            title="Информация о боте",
            description="Discord бот на Python",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="Серверов", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="Пользователей", value=len(self.bot.users), inline=True)
        embed.add_field(name="Версия Discord.py", value=discord.__version__, inline=True)

        embed.set_footer(text=f"Запрошено {ctx.author}", icon_url=ctx.author.display_avatar.url)

        await ctx.send(embed=embed)

    @commands.command(name='gb_hello')
    @is_admin_or_whitelisted()
    async def hello(self, ctx):
        """Поздороваться с ботом"""
        await ctx.message.delete()
        await ctx.send(f'Привет, {ctx.author.mention}! 👋')

    @commands.command(name='gb_say')
    @is_admin_or_whitelisted()
    async def say(self, ctx, *, message: str):
        print("say call")
        """Заставить бота повторить сообщение"""
        await ctx.message.delete()
        await ctx.send(message)

    @commands.command(name='gb_duel')
    async def duel(self,ctx, opponent: discord.Member):
        if opponent == ctx.author:
            await ctx.send("Вы не можете драться сами с собой!")
            return

        await ctx.send(f"{ctx.author.mention} вызывает {opponent.mention} на дуэль!")

        # Генерируем случайные силы для обоих участников
        player1_power = random.randint(1, 100)
        player2_power = random.randint(1, 100)

        await ctx.send(f"Сила {ctx.author.mention}: {player1_power}")
        await ctx.send(f"Сила {opponent.mention}: {player2_power}")

        # Определяем победителя
        if player1_power > player2_power:
            await ctx.send(f"{ctx.author.mention} выигрывает дуэль!")
        elif player1_power < player2_power:
            await ctx.send(f"{opponent.mention} выигрывает дуэль!")
        else:
            await ctx.send("Дуэль окончилась вничью!")
async def setup(bot):
    await bot.add_cog(Basic(bot))
