from discord.ext import commands

def is_admin_or_whitelisted():
    """
    Декоратор для проверки прав: администратор или в whitelist
    """
    async def predicate(ctx):
        # Проверка на администратора
        if ctx.author.guild_permissions.administrator:
            return True

        # Получаем db из бота
        db = ctx.bot.db

        # Проверка на whitelist
        if db.is_whitelisted(ctx.guild.id, ctx.author.id):
            return True

        # Если ни то, ни другое
        print("no rights")
        await ctx.send("❌ У вас нет прав для использования этой команды!")
        return False

    return commands.check(predicate)
