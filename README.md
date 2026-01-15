# Discord Bot на Python

Простой Discord бот, созданный с использованием discord.py.

## Возможности

- Базовые команды (ping, info, hello, say)
- Модульная структура с использованием Cogs
- Приветствие новых участников
- Легко расширяемый

## Установка

### 1. Создание бота в Discord Developer Portal

1. Перейдите на [Discord Developer Portal](https://discord.com/developers/applications)
2. Нажмите "New Application" и дайте боту имя
3. Перейдите в раздел "Bot" в левом меню
4. Нажмите "Add Bot"
5. Скопируйте токен бота (понадобится позже)
6. Включите "Message Content Intent" в разделе "Privileged Gateway Intents"

### 2. Приглашение бота на сервер

1. В Developer Portal перейдите в раздел "OAuth2" → "URL Generator"
2. Выберите scope: `bot`
3. Выберите необходимые права (например: Send Messages, Read Messages, Embed Links)
4. Скопируйте сгенерированную ссылку и откройте её в браузере
5. Выберите сервер и пригласите бота

### 3. Настройка проекта

1. Установите Python 3.8 или новее

2. Создайте виртуальное окружение:
```bash
python -m venv venv
```

3. Активируйте виртуальное окружение:
```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

4. Установите зависимости:
```bash
pip install -r requirements.txt
```

5. Создайте файл `.env` на основе `.env.example`:
```bash
cp .env.example .env
```

6. Откройте `.env` и вставьте токен вашего бота:
```env
DISCORD_TOKEN=ваш_токен_здесь
DISCORD_PREFIX=!
```

## Запуск

```bash
python bot.py
```

Если всё настроено правильно, вы увидите сообщение:
```
Расширения загружены
Бот YourBotName успешно запущен!
ID: 123456789
------
```

## Использование

### Доступные команды

- `!ping` - Проверка задержки бота
- `!info` - Информация о боте
- `!hello` - Поздороваться с ботом
- `!say <сообщение>` - Заставить бота повторить сообщение
- `!help` - Показать список всех команд

## Структура проекта

```
.
├── bot.py              # Главный файл бота
├── config.py           # Конфигурация и загрузка переменных окружения
├── cogs/               # Модули с командами
│   ├── __init__.py
│   └── basic.py        # Базовые команды
├── requirements.txt    # Зависимости Python
├── .env.example        # Пример файла с переменными окружения
├── .gitignore         # Файлы для игнорирования в git
└── README.md          # Этот файл
```

## Добавление новых команд

Создайте новый файл в папке `cogs/`:

```python
import discord
from discord.ext import commands

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='mycommand')
    async def my_command(self, ctx):
        await ctx.send('Моя команда работает!')

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

Затем загрузите его в [bot.py](bot.py):
```python
await self.load_extension('cogs.mycog')
```

## Полезные ссылки

- [discord.py документация](https://discordpy.readthedocs.io/)
- [Discord Developer Portal](https://discord.com/developers/applications)
- [discord.py GitHub](https://github.com/Rapptz/discord.py)

## Лицензия

MIT
