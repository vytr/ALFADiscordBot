import discord
from discord.ext import commands, tasks
from datetime import datetime
from utils import is_admin_or_whitelisted
import io
import csv
from io import StringIO

class Stats(commands.Cog):
    """Статистика пользователей"""

    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.cleanup_task.start()

    def cog_unload(self):
        self.cleanup_task.cancel()

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        """Ежедневная очистка старых данных"""
        deleted = self.db.cleanup_old_data()
        print(f"Cleaned up {deleted} old records")

    @cleanup_task.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message):
        """Отслеживание сообщений"""
        # Игнорируем сообщения от ботов
        if message.author.bot:
            return

        # Игнорируем DM
        if not message.guild:
            return

        # Логируем сообщение
        self.db.log_message(message.guild.id, message.author.id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Отслеживание активности в голосовых каналах"""
        # Игнорируем ботов
        if member.bot:
            return

        guild_id = member.guild.id
        user_id = member.id

        # Пользователь присоединился к каналу
        if before.channel is None and after.channel is not None:
            self.db.start_voice_session(guild_id, user_id, after.channel.id)
            print(f"Voice session started: {member.name} -> {after.channel.name}")

        # Пользователь покинул канал
        elif before.channel is not None and after.channel is None:
            self.db.end_voice_session(guild_id, user_id, before.channel.id)
            print(f"Voice session ended: {member.name} <- {before.channel.name}")

        # Пользователь переключился между каналами
        elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            self.db.end_voice_session(guild_id, user_id, before.channel.id)
            self.db.start_voice_session(guild_id, user_id, after.channel.id)
            print(f"Voice channel switched: {member.name} {before.channel.name} -> {after.channel.name}")

    @commands.command(name='alfa_stats')
    @is_admin_or_whitelisted()
    async def stats(self, ctx, member: discord.Member = None, days: int = None):
        """Показать статистику пользователя. Формат: !stats [@user] [7/14/30]"""
        await ctx.message.delete()

        # Если пользователь не указан - показываем статистику автора
        if member is None:
            member = ctx.author

        # Проверяем допустимость дней
        if days and days not in [7, 14, 30]:
            await ctx.send("❌ Допустимые периоды: 7, 14 или 30 дней")
            return

        # Получаем статистику
        stats = self.db.get_user_stats(ctx.guild.id, member.id, days)

        if not stats:
            await ctx.send(f"📊 Нет данных для {member.mention}")
            return

        # Формируем embed
        period_text = f"за последние {days} дней" if days else "за все время"
        embed = discord.Embed(
            title=f"📊 Статистика {member.display_name}",
            description=f"Статистика активности {period_text}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        # Сообщения
        if days:
            embed.add_field(
                name="💬 Сообщения",
                value=f"**{period_text}:** {stats['period_messages']}\n**Всего:** {stats['total_messages']}",
                inline=False
            )
        else:
            embed.add_field(
                name="💬 Сообщения",
                value=f"**Всего:** {stats['total_messages']}",
                inline=False
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
                value=f"**{period_text}:** {hours_period}ч {minutes_period}м\n**Всего:** {hours_total}ч {minutes_total}м",
                inline=False
            )
        else:
            embed.add_field(
                name="🎤 Голосовые каналы",
                value=f"**Всего:** {hours_total}ч {minutes_total}м",
                inline=False
            )

        # Топ каналов
        if stats['voice_by_channel']:
            top_channels = []
            for channel_id, duration in stats['voice_by_channel'][:5]:
                channel = ctx.guild.get_channel(channel_id)
                channel_name = channel.name if channel else f"ID:{channel_id}"
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                top_channels.append(f"**{channel_name}:** {hours}ч {minutes}м")

            embed.add_field(
                name="🏆 Топ голосовых каналов",
                value="\n".join(top_channels),
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.command(name='alfa_stats_export')
    @is_admin_or_whitelisted()
    async def stats_export(self, ctx, member: discord.Member = None, days: int = None):
        """Экспортировать статистику в CSV. Формат: !stats_export [@user] [7/14/30]"""
        await ctx.message.delete()

        # Если пользователь не указан - показываем статистику автора
        if member is None:
            member = ctx.author

        # Проверяем допустимость дней
        if days and days not in [7, 14, 30]:
            await ctx.send("❌ Допустимые периоды: 7, 14 или 30 дней")
            return

        # Получаем статистику
        stats = self.db.get_user_stats(ctx.guild.id, member.id, days)

        if not stats:
            await ctx.send(f"📊 Нет данных для {member.mention}")
            return

        # Формируем CSV
        output = StringIO()
        writer = csv.writer(output)

        period_text = f"{days} days" if days else "all time"

        writer.writerow(['User Statistics'])
        writer.writerow(['User:', member.display_name])
        writer.writerow(['User ID:', member.id])
        writer.writerow(['Period:', period_text])
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
        writer.writerow(['Total Voice Time (seconds):', int(stats['total_voice_time'])])
        writer.writerow([])

        writer.writerow(['Voice Channels'])
        writer.writerow(['Channel Name', 'Time (seconds)', 'Time (formatted)'])
        for channel_id, duration in stats['voice_by_channel']:
            channel = ctx.guild.get_channel(channel_id)
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

        await ctx.send(f"📊 Экспорт статистики {member.mention}", file=file)

    @commands.command(name='alfa_stats_all')
    @is_admin_or_whitelisted()
    async def stats_all(self, ctx, days: int = None, role: discord.Role = None):
        """Показать статистику всех пользователей. Формат: !stats_all [7/14/30]"""
        await ctx.message.delete()

        # Проверяем допустимость дней
        if days and days not in [7, 14, 30]:
            await ctx.send("❌ Допустимые периоды: 7, 14 или 30 дней")
            return

        # Получаем статистику всех пользователей
        all_stats = self.db.get_all_users_stats(ctx.guild.id, days)
        filtered = []
        if role:
            for user_data in all_stats:
                member = ctx.guild.get_member(user_data['user_id'])
                if not member:
                    try:
                        member = await ctx.guild.fetch_member(int(user_data['user_id']))
                    except discord.NotFound:
                        continue
                if role in member.roles:
                   filtered.append(user_data)
        else:
            filtered = all_stats
            

        if not filtered:
            await ctx.send("📊 Нет данных о пользователях")
            return

        # Ограничиваем до топ-25 для отображения
        display_stats = filtered[:25]

        period_text = f"за последние {days} дней" if days else "за все время"
        title = f"📊 Статистика пользователей сервера"
        if role:
            title += f" с ролью {role.name}"
        embed = discord.Embed(
            title=title,
            description=f"Топ-{len(display_stats)} пользователей {period_text}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        # Топ по сообщениям
        messages_top = sorted(display_stats, key=lambda x: x['period_messages'], reverse=True)[:10]
        messages_text = []
        for i, user_data in enumerate(messages_top, 1):
            member = ctx.guild.get_member(user_data['user_id'])
            if member:
                messages_text.append(f"{i}. **{member.display_name}**: {user_data['period_messages']} сообщений")

        if messages_text:
            embed.add_field(
                name="💬 Топ по сообщениям",
                value="\n".join(messages_text),
                inline=False
            )

        # Топ по времени в войсе
        voice_top = sorted(display_stats, key=lambda x: x['period_voice_time'], reverse=True)[:10]
        voice_text = []
        for i, user_data in enumerate(voice_top, 1):
            member = ctx.guild.get_member(user_data['user_id'])
            if member:
                hours = int(user_data['period_voice_time'] // 3600)
                minutes = int((user_data['period_voice_time'] % 3600) // 60)
                voice_text.append(f"{i}. **{member.display_name}**: {hours}ч {minutes}м")

        if voice_text:
            embed.add_field(
                name="🎤 Топ по времени в войсе",
                value="\n".join(voice_text),
                inline=False
            )

        embed.set_footer(text=f"Всего пользователей: {len(all_stats)} | Используйте !stats_all_export для полного списка")

        await ctx.send(embed=embed)

    @commands.command(name='alfa_stats_all_export')
    @is_admin_or_whitelisted()
    async def stats_all_export(self, ctx, days: int = None):
        """Экспортировать статистику всех пользователей в CSV. Формат: !stats_all_export [7/14/30]"""
        await ctx.message.delete()

        # Проверяем допустимость дней
        if days and days not in [7, 14, 30]:
            await ctx.send("❌ Допустимые периоды: 7, 14 или 30 дней")
            return

        # Получаем статистику всех пользователей
        all_stats = self.db.get_all_users_stats(ctx.guild.id, days)

        if not all_stats:
            await ctx.send("📊 Нет данных о пользователях")
            return

        # Формируем CSV
        output = StringIO()
        writer = csv.writer(output)

        period_text = f"{days} days" if days else "all time"

        writer.writerow(['Server Statistics'])
        writer.writerow(['Server:', ctx.guild.name])
        writer.writerow(['Period:', period_text])
        writer.writerow(['Total Users:', len(all_stats)])
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
            member = ctx.guild.get_member(user_data['user_id'])
            user_name = member.display_name if member else f"User ID: {user_data['user_id']}"

            if days:
                # Форматируем время
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
            filename=f'server_stats_{ctx.guild.name}_{period_text}.csv'
        )

        await ctx.send(f"📊 Экспорт статистики сервера ({len(all_stats)} пользователей)", file=file)

    # Добавьте эти улучшенные команды в stats.py
# Заменяют существующие alfa_inactive, alfa_inactive_export, alfa_activity_summary

    @commands.command(name='alfa_inactive')
    @is_admin_or_whitelisted()
    async def inactive_users(self, ctx, days: int = 7, role: discord.Role = None):
        """Показать список неактивных пользователей. Формат: !alfa_inactive [7/14/30] [@роль]"""
        await ctx.message.delete()
        
        # Проверяем допустимость дней
        if days not in [7, 14, 30]:
            await ctx.send("❌ Допустимые периоды: 7, 14 или 30 дней", delete_after=10)
            return
        
        # Получаем всех пользователей сервера (не ботов)
        all_members = [m for m in ctx.guild.members if not m.bot]
        
        # Фильтруем по роли если указана
        if role:
            all_members = [m for m in all_members if role in m.roles]
        
        # Получаем статистику активных пользователей
        active_stats = self.db.get_all_users_stats(ctx.guild.id, days)
        active_user_ids = {stat['user_id'] for stat in active_stats if stat['period_messages'] > 0 or stat['period_voice_time'] > 0}
        
        # Находим неактивных
        inactive_members = [m for m in all_members if m.id not in active_user_ids]
        
        if not inactive_members:
            role_text = f" с ролью {role.mention}" if role else ""
            await ctx.send(f"✅ Все пользователи{role_text} были активны за последние {days} дней!", delete_after=15)
            return
        
        # Формируем embed
        title_suffix = f" (роль: {role.name})" if role else ""
        embed = discord.Embed(
            title=f"😴 Неактивные пользователи{title_suffix}",
            description=f"Пользователи без активности за последние **{days} дней**",
            color=0xE67E22,
            timestamp=datetime.utcnow()
        )
        
        # Группируем по ролям
        inactive_text = []
        for i, member in enumerate(inactive_members[:25], 1):  # Ограничиваем до 25
            # Получаем высшую роль (кроме @everyone)
            top_role = member.top_role.name if member.top_role.name != "@everyone" else "Нет роли"
            inactive_text.append(f"{i}. {member.mention} • `{top_role}`")
        
        if len(inactive_text) > 0:
            # Разбиваем на части если много
            if len(inactive_members) <= 25:
                embed.add_field(
                    name=f"👥 Список ({len(inactive_members)} пользователей)",
                    value="\n".join(inactive_text),
                    inline=False
                )
            else:
                # Первые 25
                embed.add_field(
                    name=f"👥 Первые 25 из {len(inactive_members)}",
                    value="\n".join(inactive_text[:25]),
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
        
        embed.set_footer(text=f"Используйте !alfa_inactive_export {days} для полного списка")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='alfa_inactive_export')
    @is_admin_or_whitelisted()
    async def inactive_export(self, ctx, days: int = 7, role: discord.Role = None):
        """Экспортировать список неактивных в CSV. Формат: !alfa_inactive_export [7/14/30] [@роль]"""
        await ctx.message.delete()
        
        # Проверяем допустимость дней
        if days not in [7, 14, 30]:
            await ctx.send("❌ Допустимые периоды: 7, 14 или 30 дней", delete_after=10)
            return
        
        # Получаем всех пользователей сервера (не ботов)
        all_members = [m for m in ctx.guild.members if not m.bot]
        
        # Фильтруем по роли если указана
        if role:
            all_members = [m for m in all_members if role in m.roles]
        
        # Получаем статистику активных пользователей
        active_stats = self.db.get_all_users_stats(ctx.guild.id, days)
        active_user_ids = {stat['user_id'] for stat in active_stats if stat['period_messages'] > 0 or stat['period_voice_time'] > 0}
        
        # Находим неактивных
        inactive_members = [m for m in all_members if m.id not in active_user_ids]
        
        if not inactive_members:
            role_text = f" с ролью {role.mention}" if role else ""
            await ctx.send(f"✅ Все пользователи{role_text} были активны за последние {days} дней!", delete_after=15)
            return
        
        # Формируем CSV
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Inactive Users Report'])
        writer.writerow(['Server:', ctx.guild.name])
        writer.writerow(['Period:', f'{days} days'])
        if role:
            writer.writerow(['Filtered by role:', role.name])
        writer.writerow(['Total Members:', len(all_members)])
        writer.writerow(['Inactive Members:', len(inactive_members)])
        writer.writerow(['Report Date:', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')])
        writer.writerow([])
        
        # Заголовок таблицы
        writer.writerow([
            'Rank',
            'Username',
            'Display Name',
            'User ID',
            'Top Role',
            'All Roles',  # НОВОЕ: Все роли
            'Joined Server',
            'Account Created'
        ])
        
        # Записываем данных
        for i, member in enumerate(inactive_members, 1):
            top_role = member.top_role.name if member.top_role.name != "@everyone" else "No Role"
            
            # Все роли (кроме @everyone)
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
                all_roles,  # НОВОЕ
                joined,
                created
            ])
        
        csv_data = output.getvalue()
        
        # Создаем файл
        role_suffix = f"_role_{role.name}" if role else ""
        file = discord.File(
            io.BytesIO(csv_data.encode('utf-8-sig')),
            filename=f'inactive_users_{ctx.guild.name}_{days}days{role_suffix}.csv'
        )
        
        role_text = f" с ролью **{role.name}**" if role else ""
        await ctx.send(
            f"📊 Экспорт неактивных пользователей{role_text} ({len(inactive_members)} пользователей за {days} дней)",
            file=file
        )
    
    @commands.command(name='alfa_activity_summary')
    @is_admin_or_whitelisted()
    async def activity_summary(self, ctx, days: int = 7, role: discord.Role = None):
        """Общая сводка активности. Формат: !alfa_activity_summary [7/14/30] [@роль]"""
        await ctx.message.delete()
        
        # Проверяем допустимость дней
        if days not in [7, 14, 30]:
            await ctx.send("❌ Допустимые периоды: 7, 14 или 30 дней", delete_after=10)
            return
        
        # Получаем всех пользователей
        all_members = [m for m in ctx.guild.members if not m.bot]
        
        # Фильтруем по роли если указана
        if role:
            all_members = [m for m in all_members if role in m.roles]
        
        # Получаем статистику
        all_stats = self.db.get_all_users_stats(ctx.guild.id, days)
        
        # Фильтруем статистику по роли
        if role:
            filtered_user_ids = {m.id for m in all_members}
            all_stats = [s for s in all_stats if s['user_id'] in filtered_user_ids]
        
        # Считаем активность
        very_active = [s for s in all_stats if s['period_messages'] >= 100 or s['period_voice_time'] >= 3600*10]  # 100+ сообщений или 10+ часов
        active = [s for s in all_stats if (s['period_messages'] >= 20 or s['period_voice_time'] >= 3600*2) and s not in very_active]  # 20+ сообщений или 2+ часов
        low_active = [s for s in all_stats if (s['period_messages'] > 0 or s['period_voice_time'] > 0) and s not in very_active and s not in active]
        
        active_user_ids = {stat['user_id'] for stat in all_stats if stat['period_messages'] > 0 or stat['period_voice_time'] > 0}
        inactive_members = [m for m in all_members if m.id not in active_user_ids]
        
        # Общая статистика
        total_messages = sum(s['period_messages'] for s in all_stats)
        total_voice_time = sum(s['period_voice_time'] for s in all_stats)
        
        # Формируем embed
        title_suffix = f" (роль: {role.name})" if role else ""
        embed = discord.Embed(
            title=f"📊 Сводка активности сервера{title_suffix}",
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
            
            visual = f"🔥`{'█' * very_bar}` {very_active_pct:.1f}%\n"
            visual += f"⚡`{'█' * active_bar}` {active_pct:.1f}%\n"
            visual += f"💬`{'█' * low_bar}` {low_active_pct:.1f}%\n"
            visual += f"😴`{'█' * inactive_bar}` {inactive_pct:.1f}%"
            
            embed.add_field(
                name="📊 Распределение",
                value=visual,
                inline=False
            )
        
        # Топ-3 самых активных
        if all_stats:
            top_messages = sorted(all_stats, key=lambda x: x['period_messages'], reverse=True)[:3]
            top_text = []
            for i, user_data in enumerate(top_messages, 1):
                member = ctx.guild.get_member(user_data['user_id'])
                if member:
                    emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
                    top_text.append(f"{emoji} {member.mention}: {user_data['period_messages']} сообщений")
            
            if top_text:
                embed.add_field(
                    name="🏆 Топ-3 по сообщениям",
                    value="\n".join(top_text),
                    inline=False
                )
        
        embed.set_footer(text=f"Используйте !alfa_inactive {days} для списка неактивных")
        
        await ctx.send(embed=embed)

    @commands.command(name='alfa_export')
    @is_admin_or_whitelisted()
    async def export_stats(self, ctx, days: int = 7, role: discord.Role = None):
        """Экспортировать полную статистику в CSV. Формат: !alfa_export [7/14/30] [@роль]"""
        await ctx.message.delete()

        if days not in [7, 14, 30]:
            await ctx.send("❌ Допустимые периоды: 7, 14 или 30 дней", delete_after=10)
            return

        # Получаем статистику
        all_stats = self.db.get_all_users_stats(ctx.guild.id, days)

        if not all_stats:
            await ctx.send("📊 Нет данных для экспорта", delete_after=10)
            return
        
        # Фильтруем по роли если указана
        if role:
            filtered_stats = []
            for stat in all_stats:
                member = ctx.guild.get_member(stat['user_id'])
                if member and role in member.roles:
                    filtered_stats.append(stat)
            all_stats = filtered_stats
        
        if not all_stats:
            await ctx.send(f"📊 Нет данных для роли {role.mention}", delete_after=10)
            return

        # Формируем CSV
        output = StringIO()
        writer = csv.writer(output)

        writer.writerow(['User Statistics Report'])
        writer.writerow(['Server:', ctx.guild.name])
        writer.writerow(['Period:', f'{days} days'])
        if role:
            writer.writerow(['Filtered by role:', role.name])
        writer.writerow(['Total Users:', len(all_stats)])
        writer.writerow(['Report Date:', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')])
        writer.writerow([])

        writer.writerow([
            'Rank',
            'Username',
            'Display Name',
            'User ID',
            'Top Role',
            'All Roles',  # НОВОЕ
            'Messages (Period)',
            'Messages (Total)',
            'Voice Time (Period, hours)',
            'Voice Time (Total, hours)'
        ])

        for i, user_data in enumerate(all_stats, 1):
            member = ctx.guild.get_member(user_data['user_id'])
            
            if member:
                username = member.name
                display_name = member.display_name
                top_role = member.top_role.name if member.top_role.name != "@everyone" else "No Role"
                
                # Все роли (кроме @everyone)
                all_roles = ", ".join([r.name for r in member.roles if r.name != "@everyone"])
                if not all_roles:
                    all_roles = "No Roles"
            else:
                username = f"Unknown (ID: {user_data['user_id']})"
                display_name = username
                top_role = "Unknown"
                all_roles = "Unknown"

            writer.writerow([
                i,
                username,
                display_name,
                user_data['user_id'],
                top_role,
                all_roles,  # НОВОЕ
                user_data['period_messages'],
                user_data['total_messages'],
                round(user_data['period_voice_time'] / 3600, 2),
                round(user_data['total_voice_time'] / 3600, 2)
            ])

        csv_data = output.getvalue()

        # Создаем файл
        role_suffix = f"_role_{role.name}" if role else ""
        file = discord.File(
            io.BytesIO(csv_data.encode('utf-8-sig')),
            filename=f'user_stats_{ctx.guild.name}_{days}days{role_suffix}.csv'
        )

        role_text = f" для роли **{role.name}**" if role else ""
        await ctx.send(
            f"📊 Статистика {len(all_stats)} пользователей{role_text} экспортирована",
            file=file
        )

async def setup(bot):
    await bot.add_cog(Stats(bot))
