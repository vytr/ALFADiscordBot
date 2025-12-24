import discord
from discord.ext import commands
import asyncio
import config
from database import Database
import traceback

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
        cogs_to_load = [
            'cogs.help',
            'cogs.basic',
            'cogs.whitelist',
            'cogs.stats',
            'cogs.panel',
            'cogs.polls_extension',
            'cogs.drink_game'
        ]
        
        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                print(f'✅ Загружен: {cog}')
            except Exception as e:
                print(f'❌ Ошибка загрузки {cog}:')
                print(f'   {type(e).__name__}: {e}')
                traceback.print_exc()

        print("\n🎉 Все расширения загружены\n")

    async def on_ready(self):
        """Вызывается когда бот успешно подключился к Discord"""
        print(f'🤖 Бот {self.user} успешно запущен!')
        print(f'📌 ID: {self.user.id}')
        print('━━━━━━━━━━━━━━━━━━━━━━━━━━')
        
        # Синхронизация команд
        try:
            print("⏳ Синхронизация slash команд...")
            synced = await self.tree.sync()
            print(f"✅ Синхронизировано {len(synced)} команд:")
            for cmd in synced:
                print(f"   • /{cmd.name}")
            print('━━━━━━━━━━━━━━━━━━━━━━━━━━')
        except Exception as e:
            print(f"❌ Ошибка синхронизации команд: {e}")
            traceback.print_exc()
        
        # Установка статуса
        await self.change_presence(
            activity=discord.Game(name=f"{config.DISCORD_PREFIX}help | /panel")
        )
        print("✅ Бот готов к работе!\n")

async def main():
    bot = DiscordBot()
    async with bot:
        await bot.start(config.DISCORD_TOKEN)

if __name__ == '__main__':
    asyncio.run(main())