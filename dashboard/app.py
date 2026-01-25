import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from urllib.parse import urlencode
import os

# Конфигурация Discord OAuth
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "YOUR_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8501")
BOT_API_URL = "http://localhost:5555/api"

st.set_page_config(page_title="ALFA Bot Dashboard", page_icon="📊", layout="wide")

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

def get_user_whitelisted_guilds(user_id):
    """Получает серверы где пользователь в whitelist"""
    try:
        response = requests.get(f"{BOT_API_URL}/user/guilds/{user_id}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get('guilds', [])
        return []
    except:
        return []

# ==================== ПРОВЕРКА АВТОРИЗАЦИИ ====================

# Инициализация session_state
if 'user' not in st.session_state:
    st.session_state.user = None
if 'access_token' not in st.session_state:
    st.session_state.access_token = None

# Обработка OAuth callback
query_params = st.query_params
if 'code' in query_params and st.session_state.user is None:
    code = query_params['code']
    
    try:
        # Получаем токен
        token_data = exchange_code(code)
        
        if 'access_token' in token_data:
            st.session_state.access_token = token_data['access_token']
            
            # Получаем информацию о пользователе
            user_info = get_user_info(token_data['access_token'])
            st.session_state.user = user_info
            
            # Очищаем query params
            st.query_params.clear()
            st.rerun()
        else:
            st.error("❌ Ошибка авторизации")
    except Exception as e:
        st.error(f"❌ Ошибка: {str(e)}")

# ==================== СТРАНИЦА ЛОГИНА ====================

if st.session_state.user is None:
    st.title("🔐 ALFA Bot Dashboard")
    st.markdown("### Для доступа необходима авторизация через Discord")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<br>" * 3, unsafe_allow_html=True)
        
        st.info("""
        **Требования для доступа:**
        - Аккаунт Discord
        - Наличие в whitelist хотя бы на одном сервере с ALFA Bot
        """)
        
        auth_url = get_discord_auth_url()
        st.markdown(f"""
        <div style="text-align: center; margin-top: 30px;">
            <a href="{auth_url}" target="_self">
                <button style="
                    background-color: #5865F2;
                    color: white;
                    padding: 15px 40px;
                    font-size: 18px;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                    font-weight: bold;
                ">
                    🔗 Войти через Discord
                </button>
            </a>
        </div>
        """, unsafe_allow_html=True)
    
    st.stop()

# ==================== ГЛАВНАЯ СТРАНИЦА ====================

# Получаем серверы где пользователь в whitelist
user_id = st.session_state.user['id']
whitelisted_guilds = get_user_whitelisted_guilds(user_id)

# Проверяем доступ
if not whitelisted_guilds:
    st.error("❌ У вас нет доступа к dashboard")
    st.info("Вы должны быть добавлены в whitelist хотя бы на одном сервере")
    
    if st.button("🚪 Выйти"):
        st.session_state.user = None
        st.session_state.access_token = None
        st.rerun()
    
    st.stop()

# ==================== КЭШИРОВАНИЕ ДАННЫХ ====================

@st.cache_data(ttl=30)
def get_guild_members(guild_id):
    try:
        response = requests.get(f"{BOT_API_URL}/guild/{guild_id}/members", timeout=5)
        members = response.json()
        return {m['id']: m for m in members if not m.get('bot', False)}
    except:
        return {}

@st.cache_data(ttl=60)
def get_guild_stats(guild_id, days):
    try:
        response = requests.get(f"{BOT_API_URL}/guild/{guild_id}/stats/{days}", timeout=5)
        return response.json()
    except:
        return []

@st.cache_data(ttl=60)
def get_inactive_users(guild_id, days, activity_type='both'):
    try:
        response = requests.get(f"{BOT_API_URL}/guild/{guild_id}/inactive/{days}/{activity_type}", timeout=5)
        return response.json()
    except:
        return {'inactive_user_ids': [], 'total_members': 0, 'active_members': 0, 'inactive_members': 0}

@st.cache_data(ttl=60)
def get_warnings(guild_id):
    try:
        response = requests.get(f"{BOT_API_URL}/guild/{guild_id}/warnings", timeout=5)
        return response.json()
    except:
        return {'total_warnings': 0, 'active_warnings': 0, 'unique_users': 0, 'top_offenders': []}

@st.cache_data(ttl=300)
def get_guild_roles(guild_id):
    try:
        response = requests.get(f"{BOT_API_URL}/guild/{guild_id}/roles", timeout=5)
        return response.json()
    except:
        return []

def make_discord_link(user_id, members_cache):
    member = members_cache.get(user_id)
    if member:
        name = member['display_name']
        avatar = member.get('avatar') or 'https://cdn.discordapp.com/embed/avatars/0.png'
        return f'<img src="{avatar}" width="24" style="border-radius:50%; vertical-align:middle; margin-right:8px;"><a href="https://discord.com/users/{user_id}" target="_blank" style="text-decoration:none; color:#5865F2; font-weight:500;">{name}</a>'
    return f'<a href="https://discord.com/users/{user_id}" target="_blank" style="color:#5865F2;">User {user_id}</a>'

# ==================== HEADER ====================

st.title("📊 ALFA Bot Dashboard")

# ==================== ВЫБОР СЕРВЕРА ====================

guild = st.sidebar.selectbox(
    "🏰 Выберите сервер",
    whitelisted_guilds,
    format_func=lambda x: f"{x['name']} ({x['member_count']} участников)"
)

guild_id = guild['id']
members_cache = get_guild_members(guild_id)

# Информация о сервере
st.sidebar.markdown("---")
st.sidebar.markdown(f"**Сервер:** {guild['name']}")
st.sidebar.markdown(f"**Участников:** {guild['member_count']}")
if guild.get('icon'):
    st.sidebar.image(guild['icon'], width=100)

st.sidebar.markdown("---")

# Информация о пользователе и кнопка выхода
st.sidebar.markdown("### 👤 Профиль")
user_avatar = f"https://cdn.discordapp.com/avatars/{st.session_state.user['id']}/{st.session_state.user['avatar']}.png" if st.session_state.user.get('avatar') else 'https://cdn.discordapp.com/embed/avatars/0.png'
st.sidebar.markdown(f"""
<div style="text-align: center; padding: 10px;">
    <img src="{user_avatar}" width="64" style="border-radius: 50%; margin-bottom: 10px;">
    <br>
    <strong>{st.session_state.user['username']}</strong>
</div>
""", unsafe_allow_html=True)

if st.sidebar.button("🚪 Выйти", use_container_width=True, type="primary"):
    st.session_state.user = None
    st.session_state.access_token = None
    st.rerun()

# ==================== ТАБЫ ====================

tab1, tab2, tab3, tab4 = st.tabs(["📈 Статистика", "😴 Неактивные", "⚠️ Выговоры", "📊 Графики"])

# ==================== ТАБ 1: СТАТИСТИКА ====================
with tab1:
    st.header("📈 Статистика активности")
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        days = st.selectbox("📅 Период", [7, 14, 30], index=0, key="stats_days")
    
    stats = get_guild_stats(guild_id, days)
    
    if not stats:
        st.warning("Нет данных за выбранный период")
    else:
        df = pd.DataFrame(stats)
        
        # Метрики
        col1, col2, col3, col4 = st.columns(4)
        
        total_messages = df['period_messages'].sum()
        total_voice_hours = df['period_voice_time'].sum() / 3600
        active_users = len(df[df['period_messages'] > 0])
        avg_messages = df['period_messages'].mean()
        
        col1.metric("💬 Всего сообщений", f"{total_messages:,}")
        col2.metric("🎤 Всего часов в войсе", f"{total_voice_hours:.1f}")
        col3.metric("👥 Активных пользователей", active_users)
        col4.metric("📊 Среднее сообщений/юзер", f"{avg_messages:.0f}")
        
        st.markdown("---")
        
        # Топ по активности
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🏆 Топ-10 по сообщениям")
            top_messages = df.nlargest(10, 'period_messages').copy()
            top_messages['Пользователь'] = top_messages['user_id'].apply(
                lambda x: make_discord_link(x, members_cache)
            )
            top_messages['Сообщений'] = top_messages['period_messages']
            
            st.markdown(
                top_messages[['Пользователь', 'Сообщений']].to_html(escape=False, index=False),
                unsafe_allow_html=True
            )
        
        with col2:
            st.subheader("🎤 Топ-10 по времени в войсе")
            top_voice = df.nlargest(10, 'period_voice_time').copy()
            top_voice['Пользователь'] = top_voice['user_id'].apply(
                lambda x: make_discord_link(x, members_cache)
            )
            top_voice['Часов'] = (top_voice['period_voice_time'] / 3600).round(1)
            
            st.markdown(
                top_voice[['Пользователь', 'Часов']].to_html(escape=False, index=False),
                unsafe_allow_html=True
            )

# ==================== ТАБ 2: НЕАКТИВНЫЕ ====================
with tab2:
    st.header("😴 Неактивные пользователи")
    
    roles = get_guild_roles(guild_id)
    
    # Фильтры
    col1, col2 = st.columns([1, 1])

    with col1:
        inactive_days = st.selectbox(
            "📅 Период неактивности (дней)", 
            [7, 14, 30], 
            index=0, 
            key="inactive_days"
        )

    with col2:
        activity_type = st.selectbox(
            "📊 Тип активности:",
            options=['both', 'messages', 'voice'],
            format_func=lambda x: {
                'both': '💬🎤 Чат И Войс (оба)',
                'messages': '💬 Только чат',
                'voice': '🎤 Только войс'
            }[x],
            key="activity_type"
        )

    col3, col4 = st.columns(2)

    with col3:
        include_roles = st.multiselect(
            "✅ Показать только с ролями:",
            options=roles,
            format_func=lambda x: x['name'],
            key="include_roles"
        )

    with col4:
        exclude_roles = st.multiselect(
            "❌ Исключить пользователей с ролями:",
            options=roles,
            format_func=lambda x: x['name'],
            key="exclude_roles"
        )

    inactive_data = get_inactive_users(guild_id, inactive_days, activity_type)
    inactive_ids = inactive_data.get('inactive_user_ids', [])
    
    # Применяем фильтры по ролям
    if include_roles or exclude_roles:
        include_role_ids = {r['id'] for r in include_roles}
        exclude_role_ids = {r['id'] for r in exclude_roles}
        
        filtered_ids = []
        
        for user_id in inactive_ids:
            member = members_cache.get(user_id)
            if not member:
                continue
            
            user_roles = set(member.get('roles', []))
            
            if include_role_ids:
                if not (user_roles & include_role_ids):
                    continue
            
            if exclude_role_ids:
                if user_roles & exclude_role_ids:
                    continue
            
            filtered_ids.append(user_id)
        
        inactive_ids = filtered_ids
        inactive_data['inactive_members'] = len(inactive_ids)
    
    # Метрики
    col1, col2, col3 = st.columns(3)
    
    col1.metric("👥 Всего участников", inactive_data.get('total_members', 0))
    col2.metric("✅ Активных", inactive_data.get('active_members', 0))
    col3.metric(
        "❌ Неактивных" + (" (с фильтром)" if (include_roles or exclude_roles) else ""),
        len(inactive_ids)
    )
    
    # Процент активности
    if inactive_data.get('total_members', 0) > 0:
        activity_percent = (inactive_data.get('active_members', 0) / inactive_data['total_members']) * 100
        
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=activity_percent,
            title={'text': "Процент активности"},
            gauge={
                'axis': {'range': [None, 100]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, 30], 'color': "lightgray"},
                    {'range': [30, 70], 'color': "gray"},
                    {'range': [70, 100], 'color': "lightgreen"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 90
                }
            }
        ))
        
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Список неактивных
    if inactive_ids:
        st.subheader(f"📋 Список неактивных пользователей ({len(inactive_ids)})")
        
        if include_roles:
            st.info(f"✅ Фильтр: показаны только пользователи с ролями: {', '.join([r['name'] for r in include_roles])}")
        if exclude_roles:
            st.warning(f"❌ Фильтр: исключены пользователи с ролями: {', '.join([r['name'] for r in exclude_roles])}")
        
        inactive_list = []
        for user_id in inactive_ids:
            member = members_cache.get(user_id)
            if member:
                user_role_ids = member.get('roles', [])
                user_role_names = [r['name'] for r in roles if r['id'] in user_role_ids]
                
                inactive_list.append({
                    'user_id': user_id,
                    'name': member['display_name'],
                    'roles': ', '.join(user_role_names) if user_role_names else 'Нет ролей'
                })
            else:
                inactive_list.append({
                    'user_id': user_id,
                    'name': f'User {user_id}',
                    'roles': 'Неизвестно'
                })
        
        inactive_df = pd.DataFrame(inactive_list)
        inactive_df['Пользователь'] = inactive_df['user_id'].apply(
            lambda x: make_discord_link(x, members_cache)
        )
        
        st.markdown(
            inactive_df[['Пользователь', 'roles']].rename(columns={'roles': 'Роли'}).to_html(escape=False, index=False),
            unsafe_allow_html=True
        )
        
        csv = inactive_df[['user_id', 'name', 'roles']].to_csv(index=False)
        st.download_button(
            label="📥 Скачать список (CSV)",
            data=csv,
            file_name=f"inactive_users_{guild['name']}_{inactive_days}days.csv",
            mime="text/csv"
        )
    else:
        if include_roles or exclude_roles:
            st.info("🔍 Нет пользователей, соответствующих выбранным фильтрам")
        else:
            st.success("🎉 Все пользователи активны!")

