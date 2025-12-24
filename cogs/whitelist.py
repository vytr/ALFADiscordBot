import discord
from discord.ext import commands
from datetime import datetime

class Whitelist(commands.Cog):
    """Команды для управления whitelist"""

    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    @commands.command(name='whitelist_add')
    @commands.has_permissions(administrator=True)
    async def whitelist_add(self, ctx, member: discord.Member):
        """Добавить пользователя в whitelist (только для администраторов)"""
        await ctx.message.delete()
        if self.db.add_to_whitelist(ctx.guild.id, member.id, ctx.author.id):
            embed = discord.Embed(
                title="✅ Whitelist",
                description=f"{member.mention} добавлен в whitelist",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Ошибка при добавлении в whitelist")

    @commands.command(name='whitelist_remove')
    @commands.has_permissions(administrator=True)
    async def whitelist_remove(self, ctx, member: discord.Member):
        """Удалить пользователя из whitelist (только для администраторов)"""
        await ctx.message.delete()
        if self.db.remove_from_whitelist(ctx.guild.id, member.id):
            embed = discord.Embed(
                title="✅ Whitelist",
                description=f"{member.mention} удален из whitelist",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Ошибка при удалении из whitelist")

    @commands.command(name='whitelist_list')
    @commands.has_permissions(administrator=True)
    async def whitelist_list(self, ctx):
        """Показать список пользователей в whitelist (только для администраторов)"""
        await ctx.message.delete()
        whitelist = self.db.get_whitelist(ctx.guild.id)

        if not whitelist:
            await ctx.send("📋 Whitelist пуст")
            return

        embed = discord.Embed(
            title="📋 Whitelist",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        for user_id, added_by, added_at in whitelist:
            member = ctx.guild.get_member(user_id)
            if member:
                embed.add_field(
                    name=f"{member.name}",
                    value=f"ID: {user_id}\nДобавлен: {added_at}",
                    inline=False
                )

        await ctx.send(embed=embed)

    @whitelist_add.error
    @whitelist_remove.error
    @whitelist_list.error
    async def whitelist_error(self, ctx, error):
        """Обработка ошибок команд whitelist"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ У вас нет прав администратора для использования этой команды!")

async def setup(bot):
    db = bot.db  # Получаем объект базы данных из бота
    await bot.add_cog(Whitelist(bot, db))
