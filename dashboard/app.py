import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="ALFA Bot Dashboard", page_icon="📊", layout="wide")

BOT_API_URL = "http://localhost:5555/api"

# Кэширование данных
@st.cache_data(ttl=60)
def get_guilds():
    try:
        response = requests.get(f"{BOT_API_URL}/guilds", timeout=5)
        return response.json()
    except:
        return []

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
def get_inactive_users(guild_id, days):
    try:
        response = requests.get(f"{BOT_API_URL}/guild/{guild_id}/inactive/{days}", timeout=5)
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

def make_discord_link(user_id, members_cache):
    member = members_cache.get(user_id)
    if member:
        name = member['display_name']
        avatar = member.get('avatar') or 'https://cdn.discordapp.com/embed/avatars/0.png'
        return f'<img src="{avatar}" width="24" style="border-radius:50%; vertical-align:middle; margin-right:8px;"><a href="https://discord.com/users/{user_id}" target="_blank" style="text-decoration:none; color:#5865F2; font-weight:500;">{name}</a>'
    return f'<a href="https://discord.com/users/{user_id}" target="_blank" style="color:#5865F2;">User {user_id}</a>'

# Заголовок
st.title("📊 ALFA Bot Dashboard")

# Проверка подключения
guilds = get_guilds()

if not guilds:
    st.error("❌ Не удается подключиться к боту. Убедитесь что бот запущен и API работает на порту 5555")
    st.info("Проверьте: http://localhost:5555/stats")
    st.stop()

# Выбор сервера
guild = st.sidebar.selectbox(
    "🏰 Выберите сервер",
    guilds,
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

# Табы
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
    
    inactive_days = st.selectbox("📅 Период неактивности (дней)", [7, 14, 30], index=0, key="inactive_days")
    
    inactive_data = get_inactive_users(guild_id, inactive_days)
    
    # Метрики
    col1, col2, col3 = st.columns(3)
    
    col1.metric("👥 Всего участников", inactive_data.get('total_members', 0))
    col2.metric("✅ Активных", inactive_data.get('active_members', 0))
    col3.metric("❌ Неактивных", inactive_data.get('inactive_members', 0))
    
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
    inactive_ids = inactive_data.get('inactive_user_ids', [])
    
    if inactive_ids:
        st.subheader(f"📋 Список неактивных пользователей ({len(inactive_ids)})")
        
        # Создаем DataFrame
        inactive_df = pd.DataFrame({'user_id': inactive_ids})
        inactive_df['Пользователь'] = inactive_df['user_id'].apply(
            lambda x: make_discord_link(x, members_cache)
        )
        
        # Выводим в виде таблицы
        st.markdown(
            inactive_df[['Пользователь']].to_html(escape=False, index=False),
            unsafe_allow_html=True
        )
        
        # Кнопка экспорта
        csv = inactive_df[['user_id']].to_csv(index=False)
        st.download_button(
            label="📥 Скачать список (CSV)",
            data=csv,
            file_name=f"inactive_users_{guild['name']}_{inactive_days}days.csv",
            mime="text/csv"
        )
    else:
        st.success("🎉 Все пользователи активны!")

# ==================== ТАБ 3: ВЫГОВОРЫ ====================
with tab3:
    st.header("⚠️ Система выговоров")
    
    warnings_data = get_warnings(guild_id)
    
    # Метрики
    col1, col2, col3 = st.columns(3)
    
    col1.metric("📋 Всего выговоров", warnings_data.get('total_warnings', 0))
    col2.metric("🔴 Активных", warnings_data.get('active_warnings', 0))
    col3.metric("👤 Уникальных пользователей", warnings_data.get('unique_users', 0))
    
    st.markdown("---")
    
    # Топ нарушителей
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
        
        # График
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
        
        # График 1: Распределение активности
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
        
        # График 3: Корреляция сообщений и войса
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

# Футер
st.markdown("---")
st.markdown("**ALFA Bot Dashboard** • Обновляется каждую минуту")