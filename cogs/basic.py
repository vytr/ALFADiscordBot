import discord
from discord.ext import commands
from datetime import datetime

class Basic(commands.Cog):
    """Базовые команды для бота"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='ping')
    async def ping(self, ctx):
        """Проверка задержки бота"""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f'🏓 Понг! Задержка: {latency}ms')

    @commands.command(name='info')
    async def info(self, ctx):
        """Информация о боте"""
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

    @commands.command(name='hello')
    async def hello(self, ctx):
        """Поздороваться с ботом"""
        await ctx.send(f'Привет, {ctx.author.mention}! 👋')

    @commands.command(name='say')
    async def say(self, ctx, *, message: str):
        """Заставить бота повторить сообщение"""
        await ctx.message.delete()
        await ctx.send(message)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Приветствие новых участников"""
        channel = member.guild.system_channel
        if channel is not None:
            embed = discord.Embed(
                description=f'Добро пожаловать на сервер, {member.mention}!',
                color=discord.Color.green()
            )
            await channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Basic(bot))
