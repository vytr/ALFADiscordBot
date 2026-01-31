import discord
from discord.ext import commands
from datetime import datetime
from utils import t

class Whitelist(commands.Cog):
    """Команды для управления whitelist"""

    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    @commands.command(name='gb_whitelist_add')
    @commands.has_permissions(administrator=True)
    async def whitelist_add(self, ctx, member: discord.Member):
        """Добавить пользователя в whitelist (только для администраторов)"""
        await ctx.message.delete()
        guild_id = ctx.guild.id
        if self.db.add_to_whitelist(guild_id, member.id, ctx.author.id):
            embed = discord.Embed(
                title="✅ Whitelist",
                description=t('whitelist_added', guild_id=guild_id, user=member.mention),
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(t('whitelist_add_error', guild_id=guild_id))

    @commands.command(name='gb_whitelist_remove')
    @commands.has_permissions(administrator=True)
    async def whitelist_remove(self, ctx, member: discord.Member):
        """Удалить пользователя из whitelist (только для администраторов)"""
        await ctx.message.delete()
        guild_id = ctx.guild.id
        if self.db.remove_from_whitelist(guild_id, member.id):
            embed = discord.Embed(
                title="✅ Whitelist",
                description=t('whitelist_removed', guild_id=guild_id, user=member.mention),
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(t('whitelist_remove_error', guild_id=guild_id))

    @commands.command(name='gb_whitelist_list')
    @commands.has_permissions(administrator=True)
    async def whitelist_list(self, ctx):
        """Показать список пользователей в whitelist (только для администраторов)"""
        await ctx.message.delete()
        guild_id = ctx.guild.id
        whitelist = self.db.get_whitelist(guild_id)

        if not whitelist:
            await ctx.send(t('whitelist_empty', guild_id=guild_id))
            return

        embed = discord.Embed(
            title=t('whitelist_title', guild_id=guild_id),
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        for user_id, added_by, added_at in whitelist:
            member = ctx.guild.get_member(user_id)
            if member:
                embed.add_field(
                    name=f"{member.name}",
                    value=f"ID: {user_id}\n{t('whitelist_added_at', guild_id=guild_id, date=added_at)}",
                    inline=False
                )

        await ctx.send(embed=embed)

    @whitelist_add.error
    @whitelist_remove.error
    @whitelist_list.error
    async def whitelist_error(self, ctx, error):
        """Обработка ошибок команд whitelist"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(t('whitelist_no_permission', guild_id=ctx.guild.id))

async def setup(bot):
    db = bot.db  # Получаем объект базы данных из бота
    await bot.add_cog(Whitelist(bot, db))
