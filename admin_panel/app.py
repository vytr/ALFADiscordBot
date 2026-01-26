import streamlit as st
import requests
from urllib.parse import urlencode
import os
from dotenv import load_dotenv

load_dotenv()

# Конфигурация
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "YOUR_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("ADMIN_PANEL_REDIRECT_URI", "http://localhost:8502")
BOT_API_URL = "http://localhost:5555/api"

st.set_page_config(
    page_title="GuildBrew Admin Panel",
    page_icon="🎛️",
    layout="wide"
)

# ==================== DISCORD OAUTH ====================

def get_discord_auth_url():
    """Генерирует URL для авторизации через Discord"""
    params = {
        'client_id': DISCORD_CLIENT_ID,
        'redirect_uri': DISCORD_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'identify guilds'
    }
    return f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"


def exchange_code(code):
    """Обменивает код на access token"""
    data = {
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': DISCORD_REDIRECT_URI
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    response = requests.post('https://discord.com/api/oauth2/token', data=data, headers=headers)
    return response.json()


def get_user_info(access_token):
    """Получает информацию о пользователе"""
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get('https://discord.com/api/users/@me', headers=headers)
    return response.json()


def get_admin_guilds(access_token):
    """Получает серверы где пользователь является администратором"""
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(f"{BOT_API_URL}/admin/guilds", headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            return data.get('guilds', [])
        return []
    except Exception as e:
        st.error(f"Ошибка получения серверов: {e}")
        return []


def get_guild_settings(guild_id):
    """Получает настройки сервера"""
    try:
        response = requests.get(f"{BOT_API_URL}/admin/guild/{guild_id}/settings", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        st.error(f"Ошибка получения настроек: {e}")
        return None


def update_guild_settings(guild_id, access_token, settings):
    """Обновляет настройки сервера"""
    try:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        response = requests.put(
            f"{BOT_API_URL}/admin/guild/{guild_id}/settings",
            headers=headers,
            json=settings,
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Ошибка обновления настроек: {e}")
        return False


def reset_guild_settings(guild_id, access_token):
    """Сбрасывает настройки сервера к дефолтным"""
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.delete(
            f"{BOT_API_URL}/admin/guild/{guild_id}/settings",
            headers=headers,
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Ошибка сброса настроек: {e}")
        return False


# ==================== ИНИЦИАЛИЗАЦИЯ SESSION STATE ====================

if 'user' not in st.session_state:
    st.session_state.user = None
if 'access_token' not in st.session_state:
    st.session_state.access_token = None

# ==================== ОБРАБОТКА OAUTH CALLBACK ====================

query_params = st.query_params
if 'code' in query_params and st.session_state.user is None:
    code = query_params['code']

    try:
        token_data = exchange_code(code)

        if 'access_token' in token_data:
            st.session_state.access_token = token_data['access_token']
            user_info = get_user_info(token_data['access_token'])
            st.session_state.user = user_info

            st.query_params.clear()
            st.rerun()
        else:
            st.error("Ошибка авторизации")
    except Exception as e:
        st.error(f"Ошибка: {str(e)}")

# ==================== СТРАНИЦА ЛОГИНА ====================

if st.session_state.user is None:
    st.title("🎛️ GuildBrew Admin Panel")
    st.markdown("### Панель администратора для настройки бота")

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("""
        <div style="text-align: center; margin: 50px 0;">
            <p style="font-size: 18px; color: #666;">
                Войдите через Discord для доступа к настройкам бота.<br>
                <strong>Доступ только для администраторов серверов.</strong>
            </p>
        </div>
        """, unsafe_allow_html=True)

        auth_url = get_discord_auth_url()

        st.markdown(f"""
        <div style="text-align: center;">
            <a href="{auth_url}" target="_self">
                <button style="
                    background-color: #5865F2;
                    color: white;
                    padding: 15px 40px;
                    font-size: 18px;
                    border: none;
                    border-radius: 8px;
                    cursor: pointer;
                    font-weight: bold;
                ">
                    🔐 Войти через Discord
                </button>
            </a>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="text-align: center; margin-top: 30px; color: #888; font-size: 14px;">
            <p>🔒 Безопасная авторизация через OAuth 2.0</p>
            <p>👑 Требуются права администратора на сервере</p>
        </div>
        """, unsafe_allow_html=True)

    st.stop()

# ==================== ГЛАВНАЯ СТРАНИЦА ====================

# Получаем серверы где пользователь админ
admin_guilds = get_admin_guilds(st.session_state.access_token)

if not admin_guilds:
    st.error("❌ У вас нет доступа к Admin Panel")
    st.info("Вы должны быть администратором хотя бы на одном сервере где присутствует бот")

    if st.button("🚪 Выйти"):
        st.session_state.user = None
        st.session_state.access_token = None
        st.rerun()

    st.stop()

# ==================== SIDEBAR ====================

st.sidebar.title("🎛️ Admin Panel")

# Выбор сервера
guild = st.sidebar.selectbox(
    "🏰 Выберите сервер",
    admin_guilds,
    format_func=lambda x: f"{x['name']} ({x['member_count']} участников)"
)

guild_id = guild['id']

st.sidebar.markdown("---")

# Информация о сервере
st.sidebar.markdown(f"**Сервер:** {guild['name']}")
st.sidebar.markdown(f"**ID:** {guild_id}")
if guild.get('icon'):
    st.sidebar.image(guild['icon'], width=100)

st.sidebar.markdown("---")

# Информация о пользователе
st.sidebar.markdown("### 👤 Профиль")
user_avatar = f"https://cdn.discordapp.com/avatars/{st.session_state.user['id']}/{st.session_state.user['avatar']}.png" if st.session_state.user.get('avatar') else 'https://cdn.discordapp.com/embed/avatars/0.png'

st.sidebar.markdown(f"""
<div style="text-align: center; padding: 10px;">
    <img src="{user_avatar}" width="64" style="border-radius: 50%; margin-bottom: 10px;">
    <br>
    <strong>{st.session_state.user['username']}</strong>
    <br>
    <span style="color: #43b581;">👑 Администратор</span>
</div>
""", unsafe_allow_html=True)

if st.sidebar.button("🚪 Выйти", use_container_width=True, type="primary"):
    st.session_state.user = None
    st.session_state.access_token = None
    st.rerun()

# ==================== ОСНОВНОЙ КОНТЕНТ ====================

st.title(f"⚙️ Настройки: {guild['name']}")

# Загружаем текущие настройки
settings = get_guild_settings(guild_id)

if not settings:
    st.error("Не удалось загрузить настройки сервера")
    st.stop()

# ==================== ТАБЫ ====================

tab1, tab2, tab3 = st.tabs(["🎨 Брендинг", "📝 Тексты", "👁️ Превью"])

# ==================== ТАБ 1: БРЕНДИНГ ====================

with tab1:
    st.header("🎨 Настройки брендинга")

    col1, col2 = st.columns(2)

    with col1:
        bot_name = st.text_input(
            "Название бота",
            value=settings.get('bot_name', 'GuildBrew'),
            max_chars=32,
            help="Отображается в заголовках панели и dashboard"
        )

        primary_color = st.color_picker(
            "Primary Color",
            value=settings.get('primary_color', '#5865F2'),
            help="Основной цвет (используется в заголовках)"
        )

        secondary_color = st.color_picker(
            "Secondary Color",
            value=settings.get('secondary_color', '#2ECC71'),
            help="Вторичный цвет (используется для акцентов)"
        )

    with col2:
        logo_url = st.text_input(
            "URL логотипа",
            value=settings.get('logo_url') or '',
            help="Ссылка на изображение логотипа (PNG/JPG)"
        )

        if logo_url:
            st.markdown("**Превью логотипа:**")
            try:
                st.image(logo_url, width=128)
            except:
                st.warning("Не удалось загрузить изображение")

# ==================== ТАБ 2: ТЕКСТЫ ====================

with tab2:
    st.header("📝 Настройки текстов")

    panel_title = st.text_input(
        "Заголовок панели",
        value=settings.get('panel_title', 'GuildBrew Control Panel'),
        max_chars=64,
        help="Заголовок в Discord панели (/panel)"
    )

    welcome_message = st.text_area(
        "Приветственное сообщение",
        value=settings.get('welcome_message', 'Добро пожаловать в панель управления!\nВыберите нужный раздел, нажав на кнопку ниже.'),
        height=100,
        help="Текст под заголовком панели"
    )

    footer_text = st.text_input(
        "Текст footer",
        value=settings.get('footer_text', 'GuildBrew • Панель управления'),
        max_chars=64,
        help="Текст в нижней части embed'ов"
    )

# ==================== ТАБ 3: ПРЕВЬЮ ====================

with tab3:
    st.header("👁️ Превью панели Discord")

    st.markdown("""
    <style>
    .discord-embed {
        background-color: #2f3136;
        border-radius: 4px;
        padding: 16px;
        margin: 16px 0;
        border-left: 4px solid;
        max-width: 520px;
    }
    .embed-title {
        color: white;
        font-weight: bold;
        font-size: 16px;
        margin-bottom: 8px;
    }
    .embed-description {
        color: #dcddde;
        font-size: 14px;
        white-space: pre-line;
    }
    .embed-footer {
        color: #72767d;
        font-size: 12px;
        margin-top: 12px;
        padding-top: 8px;
        border-top: 1px solid #40444b;
    }
    </style>
    """, unsafe_allow_html=True)

    preview_title = panel_title if panel_title else 'GuildBrew Control Panel'
    preview_welcome = welcome_message if welcome_message else 'Добро пожаловать!'
    preview_footer = footer_text if footer_text else 'GuildBrew'
    preview_color = primary_color if primary_color else '#5865F2'

    st.markdown(f"""
    <div class="discord-embed" style="border-left-color: {preview_color};">
        <div class="embed-title">🎛️ {preview_title}</div>
        <div class="embed-description">{preview_welcome}</div>
        <div class="embed-footer">{preview_footer}</div>
    </div>
    """, unsafe_allow_html=True)

    st.info("Так будет выглядеть панель управления в Discord при использовании команды `/panel`")

# ==================== КНОПКИ ДЕЙСТВИЙ ====================

st.markdown("---")

col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    if st.button("💾 Сохранить настройки", type="primary", use_container_width=True):
        new_settings = {
            'bot_name': bot_name,
            'primary_color': primary_color,
            'secondary_color': secondary_color,
            'panel_title': panel_title,
            'welcome_message': welcome_message,
            'logo_url': logo_url if logo_url else None,
            'footer_text': footer_text
        }

        if update_guild_settings(guild_id, st.session_state.access_token, new_settings):
            st.success("✅ Настройки сохранены!")
            st.balloons()
        else:
            st.error("❌ Ошибка сохранения настроек")

with col2:
    if st.button("🔄 Обновить", use_container_width=True):
        st.rerun()

with col3:
    if st.button("🗑️ Сбросить", use_container_width=True):
        if reset_guild_settings(guild_id, st.session_state.access_token):
            st.success("✅ Настройки сброшены к дефолтным")
            st.rerun()
        else:
            st.error("❌ Ошибка сброса настроек")

# ==================== FOOTER ====================

st.markdown("---")
st.markdown("**GuildBrew Admin Panel** • Настройки применяются мгновенно")
