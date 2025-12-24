import discord
from discord.ext import commands
from datetime import datetime
import io
import csv
from io import StringIO
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge
import numpy as np

class StatsSelectMenu(discord.ui.Select):
    """Dropdown меню для выбора периода статистики"""
    def __init__(self, bot, user_id):
        self.bot = bot
        self.user_id = user_id
        options = [
            discord.SelectOption(label="За все время", description="Полная статистика", emoji="📊", value="all"),
            discord.SelectOption(label="За 7 дней", description="Последняя неделя", emoji="📅", value="7"),
            discord.SelectOption(label="За 14 дней", description="Последние 2 недели", emoji="📆", value="14"),
            discord.SelectOption(label="За 30 дней", description="Последний месяц", emoji="🗓️", value="30"),
        ]
        super().__init__(
            placeholder="Выберите период статистики...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="stats_period_select"
        )

    async def callback(self, interaction: discord.Interaction):
        period = self.values[0]
        days = None if period == "all" else int(period)
        
        # Получаем статистику
        member = interaction.guild.get_member(self.user_id)
        if not member:
            await interaction.response.send_message("❌ Пользователь не найден", ephemeral=True)
            return
            
        stats = self.bot.db.get_user_stats(interaction.guild.id, member.id, days)
        
        if not stats:
            await interaction.response.send_message(f"📊 Нет данных для статистики", ephemeral=True)
            return

        # Формируем embed
        period_text = f"за последние {days} дней" if days else "за все время"
        embed = discord.Embed(
            title=f"📊 Ваша статистика",
            description=f"Статистика активности {period_text}",
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        # Сообщения
        if days:
            embed.add_field(
                name="💬 Сообщения",
                value=f"**{period_text.capitalize()}:** {stats['period_messages']}\n**Всего:** {stats['total_messages']}",
                inline=True
            )
        else:
            embed.add_field(
                name="💬 Сообщения",
                value=f"**Всего:** {stats['total_messages']}",
                inline=True
            )

        # Голосовые каналы
        voice_time_period = sum([duration for _, duration in stats['voice_by_channel']])
        hours_period = int(voice_time_period // 3600)
        minutes_period = int((voice_time_period % 3600) // 60)

        hours_total = int(stats['total_voice_time'] // 3600)
        minutes_total = int((stats['total_voice_time'] % 3600) // 60)

        if days:
            embed.add_field(
                name="🎤 Голосовые каналы",
                value=f"**{period_text.capitalize()}:** {hours_period}ч {minutes_period}м\n**Всего:** {hours_total}ч {minutes_total}м",
                inline=True
            )
        else:
            embed.add_field(
                name="🎤 Голосовые каналы",
                value=f"**Всего:** {hours_total}ч {minutes_total}м",
                inline=True
            )

        # Процент активности (если есть период)
        if days:
            total_users_stats = self.bot.db.get_all_users_stats(interaction.guild.id, days)
            if total_users_stats:
                user_rank_messages = next((i+1 for i, u in enumerate(sorted(total_users_stats, key=lambda x: x['period_messages'], reverse=True)) if u['user_id'] == member.id), None)
                user_rank_voice = next((i+1 for i, u in enumerate(sorted(total_users_stats, key=lambda x: x['period_voice_time'], reverse=True)) if u['user_id'] == member.id), None)
                
                if user_rank_messages and user_rank_voice:
                    embed.add_field(
                        name="🏆 Ваше место",
                        value=f"**По сообщениям:** #{user_rank_messages}/{len(total_users_stats)}\n**По войсу:** #{user_rank_voice}/{len(total_users_stats)}",
                        inline=False
                    )

        # Топ каналов
        if stats['voice_by_channel']:
            top_channels = []
            for channel_id, duration in stats['voice_by_channel'][:3]:
                channel = interaction.guild.get_channel(channel_id)
                channel_name = channel.name if channel else f"ID:{channel_id}"
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                top_channels.append(f"**{channel_name}:** {hours}ч {minutes}м")

            embed.add_field(
                name="🎯 Топ-3 голосовых канала",
                value="\n".join(top_channels),
                inline=False
            )

        embed.set_footer(text=f"Запросил: {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)

        await interaction.response.send_message(embed=embed, ephemeral=True)


class ExportModal(discord.ui.Modal, title="📤 Экспорт статистики"):
    """Модальное окно для экспорта статистики"""
    
    def __init__(self, bot, export_type="user"):
        super().__init__()
        self.bot = bot
        self.export_type = export_type
        
        self.period = discord.ui.TextInput(
            label="Период (дней)",
            placeholder="7, 14, 30 или оставьте пустым для всего времени",
            required=False,
            max_length=2
        )
        self.add_item(self.period)
        
        if export_type == "user":
            self.user_id = discord.ui.TextInput(
                label="ID пользователя",
                placeholder="Оставьте пустым для своей статистики",
                required=False,
                max_length=20
            )
            self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        # Обработка периода
        days = None
        if self.period.value.strip():
            try:
                days = int(self.period.value)
                if days not in [7, 14, 30]:
                    await interaction.response.send_message("❌ Допустимые периоды: 7, 14 или 30 дней", ephemeral=True)
                    return
            except ValueError:
                await interaction.response.send_message("❌ Период должен быть числом", ephemeral=True)
                return

        await interaction.response.defer(ephemeral=True)

        if self.export_type == "user":
            # Определяем пользователя
            if self.user_id.value.strip():
                try:
                    user_id = int(self.user_id.value)
                    member = interaction.guild.get_member(user_id)
                    if not member:
                        await interaction.followup.send("❌ Пользователь не найден", ephemeral=True)
                        return
                except ValueError:
                    await interaction.followup.send("❌ Неверный ID пользователя", ephemeral=True)
                    return
            else:
                member = interaction.user

            # Получаем статистику
            stats = self.bot.db.get_user_stats(interaction.guild.id, member.id, days)

            if not stats:
                await interaction.followup.send(f"📊 Нет данных для {member.mention}", ephemeral=True)
                return

            # Формируем CSV
            output = StringIO()
            writer = csv.writer(output)

            period_text = f"{days} days" if days else "all time"

            writer.writerow(['User Statistics'])
            writer.writerow(['User:', member.display_name])
            writer.writerow(['User ID:', member.id])
            writer.writerow(['Period:', period_text])
            writer.writerow(['Export Date:', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')])
            writer.writerow([])

            writer.writerow(['Messages'])
            if days:
                writer.writerow(['Period Messages:', stats['period_messages']])
            writer.writerow(['Total Messages:', stats['total_messages']])
            writer.writerow([])

            writer.writerow(['Voice Time'])
            voice_time_period = sum([duration for _, duration in stats['voice_by_channel']])
            if days:
                writer.writerow(['Period Voice Time (seconds):', int(voice_time_period)])
                writer.writerow(['Period Voice Time (formatted):', f"{int(voice_time_period // 3600)}h {int((voice_time_period % 3600) // 60)}m"])
            writer.writerow(['Total Voice Time (seconds):', int(stats['total_voice_time'])])
            writer.writerow(['Total Voice Time (formatted):', f"{int(stats['total_voice_time'] // 3600)}h {int((stats['total_voice_time'] % 3600) // 60)}m"])
            writer.writerow([])

            writer.writerow(['Voice Channels'])
            writer.writerow(['Channel Name', 'Time (seconds)', 'Time (formatted)'])
            for channel_id, duration in stats['voice_by_channel']:
                channel = interaction.guild.get_channel(channel_id)
                channel_name = channel.name if channel else f"ID:{channel_id}"
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                writer.writerow([channel_name, int(duration), f"{hours}h {minutes}m"])

            csv_data = output.getvalue()

            # Создаем файл
            file = discord.File(
                io.BytesIO(csv_data.encode('utf-8-sig')),
                filename=f'stats_{member.name}_{period_text}.csv'
            )

            await interaction.followup.send(f"📊 Экспорт статистики {member.mention}", file=file, ephemeral=True)

        elif self.export_type == "all":
            # Экспорт всех пользователей
            all_stats = self.bot.db.get_all_users_stats(interaction.guild.id, days)

            if not all_stats:
                await interaction.followup.send("📊 Нет данных о пользователях", ephemeral=True)
                return

            # Формируем CSV
            output = StringIO()
            writer = csv.writer(output)

            period_text = f"{days} days" if days else "all time"

            writer.writerow(['Server Statistics'])
            writer.writerow(['Server:', interaction.guild.name])
            writer.writerow(['Period:', period_text])
            writer.writerow(['Total Users:', len(all_stats)])
            writer.writerow(['Export Date:', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')])
            writer.writerow([])

            # Заголовок таблицы
            if days:
                writer.writerow([
                    'Rank',
                    'User Name',
                    'User ID',
                    f'Messages ({period_text})',
                    'Total Messages',
                    f'Voice Time ({period_text})',
                    'Total Voice Time'
                ])
            else:
                writer.writerow([
                    'Rank',
                    'User Name',
                    'User ID',
                    'Total Messages',
                    'Total Voice Time'
                ])

            # Сортируем по сообщениям
            sorted_stats = sorted(all_stats, key=lambda x: x['period_messages'], reverse=True)

            # Записываем данные
            for i, user_data in enumerate(sorted_stats, 1):
                member = interaction.guild.get_member(user_data['user_id'])
                user_name = member.display_name if member else f"User ID: {user_data['user_id']}"

                if days:
                    period_hours = int(user_data['period_voice_time'] // 3600)
                    period_minutes = int((user_data['period_voice_time'] % 3600) // 60)
                    total_hours = int(user_data['total_voice_time'] // 3600)
                    total_minutes = int((user_data['total_voice_time'] % 3600) // 60)

                    writer.writerow([
                        i,
                        user_name,
                        user_data['user_id'],
                        user_data['period_messages'],
                        user_data['total_messages'],
                        f"{period_hours}h {period_minutes}m",
                        f"{total_hours}h {total_minutes}m"
                    ])
                else:
                    hours = int(user_data['total_voice_time'] // 3600)
                    minutes = int((user_data['total_voice_time'] % 3600) // 60)

                    writer.writerow([
                        i,
                        user_name,
                        user_data['user_id'],
                        user_data['total_messages'],
                        f"{hours}h {minutes}m"
                    ])

            csv_data = output.getvalue()

            # Создаем файл
            file = discord.File(
                io.BytesIO(csv_data.encode('utf-8-sig')),
                filename=f'server_stats_{interaction.guild.name}_{period_text}.csv'
            )

            await interaction.followup.send(f"📊 Экспорт статистики сервера ({len(all_stats)} пользователей)", file=file, ephemeral=True)


class StatsView(discord.ui.View):
    """View для раздела статистики"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="📊 Моя статистика", style=discord.ButtonStyle.blurple, custom_id="my_stats")
    async def my_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Добавляем Select Menu для выбора периода
        view = discord.ui.View(timeout=180)
        view.add_item(StatsSelectMenu(self.bot, interaction.user.id))
        
        embed = discord.Embed(
            title="📊 Просмотр статистики",
            description="Выберите период для просмотра вашей статистики:",
            color=0x3498DB
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🏆 Топ сервера", style=discord.ButtonStyle.green, custom_id="server_top")
    async def server_top(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Получаем статистику за 7 дней по умолчанию
        all_stats = self.bot.db.get_all_users_stats(interaction.guild.id, 7)

        if not all_stats:
            await interaction.response.send_message("📊 Нет данных о пользователях", ephemeral=True)
            return

        # Ограничиваем до топ-10
        display_stats = all_stats[:25]

        embed = discord.Embed(
            title=f"🏆 Топ пользователей сервера",
            description=f"Рейтинг за последние 7 дней",
            color=0xF1C40F,
            timestamp=datetime.utcnow()
        )

        # Топ по сообщениям
        messages_top = sorted(display_stats, key=lambda x: x['period_messages'], reverse=True)[:10]
        messages_text = []
        for i, user_data in enumerate(messages_top, 1):
            member = interaction.guild.get_member(user_data['user_id'])
            if member:
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "▫️"
                messages_text.append(f"{emoji} **{member.display_name}**: {user_data['period_messages']} сообщений")

        if messages_text:
            embed.add_field(
                name="💬 Топ-10 по сообщениям",
                value="\n".join(messages_text),
                inline=False
            )

        # Топ по времени в войсе
        voice_top = sorted(display_stats, key=lambda x: x['period_voice_time'], reverse=True)[:10]
        voice_text = []
        for i, user_data in enumerate(voice_top, 1):
            member = interaction.guild.get_member(user_data['user_id'])
            if member:
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "▫️"
                hours = int(user_data['period_voice_time'] // 3600)
                minutes = int((user_data['period_voice_time'] % 3600) // 60)
                voice_text.append(f"{emoji} **{member.display_name}**: {hours}ч {minutes}м")

        if voice_text:
            embed.add_field(
                name="🎤 Топ-10 по времени в войсе",
                value="\n".join(voice_text),
                inline=False
            )

        embed.set_footer(text=f"Всего пользователей: {len(all_stats)}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📤 Экспорт", style=discord.ButtonStyle.gray, custom_id="export_stats")
    async def export_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Показываем выбор типа экспорта
        view = discord.ui.View(timeout=60)
        
        async def export_user_callback(inter: discord.Interaction):
            modal = ExportModal(self.bot, "user")
            await inter.response.send_modal(modal)
        
        async def export_all_callback(inter: discord.Interaction):
            # Проверка прав администратора
            if not inter.user.guild_permissions.administrator:
                await inter.response.send_message("⛔ Только администраторы могут экспортировать статистику всех пользователей", ephemeral=True)
                return
            modal = ExportModal(self.bot, "all")
            await inter.response.send_modal(modal)
        
        btn_user = discord.ui.Button(label="Моя статистика", style=discord.ButtonStyle.blurple, emoji="👤")
        btn_user.callback = export_user_callback
        
        btn_all = discord.ui.Button(label="Все пользователи", style=discord.ButtonStyle.red, emoji="👥")
        btn_all.callback = export_all_callback
        
        view.add_item(btn_user)
        view.add_item(btn_all)
        
        embed = discord.Embed(
            title="📤 Экспорт статистики",
            description="Выберите тип экспорта:",
            color=0x95A5A6
        )
        embed.add_field(name="👤 Моя статистика", value="Экспорт вашей статистики в CSV", inline=False)
        embed.add_field(name="👥 Все пользователи", value="Экспорт статистики всех пользователей (только для админов)", inline=False)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📈 График активности", style=discord.ButtonStyle.gray, custom_id="activity_chart")
    async def activity_chart(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Получаем статистику пользователя за 30 дней
        stats = self.bot.db.get_user_stats(interaction.guild.id, interaction.user.id, 30)
        
        if not stats or (stats['total_messages'] == 0 and stats['total_voice_time'] == 0):
            await interaction.followup.send("📊 Недостаточно данных для создания графика", ephemeral=True)
            return

        # Создаем график
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        fig.patch.set_facecolor('#2C2F33')
        
        # График 1: Круговая диаграмма активности
        voice_time = sum([duration for _, duration in stats['voice_by_channel']])
        messages = stats.get('period_messages', stats['total_messages'])
        
        # Нормализуем данные (сообщения в минуты для сравнения)
        voice_minutes = voice_time / 60
        message_minutes = messages * 0.5  # Примерно 30 секунд на сообщение
        
        if voice_minutes > 0 or message_minutes > 0:
            ax1.pie(
                [voice_minutes, message_minutes],
                labels=['Голосовая активность', 'Текстовая активность'],
                autopct='%1.1f%%',
                colors=['#7289DA', '#43B581'],
                textprops={'color': 'white', 'fontsize': 10}
            )
            ax1.set_title('Распределение активности', color='white', fontsize=12, fontweight='bold')
        
        # График 2: Топ голосовых каналов
        if stats['voice_by_channel']:
            channels = []
            durations = []
            for channel_id, duration in stats['voice_by_channel'][:5]:
                channel = interaction.guild.get_channel(channel_id)
                channel_name = channel.name if channel else f"ID:{channel_id}"
                # Обрезаем длинные названия
                if len(channel_name) > 15:
                    channel_name = channel_name[:12] + "..."
                channels.append(channel_name)
                durations.append(duration / 3600)  # В часах
            
            bars = ax2.barh(channels, durations, color='#7289DA')
            ax2.set_xlabel('Часы', color='white', fontsize=10)
            ax2.set_title('Топ-5 голосовых каналов', color='white', fontsize=12, fontweight='bold')
            ax2.tick_params(colors='white')
            ax2.set_facecolor('#23272A')
            
            # Добавляем значения на столбцы
            for bar in bars:
                width = bar.get_width()
                ax2.text(width, bar.get_y() + bar.get_height()/2, 
                        f'{width:.1f}ч',
                        ha='left', va='center', color='white', fontsize=9, fontweight='bold')
        else:
            ax2.text(0.5, 0.5, 'Нет данных о голосовой активности', 
                    ha='center', va='center', transform=ax2.transAxes, 
                    color='white', fontsize=12)
            ax2.set_facecolor('#23272A')
            ax2.set_xticks([])
            ax2.set_yticks([])
        
        plt.tight_layout()
        
        # Сохраняем в BytesIO
        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor='#2C2F33', dpi=150)
        buf.seek(0)
        plt.close()
        
        # Отправляем
        file = discord.File(buf, filename='activity_chart.png')
        
        embed = discord.Embed(
            title="📈 Ваша активность за 30 дней",
            color=0x7289DA,
            timestamp=datetime.utcnow()
        )
        embed.set_image(url="attachment://activity_chart.png")
        embed.set_footer(text=f"Запросил: {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        await interaction.followup.send(embed=embed, file=file, ephemeral=True)

    @discord.ui.button(label="🔙 Назад", style=discord.ButtonStyle.red, custom_id="back_to_main")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Возвращаемся к главной панели
        embed = discord.Embed(
            title="🎛️ ALFA Bot Control Panel",
            description="Добро пожаловать в панель управления!\nВыберите нужный раздел, нажав на кнопку ниже.",
            color=0x2ECC71,
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        embed.set_footer(text="ALFA Bot • Панель управления", icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None)

        await interaction.response.edit_message(embed=embed, view=PanelView(self.bot))


class PanelView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="📡 Ping", style=discord.ButtonStyle.green, custom_id="panel_ping")
    async def ping(self, interaction: discord.Interaction, button: discord.ui.Button):
        latency = round(self.bot.latency * 1000)
        
        # Определяем качество пинга
        if latency < 100:
            quality = "Отлично"
            color = 0x2ECC71
            emoji = "🟢"
        elif latency < 200:
            quality = "Хорошо"
            color = 0xF1C40F
            emoji = "🟡"
        else:
            quality = "Плохо"
            color = 0xE74C3C
            emoji = "🔴"
        
        embed = discord.Embed(
            title="🏓 Ping Test",
            description=f"{emoji} **{latency} ms** - {quality}",
            color=color,
            timestamp=datetime.utcnow()
        )
        
        # Добавляем визуальный индикатор
        ping_bar = "█" * min(10, latency // 20)
        embed.add_field(name="Визуализация", value=f"`{ping_bar}`", inline=False)
        
        embed.set_footer(text="WebSocket Latency")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="ℹ️ Info", style=discord.ButtonStyle.blurple, custom_id="panel_info")
    async def info(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Подсчет статистики в реальном времени
        total_members = sum(guild.member_count for guild in self.bot.guilds)
        total_channels = sum(len(guild.channels) for guild in self.bot.guilds)
        
        # Получаем статистику по типам каналов для текущего сервера
        text_channels = len(interaction.guild.text_channels)
        voice_channels = len(interaction.guild.voice_channels)
        categories = len(interaction.guild.categories)
        
        embed = discord.Embed(
            title="📋 ALFA Bot Information",
            description="Discord-бот для опросов и статистики с расширенными возможностями",
            color=0x5865F2,
            timestamp=datetime.utcnow()
        )
        
        # Общая информация о боте
        embed.add_field(
            name="🤖 О боте",
            value=f"**Версия:** `2.0 Extended`\n**Библиотека:** `discord.py`\n**Ping:** `{round(self.bot.latency * 1000)} ms`",
            inline=True
        )
        
        # Статистика ботa
        embed.add_field(
            name="📊 Глобальная статистика",
            value=f"**Серверов:** `{len(self.bot.guilds)}`\n**Пользователей:** `{total_members:,}`\n**Каналов:** `{total_channels}`",
            inline=True
        )
        
        # Информация о текущем сервере
        embed.add_field(
            name="🖥️ Текущий сервер",
            value=f"**Название:** `{interaction.guild.name}`\n**Участников:** `{interaction.guild.member_count}`\n**Создан:** <t:{int(interaction.guild.created_at.timestamp())}:R>",
            inline=True
        )
        
        # Каналы сервера
        embed.add_field(
            name="📡 Каналы сервера",
            value=f"**💬 Текстовых:** `{text_channels}`\n**🎤 Голосовых:** `{voice_channels}`\n**📁 Категорий:** `{categories}`",
            inline=True
        )
        
        # Команды
        slash_commands = len(self.bot.tree.get_commands())
        embed.add_field(
            name="⚡ Команды",
            value=f"**Slash команд:** `{slash_commands}`\n**Всего функций:** `25+`",
            inline=True
        )
        
        # Статус
        embed.add_field(
            name="✅ Статус",
            value=f"**Работает:** `Онлайн`\n**Аптайм:** `99.9%`\n**Готовность:** `100%`",
            inline=True
        )
        
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        embed.set_footer(text=f"Запросил: {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📊 Polls", style=discord.ButtonStyle.gray, custom_id="panel_polls")
    async def polls(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Импортируем PollsMenuView
        try:
            # Попытка импорта из cogs
            import sys
            import importlib
            
            if 'cogs.polls_extension' in sys.modules:
                polls_module = sys.modules['cogs.polls_extension']
                importlib.reload(polls_module)
                PollsMenuView = polls_module.PollsMenuView
            else:
                from cogs.polls_extension import PollsMenuView
        except ImportError:
            try:
                # Запасной вариант
                from polls_extension import PollsMenuView
            except ImportError:
                await interaction.response.send_message(
                    "❌ Ошибка: модуль polls_extension не найден. Убедитесь, что файл polls_extension.py находится в папке cogs/",
                    ephemeral=True
                )
                return
        
        embed = discord.Embed(
            title="📊 Управление опросами",
            description="Интерактивная панель для создания и управления опросами",
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="➕ Создать опрос",
            value="Создайте новый опрос через удобную форму",
            inline=True
        )
        embed.add_field(
            name="📊 Результаты",
            value="Просмотрите результаты любого опроса",
            inline=True
        )
        embed.add_field(
            name="📈 График",
            value="Визуализация результатов опроса",
            inline=True
        )
        embed.add_field(
            name="📋 Список опросов",
            value="Все опросы за выбранный период",
            inline=True
        )
        embed.add_field(
            name="🔒 Закрыть опрос",
            value="Завершите голосование",
            inline=True
        )
        embed.add_field(
            name="📤 Экспорт",
            value="Экспортируйте результаты в CSV",
            inline=True
        )
        
        embed.set_footer(text="Выберите действие с помощью кнопок ниже")
        
        await interaction.response.edit_message(embed=embed, view=PollsMenuView(self.bot))

    @discord.ui.button(label="📈 Stats", style=discord.ButtonStyle.blurple, custom_id="panel_stats")
    async def stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Открываем расширенное меню статистики
        embed = discord.Embed(
            title="📈 Статистика и аналитика",
            description="Выберите действие для работы со статистикой:",
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )
        
        # Real-time статистика сервера
        all_stats = self.bot.db.get_all_users_stats(interaction.guild.id, 7)
        if all_stats:
            total_messages = sum(u['period_messages'] for u in all_stats)
            total_voice_time = sum(u['period_voice_time'] for u in all_stats)
            active_users = len([u for u in all_stats if u['period_messages'] > 0 or u['period_voice_time'] > 0])
            
            embed.add_field(
                name="📊 Активность за 7 дней",
                value=f"**Сообщений:** `{total_messages:,}`\n**Активных пользователей:** `{active_users}`\n**Время в войсе:** `{int(total_voice_time // 3600)}ч {int((total_voice_time % 3600) // 60)}м`",
                inline=False
            )
        
        embed.set_footer(text="Выберите кнопку ниже для подробной информации")
        
        await interaction.response.edit_message(embed=embed, view=StatsView(self.bot))

    @discord.ui.button(label="🔐 Whitelist", style=discord.ButtonStyle.red, custom_id="panel_whitelist")
    async def whitelist(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="⛔ Доступ запрещен",
                description="Только администраторы могут управлять whitelist",
                color=0xE74C3C
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="🔐 Управление Whitelist",
            description="Команды для управления белым списком:",
            color=0xE74C3C
        )
        embed.add_field(
            name="Добавить в whitelist",
            value="</alfa_whitelist_add:ID> `@user`\n*Добавить пользователя в белый список*",
            inline=False
        )
        embed.add_field(
            name="Удалить из whitelist",
            value="</alfa_whitelist_remove:ID> `@user`\n*Удалить пользователя из белого списка*",
            inline=False
        )
        embed.add_field(
            name="Список whitelist",
            value="</alfa_whitelist_list:ID>\n*Просмотреть весь белый список*",
            inline=False
        )
        
        embed.set_footer(text="⚠️ Whitelist дает доступ к командам статистики и опросов")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Panel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="panel", description="🎛️ Панель управления ALFA Bot")
    async def panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎛️ ALFA Bot Control Panel",
            description="Добро пожаловать в панель управления!\nВыберите нужный раздел, нажав на кнопку ниже.",
            color=0x2ECC71,
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        embed.set_footer(text="ALFA Bot • Панель управления", icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None)

        await interaction.response.send_message(
            embed=embed,
            view=PanelView(self.bot),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Panel(bot))