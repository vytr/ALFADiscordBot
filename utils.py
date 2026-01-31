from discord.ext import commands
import json
import os
import sqlite3

# Кэш локализаций: {'ru': {...}, 'en': {...}}
_locales_cache = {}

# Кэш языков серверов: {guild_id: 'ru', ...}
_guild_locales_cache = {}

# Язык по умолчанию
DEFAULT_LOCALE = 'ru'

# Доступные языки
AVAILABLE_LOCALES = {
    'ru': 'Русский 🇷🇺',
    'en': 'English 🇬🇧'
}

def _get_db_path():
    """Получить путь к БД"""
    return os.path.join(os.path.dirname(__file__), 'bot_database.db')

def _init_locale_table():
    """Создать таблицу для языков серверов"""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS guild_locales (
            guild_id INTEGER PRIMARY KEY,
            locale TEXT NOT NULL DEFAULT 'ru'
        )
    ''')

    conn.commit()
    conn.close()

def _load_locale_file(locale: str) -> dict:
    """Загрузить файл локализации в кэш"""
    if locale in _locales_cache:
        return _locales_cache[locale]

    locale_path = os.path.join(os.path.dirname(__file__), 'locales', f'{locale}.json')

    try:
        with open(locale_path, 'r', encoding='utf-8') as f:
            _locales_cache[locale] = json.load(f)
        print(f"✅ Loaded locale: {locale}")
        return _locales_cache[locale]
    except FileNotFoundError:
        print(f"⚠️ Locale file not found: {locale_path}")
        return {}
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing locale file: {e}")
        return {}

def get_guild_locale(guild_id: int) -> str:
    """Получить язык сервера"""
    # Проверяем кэш
    if guild_id in _guild_locales_cache:
        return _guild_locales_cache[guild_id]

    # Загружаем из БД
    try:
        conn = sqlite3.connect(_get_db_path())
        cursor = conn.cursor()

        cursor.execute('SELECT locale FROM guild_locales WHERE guild_id = ?', (guild_id,))
        result = cursor.fetchone()
        conn.close()

        locale = result[0] if result else DEFAULT_LOCALE
        _guild_locales_cache[guild_id] = locale
        return locale
    except:
        return DEFAULT_LOCALE

def set_guild_locale(guild_id: int, locale: str) -> bool:
    """Установить язык для сервера"""
    if locale not in AVAILABLE_LOCALES:
        return False

    try:
        conn = sqlite3.connect(_get_db_path())
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO guild_locales (guild_id, locale)
            VALUES (?, ?)
        ''', (guild_id, locale))

        conn.commit()
        conn.close()

        # Обновляем кэш
        _guild_locales_cache[guild_id] = locale

        # Загружаем локаль если ещё не загружена
        _load_locale_file(locale)

        return True
    except Exception as e:
        print(f"Error setting guild locale: {e}")
        return False

def t(key: str, guild_id: int = None, **kwargs) -> str:
    """
    Получить переведенную строку по ключу.

    Использование:
        t('hello_message', guild_id=ctx.guild.id, user='@User')
        t('stats_period_days', guild_id=123456, days=7)

    Если guild_id не указан, используется язык по умолчанию.
    """
    # Определяем язык
    locale = get_guild_locale(guild_id) if guild_id else DEFAULT_LOCALE

    # Получаем строки для этого языка
    strings = _load_locale_file(locale)

    # Если ключ не найден - пробуем язык по умолчанию
    if key not in strings:
        strings = _load_locale_file(DEFAULT_LOCALE)

    if key not in strings:
        # Возвращаем ключ если перевод не найден
        return key

    text = strings[key]

    # Если это список (например, drink_comments), возвращаем как есть
    if isinstance(text, list):
        return text

    # Форматируем строку с переданными параметрами
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError as e:
            print(f"⚠️ Missing format key {e} in string '{key}'")
            return text

    return text

def get_available_locales() -> dict:
    """Получить список доступных языков"""
    return AVAILABLE_LOCALES

# Инициализация при импорте
_init_locale_table()
_load_locale_file(DEFAULT_LOCALE)


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
        await ctx.send(t('no_permission', guild_id=ctx.guild.id))
        return False

    return commands.check(predicate)
