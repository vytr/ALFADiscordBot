import discord
from discord.ext import commands
import asyncio
import config
from database import Database

class DiscordBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix=config.DISCORD_PREFIX,
            intents=intents,
            help_command=None  # Отключаем стандартную help команду
        )

        # Инициализация базы данных
        self.db = Database()

    async def setup_hook(self):
        """Загрузка расширений (cogs) при запуске бота"""
        await self.load_extension('cogs.help')
        await self.load_extension('cogs.basic')
        await self.load_extension('cogs.whitelist')
        await self.load_extension('cogs.stats')
        await self.load_extension("cogs.panel")
        print("Расширения загружены")

    async def on_ready(self):
        """Вызывается когда бот успешно подключился к Discord"""
        print(f'Бот {self.user} успешно запущен!')
        print(f'ID: {self.user.id}')
        print('------')
        await self.tree.sync()
        await self.change_presence(
            activity=discord.Game(name=f"{config.DISCORD_PREFIX}help")
        )

async def main():
    bot = DiscordBot()
    async with bot:
        await bot.start(config.DISCORD_TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
