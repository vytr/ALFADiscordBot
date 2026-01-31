import discord
from discord.ext import commands, tasks
from datetime import datetime
from utils import is_admin_or_whitelisted, t
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

    async def setup_hook(self):
        """Вызывается при загрузке cog - закрываем зависшие сессии"""
        print("🔧 Closing hanging voice sessions...")
        closed = self.db.close_hanging_voice_sessions(max_duration_hours=24)
        if closed > 0:
            print(f"✅ Closed {closed} hanging voice sessions")

    @commands.Cog.listener()
    async def on_ready(self):
        """Восстанавливаем голосовые сессии для пользователей уже в войсе"""
        print("🔄 Recovering voice sessions for users already in voice channels...")
        recovered = 0
        for guild in self.bot.guilds:
            for voice_channel in guild.voice_channels:
                for member in voice_channel.members:
                    if not member.bot:
                        self.db.start_voice_session(guild.id, member.id)
                        recovered += 1
                        print(f"  ↳ Recovered session: {member.name} in {voice_channel.name} ({guild.name})")

        if recovered > 0:
            print(f"✅ Recovered {recovered} voice sessions")
        else:
            print("ℹ️ No users in voice channels to recover")

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        """Ежедневная очистка старых данных"""
        deleted = self.db.cleanup_old_data()
        print(f"Cleaned up {deleted} old records")

        # Также закрываем зависшие сессии
        closed = self.db.close_hanging_voice_sessions(max_duration_hours=24)
        if closed > 0:
            print(f"Closed {closed} hanging voice sessions during cleanup")

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
        """Отслеживание активности в голосовых каналах (УПРОЩЕННАЯ ВЕРСИЯ)"""
        # Игнорируем ботов
        if member.bot:
            return

        guild_id = member.guild.id
        user_id = member.id

        # Пользователь присоединился к каналу
        if before.channel is None and after.channel is not None:
            self.db.start_voice_session(guild_id, user_id)
            print(f"Voice session started: {member.name} -> {after.channel.name}")

        # Пользователь покинул канал
        elif before.channel is not None and after.channel is None:
            self.db.end_voice_session(guild_id, user_id)
            print(f"Voice session ended: {member.name} <- {before.channel.name}")

        # Пользователь переключился между каналами
        # В упрощенной версии ничего не делаем - продолжаем считать ту же сессию
        elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            # Просто логируем переключение
            print(f"Voice channel switched: {member.name} {before.channel.name} -> {after.channel.name}")

    @commands.command(name='gb_stats')
    @is_admin_or_whitelisted()
    async def stats(self, ctx, member: discord.Member = None, days: int = None):
        """Показать статистику пользователя. Формат: !gb_stats [@user] [7/14/30]"""
        await ctx.message.delete()
        guild_id = ctx.guild.id

        # Если пользователь не указан - показываем статистику автора
        if member is None:
            member = ctx.author

        # Проверяем допустимость дней
        if days and days not in [7, 14, 30]:
            await ctx.send(t('stats_invalid_period', guild_id=guild_id))
            return

        # Получаем статистику
        stats = self.db.get_user_stats(guild_id, member.id, days)

        if not stats:
            await ctx.send(t('stats_no_data', guild_id=guild_id, user=member.mention))
            return

        # Формируем embed
        period_text = t('stats_period_days', guild_id=guild_id, days=days) if days else t('stats_period_all', guild_id=guild_id)
        embed = discord.Embed(
            title=t('stats_title', guild_id=guild_id, user=member.display_name),
            description=t('stats_description', guild_id=guild_id, period=period_text),
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        # Сообщения
        if days:
            embed.add_field(
                name=t('stats_messages', guild_id=guild_id),
                value=f"**{period_text.capitalize()}:** {stats['period_messages']}\n**{t('stats_total', guild_id=guild_id)}:** {stats['total_messages']}",
                inline=False
            )
        else:
            embed.add_field(
                name=t('stats_messages', guild_id=guild_id),
                value=f"**{t('stats_total', guild_id=guild_id)}:** {stats['total_messages']}",
                inline=False
            )

        # Голосовые каналы (УПРОЩЕННАЯ ВЕРСИЯ - без разбивки по каналам)
        voice_time_period = stats['period_voice_time']
        hours_period = int(voice_time_period // 3600)
        minutes_period = int((voice_time_period % 3600) // 60)

        hours_total = int(stats['total_voice_time'] // 3600)
        minutes_total = int((stats['total_voice_time'] % 3600) // 60)

        if days:
            embed.add_field(
                name=t('stats_voice', guild_id=guild_id),
                value=f"**{period_text.capitalize()}:** {hours_period}ч {minutes_period}м\n**{t('stats_total', guild_id=guild_id)}:** {hours_total}ч {minutes_total}м",
                inline=False
            )
        else:
            embed.add_field(
                name=t('stats_voice', guild_id=guild_id),
                value=f"**{t('stats_total', guild_id=guild_id)}:** {hours_total}ч {minutes_total}м",
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.command(name='gb_stats_export')
    @is_admin_or_whitelisted()
    async def stats_export(self, ctx, member: discord.Member = None, days: int = None):
        """Экспортировать статистику в CSV. Формат: !gb_stats_export [@user] [7/14/30]"""
        await ctx.message.delete()
        guild_id = ctx.guild.id

        # Если пользователь не указан - показываем статистику автора
        if member is None:
            member = ctx.author

        # Проверяем допустимость дней
        if days and days not in [7, 14, 30]:
            await ctx.send(t('stats_invalid_period', guild_id=guild_id))
            return

        # Получаем статистику
        stats = self.db.get_user_stats(guild_id, member.id, days)

        if not stats:
            await ctx.send(t('stats_no_data', guild_id=guild_id, user=member.mention))
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
        if days:
            writer.writerow(['Period Voice Time (seconds):', stats['period_voice_time']])
            writer.writerow(['Period Voice Time (hours):', round(stats['period_voice_time'] / 3600, 2)])
        writer.writerow(['Total Voice Time (seconds):', stats['total_voice_time']])
        writer.writerow(['Total Voice Time (hours):', round(stats['total_voice_time'] / 3600, 2)])

        csv_data = output.getvalue()

        # Создаем файл
        file = discord.File(
            io.BytesIO(csv_data.encode('utf-8-sig')),
            filename=f'user_stats_{member.display_name}_{period_text}.csv'
        )

        await ctx.send(t('stats_exported', guild_id=guild_id, user=member.mention), file=file)

    @commands.command(name='gb_leaderboard')
    @is_admin_or_whitelisted()
    async def leaderboard(self, ctx, days: int = 7):
        """Таблица лидеров. Формат: !gb_leaderboard [7/14/30]"""
        await ctx.message.delete()
        guild_id = ctx.guild.id

        if days not in [7, 14, 30]:
            await ctx.send(t('stats_invalid_period', guild_id=guild_id), delete_after=10)
            return

        # Получаем статистику всех пользователей
        all_stats = self.db.get_all_users_stats(guild_id, days)

        if not all_stats:
            await ctx.send(t('leaderboard_no_data', guild_id=guild_id), delete_after=10)
            return

        # Сортируем по сообщениям
        top_messages = sorted(all_stats, key=lambda x: x['period_messages'], reverse=True)[:20]

        # Сортируем по времени в войсе
        top_voice = sorted(all_stats, key=lambda x: x['period_voice_time'], reverse=True)[:20]

        # Создаем embed для сообщений
        embed_messages = discord.Embed(
            title=t('leaderboard_messages_title', guild_id=guild_id, days=days),
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )

        leaderboard_text = []
        for i, user_data in enumerate(top_messages, 1):
            member = ctx.guild.get_member(user_data['user_id'])
            if member:
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
                leaderboard_text.append(
                    t('leaderboard_messages_entry', guild_id=guild_id, emoji=emoji, user=member.mention, count=user_data['period_messages'])
                )

        embed_messages.description = "\n".join(leaderboard_text)

        # Создаем embed для войса
        embed_voice = discord.Embed(
            title=t('leaderboard_voice_title', guild_id=guild_id, days=days),
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        leaderboard_voice = []
        for i, user_data in enumerate(top_voice, 1):
            member = ctx.guild.get_member(user_data['user_id'])
            if member:
                hours = int(user_data['period_voice_time'] // 3600)
                minutes = int((user_data['period_voice_time'] % 3600) // 60)
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
                leaderboard_voice.append(
                    t('leaderboard_voice_entry', guild_id=guild_id, emoji=emoji, user=member.mention, hours=hours, minutes=minutes)
                )

        embed_voice.description = "\n".join(leaderboard_voice)

        await ctx.send(embed=embed_messages)
        await ctx.send(embed=embed_voice)

    @commands.command(name='gb_inactive')
    @is_admin_or_whitelisted()
    async def inactive(self, ctx, days: int = 7, role: discord.Role = None):
        """Показать неактивных участников. Формат: !gb_inactive [7/14/30] [@роль]"""
        await ctx.message.delete()
        guild_id = ctx.guild.id

        if days not in [7, 14, 30]:
            await ctx.send(t('stats_invalid_period', guild_id=guild_id), delete_after=10)
            return

        # Получаем всех участников (исключая ботов)
        all_members = [m for m in ctx.guild.members if not m.bot]

        # Фильтруем по роли если указана
        if role:
            all_members = [m for m in all_members if role in m.roles]

        # Получаем статистику
        all_stats = self.db.get_all_users_stats(guild_id, days)

        # Находим ID активных пользователей
        active_user_ids = {
            stat['user_id'] for stat in all_stats
            if stat['period_messages'] > 0 or stat['period_voice_time'] > 0
        }

        # Находим неактивных
        inactive_members = [m for m in all_members if m.id not in active_user_ids]

        if not inactive_members:
            role_suffix = t('inactive_role_suffix', guild_id=guild_id, role=role.name) if role else ""
            await ctx.send(t('inactive_none', guild_id=guild_id, suffix=role_suffix, days=days), delete_after=10)
            return

        # Формируем embed
        title_suffix = f" (роль: {role.name})" if role else ""
        embed = discord.Embed(
            title=t('inactive_title', guild_id=guild_id, suffix=title_suffix),
            description=t('inactive_description', guild_id=guild_id, days=days),
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        # Разбиваем на чанки по 20 пользователей
        chunk_size = 20
        for i in range(0, len(inactive_members), chunk_size):
            chunk = inactive_members[i:i + chunk_size]
            members_list = [f"• {m.mention} ({m.name})" for m in chunk]

            field_name = t('inactive_field_name', guild_id=guild_id, start=i+1, end=min(i+chunk_size, len(inactive_members)))
            embed.add_field(
                name=field_name,
                value="\n".join(members_list),
                inline=False
            )

        embed.set_footer(text=t('inactive_footer', guild_id=guild_id, count=len(inactive_members)))

        await ctx.send(embed=embed)

    @commands.command(name='gb_summary')
    @is_admin_or_whitelisted()
    async def summary(self, ctx, days: int = 7, role: discord.Role = None):
        """Сводка активности сервера. Формат: !gb_summary [7/14/30] [@роль]"""
        await ctx.message.delete()
        guild_id = ctx.guild.id

        if days not in [7, 14, 30]:
            await ctx.send(t('stats_invalid_period', guild_id=guild_id), delete_after=10)
            return

        # Получаем всех участников (исключая ботов)
        all_members = [m for m in ctx.guild.members if not m.bot]

        # Фильтруем по роли если указана
        if role:
            all_members = [m for m in all_members if role in m.roles]

        # Получаем статистику
        all_stats = self.db.get_all_users_stats(guild_id, days)

        # Фильтруем статистику по роли
        if role:
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
        title_suffix = f" (роль: {role.name})" if role else ""
        embed = discord.Embed(
            title=t('summary_title', guild_id=guild_id, suffix=title_suffix),
            description=t('summary_description', guild_id=guild_id, days=days),
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )

        # Общие цифры
        voice_hours = int(total_voice_time // 3600)
        voice_minutes = int((total_voice_time % 3600) // 60)
        embed.add_field(
            name=t('summary_total_activity', guild_id=guild_id),
            value=f"{t('summary_messages_count', guild_id=guild_id, count=total_messages)}\n{t('summary_voice_time', guild_id=guild_id, hours=voice_hours, minutes=voice_minutes)}",
            inline=True
        )

        embed.add_field(
            name=t('summary_members', guild_id=guild_id),
            value=f"{t('summary_members_total', guild_id=guild_id, total=len(all_members))}\n{t('summary_members_active', guild_id=guild_id, active=len(active_user_ids))}",
            inline=True
        )

        # Разбивка по уровням активности
        embed.add_field(
            name=t('summary_activity_levels', guild_id=guild_id),
            value=f"{t('summary_very_active', guild_id=guild_id, count=len(very_active))}\n{t('summary_active', guild_id=guild_id, count=len(active))}\n{t('summary_low_active', guild_id=guild_id, count=len(low_active))}\n{t('summary_inactive', guild_id=guild_id, count=len(inactive_members))}",
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
                name=t('summary_distribution', guild_id=guild_id),
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
                    top_text.append(t('summary_top3_entry', guild_id=guild_id, emoji=emoji, user=member.mention, count=user_data['period_messages']))

            if top_text:
                embed.add_field(
                    name=t('summary_top3_messages', guild_id=guild_id),
                    value="\n".join(top_text),
                    inline=False
                )

        embed.set_footer(text=t('summary_footer', guild_id=guild_id, days=days))

        await ctx.send(embed=embed)

    @commands.command(name='gb_export')
    @is_admin_or_whitelisted()
    async def export_stats(self, ctx, days: int = 7, role: discord.Role = None):
        """Экспортировать полную статистику в CSV. Формат: !gb_export [7/14/30] [@роль]"""
        await ctx.message.delete()
        guild_id = ctx.guild.id

        if days not in [7, 14, 30]:
            await ctx.send(t('stats_invalid_period', guild_id=guild_id), delete_after=10)
            return

        # Получаем статистику
        all_stats = self.db.get_all_users_stats(guild_id, days)

        if not all_stats:
            await ctx.send(t('export_no_data', guild_id=guild_id), delete_after=10)
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
            await ctx.send(t('export_no_role_data', guild_id=guild_id, role=role.mention), delete_after=10)
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
            'All Roles',
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
                all_roles,
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

        suffix = t('export_role_suffix', guild_id=guild_id, role=role.name) if role else ""
        await ctx.send(
            t('export_title', guild_id=guild_id, count=len(all_stats), suffix=suffix),
            file=file
        )

    @commands.command(name='gb_voice_debug')
    @commands.has_permissions(administrator=True)
    async def voice_debug(self, ctx):
        """[ADMIN] Показать активные голосовые сессии для отладки"""
        await ctx.message.delete()
        guild_id = ctx.guild.id

        sessions = self.db.get_active_voice_sessions(guild_id)

        if not sessions:
            await ctx.send(t('voice_debug_no_sessions', guild_id=guild_id), delete_after=10)
            return

        embed = discord.Embed(
            title=t('voice_debug_title', guild_id=guild_id),
            description=t('voice_debug_description', guild_id=guild_id, count=len(sessions)),
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )

        for session_id, g_id, user_id, join_time, current_duration in sessions:
            member = ctx.guild.get_member(user_id)
            username = member.display_name if member else f"Unknown (ID: {user_id})"

            hours = int(current_duration // 3600)
            minutes = int((current_duration % 3600) // 60)

            embed.add_field(
                name=t('voice_debug_session', guild_id=guild_id, id=session_id),
                value=t('voice_debug_session_info', guild_id=guild_id, user=username, hours=hours, minutes=minutes, started=join_time),
                inline=False
            )

        await ctx.send(embed=embed)

async def setup(bot):
    cog = Stats(bot)
    await bot.add_cog(cog)
    # Вызываем setup_hook после добавления cog
    await cog.setup_hook()