# ==================== ТАБ 3: ВЫГОВОРЫ ====================
with tab3:
    st.header("⚠️ Система выговоров")
    
    warnings_data = get_warnings(guild_id)
    
    col1, col2, col3 = st.columns(3)
    
    col1.metric("📋 Всего выговоров", warnings_data.get('total_warnings', 0))
    col2.metric("🔴 Активных", warnings_data.get('active_warnings', 0))
    col3.metric("👤 Уникальных пользователей", warnings_data.get('unique_users', 0))
    
    st.markdown("---")
    
    top_offenders = warnings_data.get('top_offenders', [])
    
    if top_offenders:
        st.subheader("🔥 Топ-10 нарушителей")
        
        offenders_df = pd.DataFrame(top_offenders)
        offenders_df['Пользователь'] = offenders_df['user_id'].apply(
            lambda x: make_discord_link(x, members_cache)
        )
        offenders_df['Активных выговоров'] = offenders_df['warning_count']
        
        st.markdown(
            offenders_df[['Пользователь', 'Активных выговоров']].to_html(escape=False, index=False),
            unsafe_allow_html=True
        )
        
        fig = px.bar(
            offenders_df,
            x='user_id',
            y='warning_count',
            title='Топ нарушителей',
            labels={'user_id': 'User ID', 'warning_count': 'Количество выговоров'},
            color='warning_count',
            color_continuous_scale='Reds'
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.success("✅ Нет активных выговоров!")

# ==================== ТАБ 4: ГРАФИКИ ====================
with tab4:
    st.header("📊 Визуализация данных")
    
    graph_days = st.selectbox("📅 Период для графиков", [7, 14, 30], index=2, key="graph_days")
    
    stats = get_guild_stats(guild_id, graph_days)
    
    if stats:
        df = pd.DataFrame(stats)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Распределение сообщений")
            fig1 = px.histogram(
                df,
                x='period_messages',
                nbins=20,
                title='Распределение пользователей по количеству сообщений',
                labels={'period_messages': 'Количество сообщений', 'count': 'Пользователей'}
            )
            st.plotly_chart(fig1, use_container_width=True)
        
        with col2:
            st.subheader("🎤 Распределение времени в войсе")
            df['voice_hours'] = df['period_voice_time'] / 3600
            fig2 = px.histogram(
                df,
                x='voice_hours',
                nbins=20,
                title='Распределение пользователей по времени в войсе',
                labels={'voice_hours': 'Часов в войсе', 'count': 'Пользователей'}
            )
            st.plotly_chart(fig2, use_container_width=True)
        
        st.subheader("📈 Корреляция: Сообщения vs Время в войсе")
        fig3 = px.scatter(
            df,
            x='period_messages',
            y='voice_hours',
            title='Зависимость времени в войсе от количества сообщений',
            labels={'period_messages': 'Сообщений', 'voice_hours': 'Часов в войсе'},
            opacity=0.6
        )
        st.plotly_chart(fig3, use_container_width=True)

st.markdown("---")
st.markdown("**ALFA Bot Dashboard** • Обновляется каждую минуту")