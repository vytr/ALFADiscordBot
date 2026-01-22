import discord
from discord.ext import commands
from datetime import datetime
import io
import csv
from io import StringIO

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
        voice_time_period = stats['period_voice_time']
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
            voice_time_period = stats['period_voice_time']
            if days:
                writer.writerow(['Period Voice Time (seconds):', int(voice_time_period)])
                writer.writerow(['Period Voice Time (formatted):', f"{int(voice_time_period // 3600)}h {int((voice_time_period % 3600) // 60)}m"])
            writer.writerow(['Total Voice Time (seconds):', int(stats['total_voice_time'])])
            writer.writerow(['Total Voice Time (formatted):', f"{int(stats['total_voice_time'] // 3600)}h {int((stats['total_voice_time'] % 3600) // 60)}m"])
            writer.writerow([])

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
            # Проверка прав: администратор или в whitelist
            if not inter.user.guild_permissions.administrator:
                if not self.bot.db.is_whitelisted(inter.guild.id, inter.user.id):
                    await inter.response.send_message("⛔ Экспорт всех пользователей доступен только администраторам и whitelisted пользователям!", ephemeral=True)
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

    @discord.ui.button(label="📊 Детальная статистика", style=discord.ButtonStyle.gray, custom_id="activity_chart")
    async def activity_chart(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Получаем статистику пользователя за 30 дней
        stats = self.bot.db.get_user_stats(interaction.guild.id, interaction.user.id, 30)
        
        if not stats or (stats['total_messages'] == 0 and stats['total_voice_time'] == 0):
            await interaction.followup.send("📊 Недостаточно данных для статистики", ephemeral=True)
            return

        embed = discord.Embed(
            title="📊 Детальная статистика за 30 дней",
            color=0x7289DA,
            timestamp=datetime.utcnow()
        )
        
        # Общие данные
        voice_time = sum([duration for _, duration in stats['voice_by_channel']])
        messages = stats.get('period_messages', stats['total_messages'])
        
        # Активность
        voice_hours = int(voice_time // 3600)
        voice_minutes = int((voice_time % 3600) // 60)
        
        embed.add_field(
            name="💬 Текстовая активность",
            value=f"**Сообщений:** {messages}\n**Всего за все время:** {stats['total_messages']}",
            inline=True
        )
        
        embed.add_field(
            name="🎤 Голосовая активность",
            value=f"**За период:** {voice_hours}ч {voice_minutes}м\n**Всего за все время:** {int(stats['total_voice_time'] // 3600)}ч {int((stats['total_voice_time'] % 3600) // 60)}м",
            inline=True
        )
        
        # Процентное соотношение
        if voice_time > 0 or messages > 0:
            # Нормализуем для сравнения (сообщения в минуты)
            voice_minutes_total = voice_time / 60
            message_minutes_total = messages * 0.5  # ~30 секунд на сообщение
            total_activity = voice_minutes_total + message_minutes_total
            
            voice_percent = (voice_minutes_total / total_activity * 100) if total_activity > 0 else 0
            message_percent = (message_minutes_total / total_activity * 100) if total_activity > 0 else 0
            
            # Визуальная полоса
            bar_length = 20
            voice_bar = int(voice_percent / 5)  # 5% = 1 символ
            message_bar = bar_length - voice_bar
            
            embed.add_field(
                name="📊 Распределение активности",
                value=f"🎤 Голосовая: `{'█' * voice_bar}{'░' * message_bar}` {voice_percent:.1f}%\n💬 Текстовая: `{'█' * message_bar}{'░' * voice_bar}` {message_percent:.1f}%",
                inline=False
            )
        
        embed.set_footer(text=f"Запросил: {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="😴 Неактивные", style=discord.ButtonStyle.gray, custom_id="inactive_users", row=3)
    async def inactive_users(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Добавляем Select Menu для выбора периода
        view = discord.ui.View(timeout=180)
        
        select = discord.ui.Select(
            placeholder="Выберите период неактивности...",
            options=[
                discord.SelectOption(label="За 7 дней", emoji="📅", value="7"),
                discord.SelectOption(label="За 14 дней", emoji="📆", value="14"),
                discord.SelectOption(label="За 30 дней", emoji="🗓️", value="30"),
            ]
        )
        
        async def select_callback(inter: discord.Interaction):
            days = int(select.values[0])
            await inter.response.defer(ephemeral=True)
            
            # Получаем всех пользователей сервера (не ботов)
            all_members = [m for m in inter.guild.members if not m.bot]
            
            # Получаем статистику активных пользователей
            active_stats = self.bot.db.get_all_users_stats(inter.guild.id, days)
            active_user_ids = {stat['user_id'] for stat in active_stats if stat['period_messages'] > 0 or stat['period_voice_time'] > 0}
            
            # Находим неактивных
            inactive_members = [m for m in all_members if m.id not in active_user_ids]
            
            if not inactive_members:
                await inter.followup.send(f"✅ Все пользователи были активны за последние {days} дней!", ephemeral=True)
                return
            
            # Формируем embed
            embed = discord.Embed(
                title=f"😴 Неактивные пользователи",
                description=f"Пользователи без активности за последние **{days} дней**",
                color=0xE67E22,
                timestamp=datetime.utcnow()
            )
            
            # Список неактивных (максимум 25)
            inactive_text = []
            for i, member in enumerate(inactive_members[:25], 1):
                top_role = member.top_role.name if member.top_role.name != "@everyone" else "Нет роли"
                inactive_text.append(f"{i}. {member.mention} • `{top_role}`")
            
            if inactive_text:
                if len(inactive_members) <= 25:
                    embed.add_field(
                        name=f"👥 Список ({len(inactive_members)} пользователей)",
                        value="\n".join(inactive_text),
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=f"👥 Первые 25 из {len(inactive_members)}",
                        value="\n".join(inactive_text),
                        inline=False
                    )
            
            # Статистика
            total_members = len(all_members)
            inactive_percent = (len(inactive_members) / total_members * 100) if total_members > 0 else 0
            
            embed.add_field(
                name="📊 Статистика",
                value=f"**Всего участников:** {total_members}\n**Неактивных:** {len(inactive_members)} ({inactive_percent:.1f}%)\n**Активных:** {len(active_user_ids)} ({100-inactive_percent:.1f}%)",
                inline=False
            )
            
            # Кнопка экспорта
            export_view = discord.ui.View(timeout=60)
            export_btn = discord.ui.Button(label="📤 Экспорт в CSV", style=discord.ButtonStyle.green)
            
            async def export_callback(export_inter: discord.Interaction):
                await export_inter.response.defer(ephemeral=True)
                
                # Формируем CSV
                from io import StringIO
                import csv
                
                output = StringIO()
                writer = csv.writer(output)
                
                writer.writerow(['Inactive Users Report'])
                writer.writerow(['Server:', inter.guild.name])
                writer.writerow(['Period:', f'{days} days'])
                writer.writerow(['Total Members:', len(all_members)])
                writer.writerow(['Inactive Members:', len(inactive_members)])
                writer.writerow(['Report Date:', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')])
                writer.writerow([])
                
                writer.writerow([
                    'Rank',
                    'Username',
                    'Display Name',
                    'User ID',
                    'Top Role',
                    'Joined Server',
                    'Account Created'
                ])
                
                for i, member in enumerate(inactive_members, 1):
                    top_role = member.top_role.name if member.top_role.name != "@everyone" else "No Role"
                    joined = member.joined_at.strftime('%Y-%m-%d') if member.joined_at else "Unknown"
                    created = member.created_at.strftime('%Y-%m-%d')
                    
                    writer.writerow([
                        i,
                        member.name,
                        member.display_name,
                        member.id,
                        top_role,
                        joined,
                        created
                    ])
                
                csv_data = output.getvalue()
                
                # Создаем файл
                import io
                file = discord.File(
                    io.BytesIO(csv_data.encode('utf-8-sig')),
                    filename=f'inactive_users_{inter.guild.name}_{days}days.csv'
                )
                
                await export_inter.followup.send(
                    f"📊 Экспорт неактивных пользователей ({len(inactive_members)} пользователей за {days} дней)",
                    file=file,
                    ephemeral=True
                )
            
            export_btn.callback = export_callback
            export_view.add_item(export_btn)
            
            embed.set_footer(text="💡 Нажмите кнопку ниже для экспорта полного списка")
            
            await inter.followup.send(embed=embed, view=export_view, ephemeral=True)
        
        select.callback = select_callback
        view.add_item(select)
        
        embed = discord.Embed(
            title="😴 Неактивные пользователи",
            description="Выберите период для поиска неактивных пользователей:",
            color=0xE67E22
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📊 Сводка", style=discord.ButtonStyle.blurple, custom_id="activity_summary", row=3)
    async def activity_summary(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Добавляем Select Menu для выбора периода
        view = discord.ui.View(timeout=180)
        
        select = discord.ui.Select(
            placeholder="Выберите период...",
            options=[
                discord.SelectOption(label="За 7 дней", emoji="📅", value="7"),
                discord.SelectOption(label="За 14 дней", emoji="📆", value="14"),
                discord.SelectOption(label="За 30 дней", emoji="🗓️", value="30"),
            ]
        )
        
        async def select_callback(inter: discord.Interaction):
            days = int(select.values[0])
            await inter.response.defer(ephemeral=True)
            
            # Получаем всех пользователей
            all_members = [m for m in inter.guild.members if not m.bot]
            
            # Получаем статистику
            all_stats = self.bot.db.get_all_users_stats(inter.guild.id, days)
            
            # Считаем активность
            very_active = [s for s in all_stats if s['period_messages'] >= 100 or s['period_voice_time'] >= 3600*10]
            active = [s for s in all_stats if (s['period_messages'] >= 20 or s['period_voice_time'] >= 3600*2) and s not in very_active]
            low_active = [s for s in all_stats if (s['period_messages'] > 0 or s['period_voice_time'] > 0) and s not in very_active and s not in active]
            
            active_user_ids = {stat['user_id'] for stat in all_stats if stat['period_messages'] > 0 or stat['period_voice_time'] > 0}
            inactive_members = [m for m in all_members if m.id not in active_user_ids]
            
            # Общая статистика
            total_messages = sum(s['period_messages'] for s in all_stats)
            total_voice_time = sum(s['period_voice_time'] for s in all_stats)
            
            # Формируем embed
            embed = discord.Embed(
                title=f"📊 Сводка активности сервера",
                description=f"Анализ активности за последние **{days} дней**",
                color=0x3498DB,
                timestamp=datetime.utcnow()
            )
            
            # Общие цифры
            embed.add_field(
                name="📈 Общая активность",
                value=f"**Сообщений:** {total_messages:,}\n**Время в войсе:** {int(total_voice_time // 3600)}ч {int((total_voice_time % 3600) // 60)}м",
                inline=True
            )
            
            embed.add_field(
                name="👥 Участники",
                value=f"**Всего:** {len(all_members)}\n**Активных:** {len(active_user_ids)}",
                inline=True
            )
            
            # Пустое поле для выравнивания
            embed.add_field(name="\u200b", value="\u200b", inline=True)
            
            # Разбивка по уровням активности
            embed.add_field(
                name="🎯 Уровни активности",
                value=f"🔥 **Очень активные:** {len(very_active)}\n⚡ **Активные:** {len(active)}\n💬 **Низкая активность:** {len(low_active)}\n😴 **Неактивные:** {len(inactive_members)}",
                inline=False
            )
            
            # Процентное соотношение
            total = len(all_members)
            if total > 0:
                very_active_pct = len(very_active) / total * 100
                active_pct = len(active) / total * 100
                low_active_pct = len(low_active) / total * 100
                inactive_pct = len(inactive_members) / total * 100
                
                # Визуальная диаграмма
                bar_length = 20
                very_bar = int(very_active_pct / 100 * bar_length)
                active_bar = int(active_pct / 100 * bar_length)
                low_bar = int(low_active_pct / 100 * bar_length)
                inactive_bar = bar_length - very_bar - active_bar - low_bar
                
                visual = f"🔥 `{'█' * very_bar}{'░' * (bar_length - very_bar)}` {very_active_pct:.1f}%\n"
                visual += f"⚡ `{'█' * active_bar}{'░' * (bar_length - active_bar)}` {active_pct:.1f}%\n"
                visual += f"💬 `{'█' * low_bar}{'░' * (bar_length - low_bar)}` {low_active_pct:.1f}%\n"
                visual += f"😴 `{'█' * inactive_bar}{'░' * (bar_length - inactive_bar)}` {inactive_pct:.1f}%"
                
                embed.add_field(
                    name="📊 Распределение активности",
                    value=visual,
                    inline=False
                )
            
            # Топ-3 самых активных
            if all_stats:
                top_messages = sorted(all_stats, key=lambda x: x['period_messages'], reverse=True)[:3]
                top_text = []
                for i, user_data in enumerate(top_messages, 1):
                    member = inter.guild.get_member(user_data['user_id'])
                    if member:
                        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
                        top_text.append(f"{emoji} {member.mention}: {user_data['period_messages']} сообщений")
                
                if top_text:
                    embed.add_field(
                        name="🏆 Топ-3 по сообщениям",
                        value="\n".join(top_text),
                        inline=False
                    )
            
            embed.set_footer(text=f"💡 Критерии: Очень активные (100+ сообщений или 10+ часов), Активные (20+ сообщений или 2+ часов)")
            
            await inter.followup.send(embed=embed, ephemeral=True)
        
        select.callback = select_callback
        view.add_item(select)
        
        embed = discord.Embed(
            title="📊 Сводка активности",
            description="Выберите период для анализа активности сервера:",
            color=0x3498DB
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

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

    @discord.ui.button(label="😴 Неактивные", style=discord.ButtonStyle.gray, custom_id="inactive_users", row=3)
    async def inactive_users(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Создаем view с select меню для периода и роли
        view = InactiveUsersView(self.bot, interaction.guild)
        
        embed = discord.Embed(
            title="😴 Неактивные пользователи",
            description="Выберите период и роль (необязательно):",
            color=0xE67E22
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📊 Сводка", style=discord.ButtonStyle.blurple, custom_id="activity_summary", row=3)
    async def activity_summary(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Создаем view с select меню для периода и роли
        view = ActivitySummaryView(self.bot, interaction.guild)
        
        embed = discord.Embed(
            title="📊 Сводка активности",
            description="Выберите период и роль (необязательно):",
            color=0x3498DB
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class PanelView(discord.ui.View):
    """Главная панель управления"""
    
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot
    
    @discord.ui.button(label="📈 Stats", style=discord.ButtonStyle.blurple, custom_id="stats_panel", row=0)
    async def stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="📈 Статистика и аналитика",
            description="Здесь вы можете просмотреть статистику пользователей и активности сервера",
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📊 Моя статистика",
            value="Посмотреть свою активность",
            inline=True
        )
        
        embed.add_field(
            name="🏆 Топ пользователей",
            value="Самые активные участники",
            inline=True
        )
        
        embed.add_field(
            name="📤 Экспорт",
            value="Скачать данные в CSV",
            inline=True
        )
        
        embed.add_field(
            name="😴 Неактивные",
            value="Найти неактивных пользователей",
            inline=True
        )
        
        embed.add_field(
            name="📊 Сводка",
            value="Общая сводка активности",
            inline=True
        )
        
        embed.set_footer(text=f"Запросил: {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        await interaction.response.edit_message(embed=embed, view=StatsView(self.bot))
    
    @discord.ui.button(label="👥 Whitelist", style=discord.ButtonStyle.green, custom_id="whitelist_panel", row=0)
    async def whitelist(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Проверка прав: только администраторы могут управлять whitelist
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "⛔ Управление whitelist доступно только администраторам!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="👥 Управление Whitelist",
            description="Whitelist дает пользователям доступ к командам управления без прав администратора",
            color=0x2ECC71,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="➕ Добавить",
            value="Добавить пользователя в whitelist",
            inline=True
        )
        
        embed.add_field(
            name="➖ Удалить",
            value="Убрать пользователя из whitelist",
            inline=True
        )
        
        embed.add_field(
            name="📋 Список",
            value="Посмотреть всех в whitelist",
            inline=True
        )
        
        embed.set_footer(text=f"Запросил: {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        await interaction.response.edit_message(embed=embed, view=WhitelistView(self.bot))
    
    @discord.ui.button(label="⚠️ Warnings", style=discord.ButtonStyle.red, custom_id="warnings_panel", row=1)  # ← НОВАЯ КНОПКА!
    async def warnings(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Проверка прав: администратор или в whitelist
        if not interaction.user.guild_permissions.administrator:
            if not self.bot.db.is_whitelisted(interaction.guild.id, interaction.user.id):
                await interaction.response.send_message(
                    "⛔ Система выговоров доступна только администраторам и whitelisted пользователям!",
                    ephemeral=True
                )
                return
        
        embed = discord.Embed(
            title="⚠️ Система выговоров",
            description="Управление выговорами и модерация сервера",
            color=0xE67E22,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="⚠️ Выдать выговор",
            value="Выдать выговор пользователю",
            inline=True
        )
        
        embed.add_field(
            name="✅ Снять выговор",
            value="Снять выговор досрочно",
            inline=True
        )
        
        embed.add_field(
            name="👤 Проверить",
            value="Проверить выговоры пользователя",
            inline=True
        )
        
        embed.add_field(
            name="📋 Список всех",
            value="Все пользователи с выговорами",
            inline=True
        )
        
        embed.add_field(
            name="📊 Статистика",
            value="Статистика выговоров сервера",
            inline=True
        )
        
        embed.add_field(
            name="\u200b",
            value="\u200b",
            inline=True
        )
        
        embed.add_field(
            name="ℹ️ Информация",
            value="• Максимум **3** выговора на пользователя\n• Автоматическое снятие через **7 дней**\n• Уведомления в DM\n• Полная история",
            inline=False
        )
        
        embed.set_footer(text=f"Запросил: {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        await interaction.response.edit_message(embed=embed, view=WarningsView(self.bot))

class WhitelistView(discord.ui.View):
    """Меню управления whitelist"""
    
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot
    
    @discord.ui.button(label="➕ Добавить", style=discord.ButtonStyle.green, custom_id="whitelist_add", row=0)
    async def add_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = WhitelistAddModal(self.bot)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="➖ Удалить", style=discord.ButtonStyle.red, custom_id="whitelist_remove", row=0)
    async def remove_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = WhitelistRemoveModal(self.bot)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📋 Список", style=discord.ButtonStyle.blurple, custom_id="whitelist_list", row=0)
    async def list_users(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # ИСПРАВЛЕНО: используем get_whitelist() вместо get_whitelisted_users()
        whitelisted = self.bot.db.get_whitelist(interaction.guild.id)
        
        if not whitelisted:
            await interaction.followup.send("📋 Whitelist пуст", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📋 Whitelist пользователей",
            description=f"Всего в whitelist: **{len(whitelisted)}**",
            color=0x2ECC71,
            timestamp=datetime.utcnow()
        )
        
        users_text = []
        # ИСПРАВЛЕНО: get_whitelist возвращает (user_id, added_by, added_at)
        for i, (user_id, added_by, added_at) in enumerate(whitelisted, 1):
            member = interaction.guild.get_member(user_id)
            if member:
                users_text.append(f"{i}. {member.mention} `{member.name}`")
            else:
                users_text.append(f"{i}. ID:{user_id} *(пользователь покинул сервер)*")
        
        # Разбиваем на части если много
        if len(users_text) <= 25:
            embed.add_field(
                name="👥 Пользователи",
                value="\n".join(users_text),
                inline=False
            )
        else:
            # Показываем первые 25
            embed.add_field(
                name=f"👥 Первые 25 из {len(users_text)}",
                value="\n".join(users_text[:25]),
                inline=False
            )
        
        embed.set_footer(text=f"Запросил: {interaction.user.name}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="🔙 Назад", style=discord.ButtonStyle.gray, custom_id="back_to_main_from_whitelist", row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🎛️ ALFA Bot Control Panel",
            description="Добро пожаловать в панель управления!\nВыберите нужный раздел, нажав на кнопку ниже.",
            color=0x5865F2,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📈 Stats",
            value="Статистика пользователей и активности",
            inline=True
        )
        
        embed.add_field(
            name="👥 Whitelist",
            value="Управление whitelist пользователями",
            inline=True
        )
        
        embed.add_field(
            name="📊 Polls",
            value="Создание и управление опросами",
            inline=True
        )
        
        embed.add_field(
            name="⚠️ Warnings",
            value="Система выговоров и модерация",
            inline=True
        )
        
        embed.set_footer(text=f"Запросил: {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        await interaction.response.edit_message(embed=embed, view=PanelView(self.bot))


class WhitelistAddModal(discord.ui.Modal, title="➕ Добавить в whitelist"):
    """Модальное окно для добавления в whitelist"""
    
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
    
    user_id = discord.ui.TextInput(
        label="ID, @упоминание или имя пользователя",
        placeholder="123456789 или @username или username",
        required=True,
        max_length=100
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        # Парсим ID пользователя
        user_input = self.user_id.value.strip()
        
        member = None
        
        # Вариант 1: Упоминание <@123456789> или <@!123456789>
        if user_input.startswith('<@') and user_input.endswith('>'):
            user_input = user_input[2:-1]
            if user_input.startswith('!'):
                user_input = user_input[1:]
            
            try:
                user_id = int(user_input)
                member = interaction.guild.get_member(user_id)
            except ValueError:
                pass
        
        # Вариант 2: Просто ID
        if not member:
            try:
                user_id = int(user_input)
                member = interaction.guild.get_member(user_id)
            except ValueError:
                pass
        
        # Вариант 3: Имя пользователя (@username или username)
        if not member:
            # Убираем @ если есть
            search_name = user_input.lstrip('@')
            
            # Ищем по точному совпадению имени
            member = discord.utils.get(interaction.guild.members, name=search_name)
            
            # Если не нашли, ищем по display_name
            if not member:
                member = discord.utils.get(interaction.guild.members, display_name=search_name)
            
            # Если не нашли, ищем по началу имени (case-insensitive)
            if not member:
                search_name_lower = search_name.lower()
                for m in interaction.guild.members:
                    if m.name.lower().startswith(search_name_lower) or m.display_name.lower().startswith(search_name_lower):
                        member = m
                        break
        
        # Если пользователь не найден
        if not member:
            await interaction.response.send_message(
                f"❌ Пользователь `{user_input}` не найден на сервере\n\n"
                f"💡 **Подсказка:**\n"
                f"• Используйте ID: `123456789`\n"
                f"• Или упоминание: скопируйте упоминание\n"
                f"• Или точное имя: `username` или `@username`",
                ephemeral=True
            )
            return
        
        # Добавляем в whitelist
        if self.bot.db.add_to_whitelist(interaction.guild.id, member.id, interaction.user.id):
            embed = discord.Embed(
                title="✅ Добавлено в whitelist",
                description=f"{member.mention} добавлен в whitelist",
                color=0x2ECC71,
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="👤 Пользователь",
                value=f"{member.mention}\n`{member.name}`",
                inline=True
            )
            
            embed.add_field(
                name="👮 Добавил",
                value=f"{interaction.user.mention}\n`{interaction.user.name}`",
                inline=True
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ {member.mention} уже в whitelist", ephemeral=True)


class WhitelistRemoveModal(discord.ui.Modal, title="➖ Удалить из whitelist"):
    """Модальное окно для удаления из whitelist"""
    
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
    
    user_id = discord.ui.TextInput(
        label="ID, @упоминание или имя пользователя",
        placeholder="123456789 или @username или username",
        required=True,
        max_length=100
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        # Парсим ID пользователя
        user_input = self.user_id.value.strip()
        
        member = None
        user_id = None
        
        # Вариант 1: Упоминание <@123456789> или <@!123456789>
        if user_input.startswith('<@') and user_input.endswith('>'):
            id_str = user_input[2:-1]
            if id_str.startswith('!'):
                id_str = id_str[1:]
            
            try:
                user_id = int(id_str)
                member = interaction.guild.get_member(user_id)
            except ValueError:
                pass
        
        # Вариант 2: Просто ID
        if not user_id:
            try:
                user_id = int(user_input)
                member = interaction.guild.get_member(user_id)
            except ValueError:
                pass
        
        # Вариант 3: Имя пользователя (@username или username)
        if not user_id:
            # Убираем @ если есть
            search_name = user_input.lstrip('@')
            
            # Ищем по точному совпадению имени
            member = discord.utils.get(interaction.guild.members, name=search_name)
            
            # Если не нашли, ищем по display_name
            if not member:
                member = discord.utils.get(interaction.guild.members, display_name=search_name)
            
            # Если не нашли, ищем по началу имени (case-insensitive)
            if not member:
                search_name_lower = search_name.lower()
                for m in interaction.guild.members:
                    if m.name.lower().startswith(search_name_lower) or m.display_name.lower().startswith(search_name_lower):
                        member = m
                        break
            
            if member:
                user_id = member.id
        
        # Если пользователь не найден
        if not user_id:
            await interaction.response.send_message(
                f"❌ Пользователь `{user_input}` не найден на сервере\n\n"
                f"💡 **Подсказка:**\n"
                f"• Используйте ID: `123456789`\n"
                f"• Или упоминание: скопируйте упоминание\n"
                f"• Или точное имя: `username` или `@username`",
                ephemeral=True
            )
            return
        
        member_name = member.mention if member else f"ID:{user_id}"
        
        # Удаляем из whitelist
        if self.bot.db.remove_from_whitelist(interaction.guild.id, user_id):
            embed = discord.Embed(
                title="✅ Удалено из whitelist",
                description=f"{member_name} удален из whitelist",
                color=0xE74C3C,
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="👤 Пользователь",
                value=member_name,
                inline=True
            )
            
            embed.add_field(
                name="👮 Удалил",
                value=f"{interaction.user.mention}\n`{interaction.user.name}`",
                inline=True
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ {member_name} не найден в whitelist", ephemeral=True)

class InactiveUsersView(discord.ui.View):
    """View для выбора периода и роли для неактивных пользователей"""
    
    def __init__(self, bot, guild):
        super().__init__(timeout=180)
        self.bot = bot
        self.guild = guild
        self.selected_days = 7
        self.selected_role = None
        
        # Добавляем селекты
        self.add_item(PeriodSelect())
        self.add_item(RoleSelect(guild))
    
    @discord.ui.button(label="🔍 Показать", style=discord.ButtonStyle.green, custom_id="show_inactive", row=2)
    async def show_inactive(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Получаем всех пользователей сервера (не ботов)
        all_members = [m for m in self.guild.members if not m.bot]
        
        # Фильтруем по роли если указана
        if self.selected_role:
            all_members = [m for m in all_members if self.selected_role in m.roles]
        
        # Получаем статистику активных пользователей
        active_stats = self.bot.db.get_all_users_stats(self.guild.id, self.selected_days)
        active_user_ids = {stat['user_id'] for stat in active_stats if stat['period_messages'] > 0 or stat['period_voice_time'] > 0}
        
        # Находим неактивных
        inactive_members = [m for m in all_members if m.id not in active_user_ids]
        
        if not inactive_members:
            role_text = f" с ролью {self.selected_role.mention}" if self.selected_role else ""
            await interaction.followup.send(f"✅ Все пользователи{role_text} были активны за последние {self.selected_days} дней!", ephemeral=True)
            return
        
        # Формируем embed
        title_suffix = f" (роль: {self.selected_role.name})" if self.selected_role else ""
        embed = discord.Embed(
            title=f"😴 Неактивные пользователи{title_suffix}",
            description=f"Пользователи без активности за последние **{self.selected_days} дней**",
            color=0xE67E22,
            timestamp=datetime.utcnow()
        )
        
        # Список неактивных (максимум 25)
        inactive_text = []
        for i, member in enumerate(inactive_members[:25], 1):
            top_role = member.top_role.name if member.top_role.name != "@everyone" else "Нет роли"
            inactive_text.append(f"{i}. {member.mention} • `{top_role}`")
        
        if inactive_text:
            if len(inactive_members) <= 25:
                embed.add_field(
                    name=f"👥 Список ({len(inactive_members)} пользователей)",
                    value="\n".join(inactive_text),
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"👥 Первые 25 из {len(inactive_members)}",
                    value="\n".join(inactive_text),
                    inline=False
                )
        
        # Статистика
        total_members = len(all_members)
        inactive_percent = (len(inactive_members) / total_members * 100) if total_members > 0 else 0
        
        embed.add_field(
            name="📊 Статистика",
            value=f"**Всего участников:** {total_members}\n**Неактивных:** {len(inactive_members)} ({inactive_percent:.1f}%)\n**Активных:** {len(active_user_ids)} ({100-inactive_percent:.1f}%)",
            inline=False
        )
        
        # Кнопка экспорта
        export_view = discord.ui.View(timeout=60)
        export_btn = discord.ui.Button(label="📤 Экспорт в CSV", style=discord.ButtonStyle.green)
        
        async def export_callback(export_inter: discord.Interaction):
            await export_inter.response.defer(ephemeral=True)
            
            # Формируем CSV
            from io import StringIO
            import csv
            
            output = StringIO()
            writer = csv.writer(output)
            
            writer.writerow(['Inactive Users Report'])
            writer.writerow(['Server:', self.guild.name])
            writer.writerow(['Period:', f'{self.selected_days} days'])
            if self.selected_role:
                writer.writerow(['Filtered by role:', self.selected_role.name])
            writer.writerow(['Total Members:', len(all_members)])
            writer.writerow(['Inactive Members:', len(inactive_members)])
            writer.writerow(['Report Date:', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')])
            writer.writerow([])
            
            writer.writerow([
                'Rank',
                'Username',
                'Display Name',
                'User ID',
                'Top Role',
                'All Roles',
                'Joined Server',
                'Account Created'
            ])
            
            for i, member in enumerate(inactive_members, 1):
                top_role = member.top_role.name if member.top_role.name != "@everyone" else "No Role"
                all_roles = ", ".join([r.name for r in member.roles if r.name != "@everyone"])
                if not all_roles:
                    all_roles = "No Roles"
                joined = member.joined_at.strftime('%Y-%m-%d') if member.joined_at else "Unknown"
                created = member.created_at.strftime('%Y-%m-%d')
                
                writer.writerow([
                    i,
                    member.name,
                    member.display_name,
                    member.id,
                    top_role,
                    all_roles,
                    joined,
                    created
                ])
            
            csv_data = output.getvalue()
            
            # Создаем файл
            import io
            role_suffix = f"_role_{self.selected_role.name}" if self.selected_role else ""
            file = discord.File(
                io.BytesIO(csv_data.encode('utf-8-sig')),
                filename=f'inactive_users_{self.guild.name}_{self.selected_days}days{role_suffix}.csv'
            )
            
            role_text = f" с ролью **{self.selected_role.name}**" if self.selected_role else ""
            await export_inter.followup.send(
                f"📊 Экспорт неактивных пользователей{role_text} ({len(inactive_members)} пользователей за {self.selected_days} дней)",
                file=file,
                ephemeral=True
            )
        
        export_btn.callback = export_callback
        export_view.add_item(export_btn)
        
        embed.set_footer(text="💡 Нажмите кнопку ниже для экспорта полного списка")
        
        await interaction.followup.send(embed=embed, view=export_view, ephemeral=True)


class ActivitySummaryView(discord.ui.View):
    """View для выбора периода и роли для сводки активности"""
    
    def __init__(self, bot, guild):
        super().__init__(timeout=180)
        self.bot = bot
        self.guild = guild
        self.selected_days = 7
        self.selected_role = None
        
        # Добавляем селекты
        self.add_item(PeriodSelect())
        self.add_item(RoleSelect(guild))
    
    @discord.ui.button(label="🔍 Показать", style=discord.ButtonStyle.green, custom_id="show_summary", row=2)
    async def show_summary(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Получаем всех пользователей
        all_members = [m for m in self.guild.members if not m.bot]
        
        # Фильтруем по роли если указана
        if self.selected_role:
            all_members = [m for m in all_members if self.selected_role in m.roles]
        
        # Получаем статистику
        all_stats = self.bot.db.get_all_users_stats(self.guild.id, self.selected_days)
        
        # Фильтруем статистику по роли
        if self.selected_role:
            filtered_user_ids = {m.id for m in all_members}
            all_stats = [s for s in all_stats if s['user_id'] in filtered_user_ids]
        
        # Считаем активность
        very_active = [s for s in all_stats if s['period_messages'] >= 100 or s['period_voice_time'] >= 3600*10]
        active = [s for s in all_stats if (s['period_messages'] >= 20 or s['period_voice_time'] >= 3600*2) and s not in very_active]
        low_active = [s for s in all_stats if (s['period_messages'] > 0 or s['period_voice_time'] > 0) and s not in very_active and s not in active]
        
        active_user_ids = {stat['user_id'] for stat in all_stats if stat['period_messages'] > 0 or stat['period_voice_time'] > 0}
        inactive_members = [m for m in all_members if m.id not in active_user_ids]
        
        # Общая статистика
        total_messages = sum(s['period_messages'] for s in all_stats)
        total_voice_time = sum(s['period_voice_time'] for s in all_stats)
        
        # Формируем embed
        title_suffix = f" (роль: {self.selected_role.name})" if self.selected_role else ""
        embed = discord.Embed(
            title=f"📊 Сводка активности сервера{title_suffix}",
            description=f"Анализ активности за последние **{self.selected_days} дней**",
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )
        
        # Общие цифры
        embed.add_field(
            name="📈 Общая активность",
            value=f"**Сообщений:** {total_messages:,}\n**Время в войсе:** {int(total_voice_time // 3600)}ч {int((total_voice_time % 3600) // 60)}м",
            inline=True
        )
        
        embed.add_field(
            name="👥 Участники",
            value=f"**Всего:** {len(all_members)}\n**Активных:** {len(active_user_ids)}",
            inline=True
        )
        
        # Пустое поле для выравнивания
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        
        # Разбивка по уровням активности
        embed.add_field(
            name="🎯 Уровни активности",
            value=f"🔥 **Очень активные:** {len(very_active)}\n⚡ **Активные:** {len(active)}\n💬 **Низкая активность:** {len(low_active)}\n😴 **Неактивные:** {len(inactive_members)}",
            inline=False
        )
        
        # Процентное соотношение
        total = len(all_members)
        if total > 0:
            very_active_pct = len(very_active) / total * 100
            active_pct = len(active) / total * 100
            low_active_pct = len(low_active) / total * 100
            inactive_pct = len(inactive_members) / total * 100
            
            # Визуальная диаграмма
            bar_length = 20
            very_bar = int(very_active_pct / 100 * bar_length)
            active_bar = int(active_pct / 100 * bar_length)
            low_bar = int(low_active_pct / 100 * bar_length)
            inactive_bar = bar_length - very_bar - active_bar - low_bar
            
            visual = f"🔥 `{'█' * very_bar}{'░' * (bar_length - very_bar)}` {very_active_pct:.1f}%\n"
            visual += f"⚡ `{'█' * active_bar}{'░' * (bar_length - active_bar)}` {active_pct:.1f}%\n"
            visual += f"💬 `{'█' * low_bar}{'░' * (bar_length - low_bar)}` {low_active_pct:.1f}%\n"
            visual += f"😴 `{'█' * inactive_bar}{'░' * (bar_length - inactive_bar)}` {inactive_pct:.1f}%"
            
            embed.add_field(
                name="📊 Распределение активности",
                value=visual,
                inline=False
            )
        
        # Топ-3 самых активных
        if all_stats:
            top_messages = sorted(all_stats, key=lambda x: x['period_messages'], reverse=True)[:3]
            top_text = []
            for i, user_data in enumerate(top_messages, 1):
                member = self.guild.get_member(user_data['user_id'])
                if member:
                    emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
                    top_text.append(f"{emoji} {member.mention}: {user_data['period_messages']} сообщений")
            
            if top_text:
                embed.add_field(
                    name="🏆 Топ-3 по сообщениям",
                    value="\n".join(top_text),
                    inline=False
                )
        
        embed.set_footer(text=f"💡 Критерии: Очень активные (100+ сообщений или 10+ часов), Активные (20+ сообщений или 2+ часов)")
        
        await interaction.followup.send(embed=embed, ephemeral=True)


class PeriodSelect(discord.ui.Select):
    """Select для выбора периода"""
    
    def __init__(self):
        options = [
            discord.SelectOption(label="За 7 дней", emoji="📅", value="7", default=True),
            discord.SelectOption(label="За 14 дней", emoji="📆", value="14"),
            discord.SelectOption(label="За 30 дней", emoji="🗓️", value="30"),
        ]
        super().__init__(placeholder="Выберите период...", options=options, row=0)
    
    async def callback(self, interaction: discord.Interaction):
        self.view.selected_days = int(self.values[0])
        await interaction.response.send_message(f"✅ Выбран период: **{self.values[0]} дней**", ephemeral=True, delete_after=3)


class RoleSelect(discord.ui.Select):
    """Select для выбора роли"""
    
    def __init__(self, guild):
        # Берем первые 24 роли (лимит Discord - 25 опций, одна будет "Все роли")
        roles = [r for r in guild.roles if r.name != "@everyone"][:24]
        
        options = [
            discord.SelectOption(label="Все роли", emoji="👥", value="all", default=True)
        ]
        
        for role in roles:
            options.append(
                discord.SelectOption(
                    label=role.name[:100],  # Ограничение Discord
                    value=str(role.id)
                )
            )
        
        super().__init__(placeholder="Выберите роль (необязательно)...", options=options, row=1)
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "all":
            self.view.selected_role = None
            await interaction.response.send_message(f"✅ Фильтр по ролям сброшен", ephemeral=True, delete_after=3)
        else:
            role_id = int(self.values[0])
            role = interaction.guild.get_role(role_id)
            if role:
                self.view.selected_role = role
                await interaction.response.send_message(f"✅ Выбрана роль: **{role.name}**", ephemeral=True, delete_after=3)
            else:
                await interaction.response.send_message(f"❌ Роль не найдена", ephemeral=True, delete_after=3)


# Добавьте этот класс в panel.py

class WarningsView(discord.ui.View):
    """Интерактивное меню для системы выговоров"""
    
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot
    
    @discord.ui.button(label="⚠️ Выдать выговор", style=discord.ButtonStyle.red, custom_id="warn_user", row=0)
    async def warn_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Показываем модальное окно для выдачи выговора
        modal = WarnUserModal(self.bot)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="✅ Снять выговор", style=discord.ButtonStyle.green, custom_id="unwarn_user", row=0)
    async def unwarn_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Показываем модальное окно для снятия выговора
        modal = UnwarnModal(self.bot)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="👤 Проверить пользователя", style=discord.ButtonStyle.blurple, custom_id="check_warnings", row=0)
    async def check_warnings(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Показываем модальное окно для проверки выговоров
        modal = CheckWarningsModal(self.bot)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📋 Список всех выговоров", style=discord.ButtonStyle.gray, custom_id="warnings_list", row=1)
    async def warnings_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Получаем cog выговоров
        warnings_cog = self.bot.get_cog('WarningSystem')
        if not warnings_cog:
            await interaction.followup.send("❌ Система выговоров не загружена", ephemeral=True)
            return
        
        warnings_data = warnings_cog.get_all_warnings(interaction.guild.id, active_only=True)
        
        if not warnings_data:
            await interaction.followup.send("✅ На сервере нет пользователей с активными выговорами!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📋 Список пользователей с выговорами",
            description=f"Всего пользователей: **{len(warnings_data)}**",
            color=0xE67E22,
            timestamp=datetime.utcnow()
        )
        
        # Группируем по количеству выговоров
        three_warns = []
        two_warns = []
        one_warn = []
        
        for user_id, count in warnings_data:
            member = interaction.guild.get_member(user_id)
            if member:
                member_text = f"{member.mention} `{member.name}`"
            else:
                member_text = f"ID:{user_id}"
            
            if count == 3:
                three_warns.append(member_text)
            elif count == 2:
                two_warns.append(member_text)
            elif count == 1:
                one_warn.append(member_text)
        
        if three_warns:
            embed.add_field(
                name="🚨 3 выговора (критично!)",
                value="\n".join(three_warns[:10]),
                inline=False
            )
        
        if two_warns:
            embed.add_field(
                name="⚠️ 2 выговора",
                value="\n".join(two_warns[:15]),
                inline=False
            )
        
        if one_warn:
            embed.add_field(
                name="⚡ 1 выговор",
                value="\n".join(one_warn[:10]) + (f"\n*...и еще {len(one_warn)-10}*" if len(one_warn) > 10 else ""),
                inline=False
            )
        
        embed.set_footer(text="💡 Используйте кнопку 'Проверить пользователя' для деталей")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="📊 Статистика выговоров", style=discord.ButtonStyle.gray, custom_id="warnings_stats", row=1)
    async def warnings_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Получаем cog выговоров
        warnings_cog = self.bot.get_cog('WarningSystem')
        if not warnings_cog:
            await interaction.followup.send("❌ Система выговоров не загружена", ephemeral=True)
            return
        
        import sqlite3
        conn = sqlite3.connect(self.bot.db.db_path)
        cursor = conn.cursor()
        
        # Общая статистика
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active,
                COUNT(DISTINCT user_id) as unique_users
            FROM warnings
            WHERE guild_id = ?
        ''', (interaction.guild.id,))
        
        stats = cursor.fetchone()
        total_warnings, active_warnings, unique_users = stats
        
        # Топ нарушителей (всего)
        cursor.execute('''
            SELECT user_id, COUNT(*) as total_count
            FROM warnings
            WHERE guild_id = ?
            GROUP BY user_id
            ORDER BY total_count DESC
            LIMIT 5
        ''', (interaction.guild.id,))
        
        top_offenders = cursor.fetchall()
        
        # Топ модераторов
        cursor.execute('''
            SELECT warned_by, COUNT(*) as warnings_given
            FROM warnings
            WHERE guild_id = ?
            GROUP BY warned_by
            ORDER BY warnings_given DESC
            LIMIT 5
        ''', (interaction.guild.id,))
        
        top_moderators = cursor.fetchall()
        
        conn.close()
        
        embed = discord.Embed(
            title="📊 Статистика выговоров сервера",
            description=f"Полная информация по системе выговоров",
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📈 Общая статистика",
            value=f"**Всего выговоров:** {total_warnings}\n**Активных:** {active_warnings}\n**Пользователей:** {unique_users}",
            inline=False
        )
        
        if top_offenders:
            offenders_text = []
            for i, (user_id, count) in enumerate(top_offenders, 1):
                member = interaction.guild.get_member(user_id)
                name = member.mention if member else f"ID:{user_id}"
                offenders_text.append(f"{i}. {name} - **{count}** выговоров")
            
            embed.add_field(
                name="🔥 Топ-5 нарушителей (за все время)",
                value="\n".join(offenders_text),
                inline=False
            )
        
        if top_moderators:
            mods_text = []
            for i, (mod_id, count) in enumerate(top_moderators, 1):
                member = interaction.guild.get_member(mod_id)
                name = member.mention if member else f"ID:{mod_id}"
                mods_text.append(f"{i}. {name} - **{count}** выданных")
            
            embed.add_field(
                name="👮 Топ-5 модераторов",
                value="\n".join(mods_text),
                inline=False
            )
        
        embed.set_footer(text="💡 Выговоры снимаются автоматически через 7 дней")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="🔙 Назад", style=discord.ButtonStyle.red, custom_id="back_to_main_from_warnings", row=2)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Возвращаемся к главной панели
        embed = discord.Embed(
            title="🎛️ ALFA Bot Control Panel",
            description="Добро пожаловать в панель управления!\nВыберите нужный раздел, нажав на кнопку ниже.",
            color=0x5865F2,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📈 Stats",
            value="Статистика пользователей и активности",
            inline=True
        )
        
        embed.add_field(
            name="👥 Whitelist",
            value="Управление whitelist пользователями",
            inline=True
        )
        
        embed.add_field(
            name="📊 Polls",
            value="Создание и управление опросами",
            inline=True
        )
        
        embed.add_field(
            name="⚠️ Warnings",
            value="Система выговоров и модерация",
            inline=True
        )
        
        embed.set_footer(text=f"Запросил: {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        await interaction.response.edit_message(embed=embed, view=PanelView(self.bot))


class WarnUserModal(discord.ui.Modal, title="⚠️ Выдать выговор"):
    """Модальное окно для выдачи выговора"""
    
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
    
    user_id = discord.ui.TextInput(
        label="ID, @упоминание или имя пользователя",
        placeholder="123456789 или @username или username",
        required=True,
        max_length=100
    )
    
    reason = discord.ui.TextInput(
        label="Причина выговора",
        placeholder="Например: Спам в чате, нарушение правил...",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Парсим ID пользователя
        user_input = self.user_id.value.strip()
        
        member = None
        
        # Вариант 1: Упоминание <@123456789> или <@!123456789>
        if user_input.startswith('<@') and user_input.endswith('>'):
            user_input = user_input[2:-1]
            if user_input.startswith('!'):
                user_input = user_input[1:]
            
            try:
                user_id = int(user_input)
                member = interaction.guild.get_member(user_id)
            except ValueError:
                pass
        
        # Вариант 2: Просто ID
        if not member:
            try:
                user_id = int(user_input)
                member = interaction.guild.get_member(user_id)
            except ValueError:
                pass
        
        # Вариант 3: Имя пользователя (@username или username)
        if not member:
            # Убираем @ если есть
            search_name = user_input.lstrip('@')
            
            # Ищем по точному совпадению имени
            member = discord.utils.get(interaction.guild.members, name=search_name)
            
            # Если не нашли, ищем по display_name
            if not member:
                member = discord.utils.get(interaction.guild.members, display_name=search_name)
            
            # Если не нашли, ищем по началу имени (case-insensitive)
            if not member:
                search_name_lower = search_name.lower()
                for m in interaction.guild.members:
                    if m.name.lower().startswith(search_name_lower) or m.display_name.lower().startswith(search_name_lower):
                        member = m
                        break
        
        # Если пользователь не найден
        if not member:
            await interaction.followup.send(
                f"❌ Пользователь `{user_input}` не найден на сервере\n\n"
                f"💡 **Подсказка:**\n"
                f"• Используйте ID: `123456789`\n"
                f"• Или упоминание: скопируйте упоминание\n"
                f"• Или точное имя: `username` или `@username`",
                ephemeral=True
            )
            return
        
        # Нельзя выдать выговор самому себе
        if member.id == interaction.user.id:
            await interaction.followup.send("❌ Вы не можете выдать выговор самому себе!", ephemeral=True)
            return
        
        # Нельзя выдать выговор боту
        if member.bot:
            await interaction.followup.send("❌ Нельзя выдать выговор боту!", ephemeral=True)
            return
        
        # Получаем cog выговоров
        warnings_cog = self.bot.get_cog('WarningSystem')
        if not warnings_cog:
            await interaction.followup.send("❌ Система выговоров не загружена", ephemeral=True)
            return
        
        # Проверяем текущее количество выговоров
        current_warnings = warnings_cog.get_active_warnings_count(interaction.guild.id, member.id)
        
        if current_warnings >= 3:
            await interaction.followup.send(f"⚠️ У {member.mention} уже **3** активных выговора (максимум)!", ephemeral=True)
            return
        
        # Добавляем выговор
        success, result = warnings_cog.add_warning(interaction.guild.id, member.id, interaction.user.id, self.reason.value)
        
        if not success:
            await interaction.followup.send(f"❌ Ошибка при выдаче выговора: {result}", ephemeral=True)
            return
        
        warning_id = result
        new_count = current_warnings + 1
        
        # Формируем embed
        embed = discord.Embed(
            title="⚠️ Выговор выдан",
            description=f"{member.mention} получил выговор",
            color=0xE67E22 if new_count < 3 else 0xE74C3C,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="👤 Пользователь",
            value=f"{member.mention}\n`{member.name}`",
            inline=True
        )
        
        embed.add_field(
            name="👮 Выдал",
            value=f"{interaction.user.mention}\n`{interaction.user.name}`",
            inline=True
        )
        
        embed.add_field(
            name="📊 Статус",
            value=f"**{new_count}**/3 выговора",
            inline=True
        )
        
        embed.add_field(
            name="📝 Причина",
            value=self.reason.value,
            inline=False
        )
        
        embed.add_field(
            name="⏰ Срок действия",
            value="7 дней (снимается автоматически)",
            inline=False
        )
        
        embed.set_footer(text=f"ID выговора: {warning_id}")
        
        # Предупреждение при 3 выговорах
        if new_count == 3:
            embed.add_field(
                name="🚨 ВНИМАНИЕ",
                value="У пользователя **3 выговора**! Рассмотрите возможность применения санкций.",
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Пытаемся отправить DM пользователю
        try:
            dm_embed = discord.Embed(
                title="⚠️ Вы получили выговор",
                description=f"Вам выдан выговор на сервере **{interaction.guild.name}**",
                color=0xE67E22 if new_count < 3 else 0xE74C3C,
                timestamp=datetime.utcnow()
            )
            
            dm_embed.add_field(
                name="📝 Причина",
                value=self.reason.value,
                inline=False
            )
            
            dm_embed.add_field(
                name="📊 Ваш статус",
                value=f"Активных выговоров: **{new_count}**/3",
                inline=True
            )
            
            dm_embed.add_field(
                name="⏰ Информация",
                value="Выговор автоматически снимется через 7 дней",
                inline=True
            )
            
            if new_count == 3:
                dm_embed.add_field(
                    name="🚨 ПРЕДУПРЕЖДЕНИЕ",
                    value="У вас максимальное количество выговоров! Следующее нарушение может привести к санкциям.",
                    inline=False
                )
            
            await member.send(embed=dm_embed)
        except:
            pass


class UnwarnModal(discord.ui.Modal, title="✅ Снять выговор"):
    """Модальное окно для снятия выговора"""
    
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
    
    warning_id = discord.ui.TextInput(
        label="ID выговора",
        placeholder="Например: 42",
        required=True,
        max_length=20
    )
    
    reason = discord.ui.TextInput(
        label="Причина снятия (необязательно)",
        placeholder="Например: Пользователь исправился",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            warn_id = int(self.warning_id.value.strip())
        except ValueError:
            await interaction.followup.send("❌ Неверный формат ID выговора", ephemeral=True)
            return
        
        # Получаем cog выговоров
        warnings_cog = self.bot.get_cog('WarningSystem')
        if not warnings_cog:
            await interaction.followup.send("❌ Система выговоров не загружена", ephemeral=True)
            return
        
        # Получаем информацию о выговоре
        import sqlite3
        conn = sqlite3.connect(self.bot.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, warned_by, reason, is_active
            FROM warnings
            WHERE id = ?
        ''', (warn_id,))
        
        warning_data = cursor.fetchone()
        conn.close()
        
        if not warning_data:
            await interaction.followup.send(f"❌ Выговор с ID `{warn_id}` не найден", ephemeral=True)
            return
        
        user_id, warned_by, warn_reason, is_active = warning_data
        
        if not is_active:
            await interaction.followup.send(f"⚠️ Выговор `{warn_id}` уже снят", ephemeral=True)
            return
        
        # Снимаем выговор
        removal_reason = self.reason.value if self.reason.value else "Снят модератором"
        
        if warnings_cog.remove_warning(warn_id, interaction.user.id, removal_reason):
            member = interaction.guild.get_member(user_id)
            member_name = member.mention if member else f"ID:{user_id}"
            
            # Получаем новое количество выговоров
            remaining = warnings_cog.get_active_warnings_count(interaction.guild.id, user_id)
            
            embed = discord.Embed(
                title="✅ Выговор снят",
                description=f"Выговор `{warn_id}` снят с пользователя {member_name}",
                color=0x2ECC71,
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="👤 Пользователь",
                value=member_name,
                inline=True
            )
            
            embed.add_field(
                name="👮 Снял",
                value=f"{interaction.user.mention}\n`{interaction.user.name}`",
                inline=True
            )
            
            embed.add_field(
                name="📊 Осталось",
                value=f"**{remaining}**/3 выговора",
                inline=True
            )
            
            embed.add_field(
                name="📝 Причина снятия",
                value=removal_reason,
                inline=False
            )
            
            embed.add_field(
                name="📋 Был выдан за",
                value=warn_reason,
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Уведомляем пользователя
            if member:
                try:
                    dm_embed = discord.Embed(
                        title="✅ Выговор снят",
                        description=f"С вас снят выговор на сервере **{interaction.guild.name}**",
                        color=0x2ECC71,
                        timestamp=datetime.utcnow()
                    )
                    
                    dm_embed.add_field(
                        name="📊 Текущий статус",
                        value=f"Активных выговоров: **{remaining}**/3",
                        inline=False
                    )
                    
                    await member.send(embed=dm_embed)
                except:
                    pass
        else:
            await interaction.followup.send(f"❌ Не удалось снять выговор `{warn_id}`", ephemeral=True)


class CheckWarningsModal(discord.ui.Modal, title="👤 Проверить выговоры"):
    """Модальное окно для проверки выговоров пользователя"""
    
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
    
    user_id = discord.ui.TextInput(
        label="ID, @упоминание или имя пользователя",
        placeholder="123456789 или @username или username",
        required=True,
        max_length=100
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Парсим ID пользователя
        user_input = self.user_id.value.strip()
        
        member = None
        user_id = None
        
        # Вариант 1: Упоминание <@123456789> или <@!123456789>
        if user_input.startswith('<@') and user_input.endswith('>'):
            id_str = user_input[2:-1]
            if id_str.startswith('!'):
                id_str = id_str[1:]
            
            try:
                user_id = int(id_str)
                member = interaction.guild.get_member(user_id)
            except ValueError:
                pass
        
        # Вариант 2: Просто ID
        if not user_id:
            try:
                user_id = int(user_input)
                member = interaction.guild.get_member(user_id)
            except ValueError:
                pass
        
        # Вариант 3: Имя пользователя (@username или username)
        if not user_id:
            # Убираем @ если есть
            search_name = user_input.lstrip('@')
            
            # Ищем по точному совпадению имени
            member = discord.utils.get(interaction.guild.members, name=search_name)
            
            # Если не нашли, ищем по display_name
            if not member:
                member = discord.utils.get(interaction.guild.members, display_name=search_name)
            
            # Если не нашли, ищем по началу имени (case-insensitive)
            if not member:
                search_name_lower = search_name.lower()
                for m in interaction.guild.members:
                    if m.name.lower().startswith(search_name_lower) or m.display_name.lower().startswith(search_name_lower):
                        member = m
                        break
            
            if member:
                user_id = member.id
        
        # Если не найден
        if not user_id:
            await interaction.followup.send(
                f"❌ Пользователь `{user_input}` не найден на сервере\n\n"
                f"💡 **Подсказка:**\n"
                f"• Используйте ID: `123456789`\n"
                f"• Или упоминание: скопируйте упоминание\n"
                f"• Или точное имя: `username` или `@username`",
                ephemeral=True
            )
            return
        
        target = member if member else None
        
        if not target:
            await interaction.followup.send(f"❌ Пользователь с ID `{user_id}` не найден на сервере", ephemeral=True)
            return
        
        # Получаем cog выговоров
        warnings_cog = self.bot.get_cog('WarningSystem')
        if not warnings_cog:
            await interaction.followup.send("❌ Система выговоров не загружена", ephemeral=True)
            return
        
        # Получаем все выговоры
        warnings = warnings_cog.get_user_warnings(interaction.guild.id, target.id)
        
        if not warnings:
            await interaction.followup.send(f"✅ У {target.mention} нет выговоров!", ephemeral=True)
            return
        
        # Считаем активные
        active_count = sum(1 for w in warnings if (len(w) == 5 or w[5] == 1))
        
        embed = discord.Embed(
            title=f"📋 Выговоры пользователя",
            description=f"{target.mention}",
            color=0xE67E22 if active_count > 0 else 0x2ECC71,
            timestamp=datetime.utcnow()
        )
        
        embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)
        
        embed.add_field(
            name="📊 Статус",
            value=f"**Активных:** {active_count}/3\n**Всего:** {len(warnings)}",
            inline=False
        )
        
        # Показываем активные выговоры
        active_warnings = [w for w in warnings if (len(w) == 5 or w[5] == 1)]
        
        if active_warnings:
            for w in active_warnings[:5]:  # Максимум 5
                from datetime import datetime as dt, timedelta
                
                warning_id = w[0]
                warned_by_id = w[1]
                reason = w[2]
                warned_at = dt.fromisoformat(w[3])
                expires_at = dt.fromisoformat(w[4])
                
                warner = interaction.guild.get_member(warned_by_id)
                warner_name = warner.name if warner else f"ID:{warned_by_id}"
                
                time_left = expires_at - dt.utcnow()
                days_left = time_left.days
                hours_left = int(time_left.seconds // 3600)
                
                embed.add_field(
                    name=f"⚠️ Выговор #{warning_id}",
                    value=f"**Причина:** {reason}\n**Выдал:** {warner_name}\n**Дата:** {warned_at.strftime('%d.%m.%Y %H:%M')}\n**Снимется через:** {days_left}д {hours_left}ч",
                    inline=False
                )
        
        # Показываем историю (снятые)
        inactive_warnings = [w for w in warnings if len(w) > 5 and w[5] == 0]
        
        if inactive_warnings and len(inactive_warnings) > 0:
            history_text = []
            for w in inactive_warnings[:3]:  # Максимум 3 из истории
                warning_id = w[0]
                reason = w[2]
                removal_reason = w[8] if len(w) > 8 else "Не указана"
                history_text.append(f"`#{warning_id}` - {reason[:30]}... | Снят: {removal_reason[:30]}")
            
            if history_text:
                embed.add_field(
                    name="📜 История (снятые)",
                    value="\n".join(history_text),
                    inline=False
                )
        
        embed.set_footer(text=f"Запросил: {interaction.user.name}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)

class Panel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="panel", description="🎛️ Панель управления ALFA Bot")
    async def panel(self, interaction: discord.Interaction):
        # Проверка прав: администратор или в whitelist
        if not interaction.user.guild_permissions.administrator:
            if not self.bot.db.is_whitelisted(interaction.guild.id, interaction.user.id):
                await interaction.response.send_message(
                    "❌ У вас нет прав для использования панели управления!\n"
                    "Панель доступна только администраторам и пользователям в whitelist.",
                    ephemeral=True
                )
                return
        
        embed = discord.Embed(
            title="🎛️ ALFA Bot Control Panel",
            description="Добро пожаловать в панель управления!\nВыберите нужный раздел, нажав на кнопку ниже.",
            color=0x5865F2,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📈 Stats",
            value="Статистика пользователей и активности",
            inline=True
        )
        
        embed.add_field(
            name="👥 Whitelist",
            value="Управление whitelist пользователями",
            inline=True
        )
        
        embed.add_field(
            name="📊 Polls",
            value="Создание и управление опросами",
            inline=True
        )
        
        embed.add_field(
            name="⚠️ Warnings",  # ← НОВОЕ!
            value="Система выговоров и модерация",
            inline=True
        )
        
        embed.set_footer(text=f"Запросил: {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        await interaction.response.send_message(embed=embed, view=PanelView(self.bot), ephemeral=True)



async def setup(bot):
    await bot.add_cog(Panel(bot))