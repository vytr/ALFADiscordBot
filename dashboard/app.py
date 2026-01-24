import streamlit as st
import requests
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="ALFA Bot Dashboard", page_icon="📊", layout="wide")

BOT_API_URL = "http://localhost:5555/api"

@st.cache_data(ttl=60)
def get_guilds():
    response = requests.get(f"{BOT_API_URL}/guilds")
    return response.json()

@st.cache_data(ttl=30)
def get_guild_members(guild_id):
    response = requests.get(f"{BOT_API_URL}/guild/{guild_id}/members")
    members = response.json()
    # Создаем словарь для быстрого поиска
    return {m['id']: m for m in members if not m['bot']}

@st.cache_data(ttl=60)
def get_guild_stats(guild_id, days):
    response = requests.get(f"{BOT_API_URL}/guild/{guild_id}/stats/{days}")
    return response.json()

st.title("📊 ALFA Bot Dashboard")

guilds = get_guilds()

if not guilds:
    st.error("Нет доступных серверов")
    st.stop()

guild = st.sidebar.selectbox(
    "Выберите сервер",
    guilds,
    format_func=lambda x: f"{x['name']} ({x['member_count']} участников)"
)

guild_id = guild['id']
members_cache = get_guild_members(guild_id)

def make_discord_link(user_id):
    member = members_cache.get(user_id)
    if member:
        name = member['display_name']
        avatar = member['avatar'] or 'https://cdn.discordapp.com/embed/avatars/0.png'
        return f'<img src="{avatar}" width="20" style="border-radius:50%; vertical-align:middle;"> <a href="https://discord.com/users/{user_id}" target="_blank">{name}</a>'
    return f'<a href="https://discord.com/users/{user_id}" target="_blank">User {user_id}</a>'

tab1, tab2, tab3 = st.tabs(["📈 Статистика", "😴 Неактивные", "⚠️ Выговоры"])

with tab1:
    st.header("Статистика активности")
    
    days = st.selectbox("Период", [7, 14, 30], index=0)
    
    stats = get_guild_stats(guild_id, days)
    df = pd.DataFrame(stats)
    
    if not df.empty:
        df = df.sort_values('period_messages', ascending=False).head(20)
        df['Пользователь'] = df['user_id'].apply(make_discord_link)
        df['Сообщения'] = df['period_messages']
        df['Войс (ч)'] = (df['period_voice_time'] / 3600).round(1)
        
        st.markdown(
            df[['Пользователь', 'Сообщения', 'Войс (ч)']].to_html(escape=False, index=False),
            unsafe_allow_html=True
        )
        
        fig = px.bar(df.head(10), x='user_id', y='period_messages', 
                     title=f'Топ-10 по сообщениям ({days} дней)')
        st.plotly_chart(fig, use_container_width=True)

# ... остальные табы аналогично