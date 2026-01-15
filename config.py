import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_PREFIX = os.getenv('DISCORD_PREFIX', '!')

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN не установлен в файле .env")
