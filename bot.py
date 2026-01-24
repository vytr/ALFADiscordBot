import discord
from discord.ext import commands
import asyncio
import config
from database import Database
import traceback
from flask import Flask, jsonify
import threading
from datetime import datetime

# Глобальные переменные для статистики
bot_start_time = datetime.now()
command_count = 0

# Flask приложение для API
flask_app = Flask(__name__)

@flask_app.route('/stats')
def stats():
    try:
        uptime = str(datetime.now() - bot_start_time).split('.')[0]
        
        # Используем глобальную переменную bot_instance
        stats_data = {
            'status': 'online' if bot_instance and bot_instance.is_ready() else 'starting',
            'uptime': uptime,
            'servers': len(bot_instance.guilds) if bot_instance and bot_instance.is_ready() else 0,
            'users': sum(guild.member_count for guild in bot_instance.guilds) if bot_instance and bot_instance.is_ready() else 0,
            'latency': round(bot_instance.latency * 1000, 2) if bot_instance and bot_instance.is_ready() else 0,
            'commands': command_count
        }
        
        return jsonify(stats_data)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def run_flask():
    flask_app.run(host='0.0.0.0', port=5555, debug=False, use_reloader=False)
# ===== КОНЕЦ ДОБАВЛЕНИЯ =====

class DiscordBot(commands.Bot):
    def __init__(self):
        # ВАЖНО: Для отслеживания опросов нужны эти intents!
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True           # ← КРИТИЧНО для poll events
        intents.guild_messages = True   # ← КРИТИЧНО для poll events

        super().__init__(
            command_prefix=config.DISCORD_PREFIX,
            intents=intents,
            help_command=None
        )

        # Инициализация базы данных (теперь с отдельной БД для опросов)
        self.db = Database()

    async def setup_hook(self):
        """Загрузка расширений (cogs) при запуске бота"""
        cogs_to_load = [
            'cogs.help',
            'cogs.basic',
            'cogs.whitelist',
            'cogs.stats',
            'cogs.panel',
            'cogs.drink_game',
            'cogs.warnings',
            'cogs.native_polls', 
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
        global bot_start_time
        if bot_start_time is None:
            bot_start_time = datetime.now()

        """Вызывается когда бот успешно подключился к Discord"""
        print(f'🤖 Бот {self.user} успешно запущен!')
        print(f'📌 ID: {self.user.id}')
        print('━━━━━━━━━━━━━━━━━━━━━━━━━━')
        
        # Проверка intents
        print("🔍 Проверка intents:")
        print(f"   guilds: {self.intents.guilds}")
        print(f"   guild_messages: {self.intents.guild_messages}")
        print(f"   message_content: {self.intents.message_content}")
        print(f"   members: {self.intents.members}")
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
        print("✅ Бот готов к работе!")
        print("📊 Отслеживание опросов активно!\n")

    async def on_command(self, ctx):
        """Отслеживание выполненных команд"""
        global command_count
        command_count += 1

bot_instance = None

async def main():
    global bot_instance
    
    bot = DiscordBot()
    bot_instance = bot  # Сохраняем в глобальную переменную
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    async with bot:
        await bot.start(config.DISCORD_TOKEN)

if __name__ == '__main__':
    asyncio.run(main())