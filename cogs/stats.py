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
        if message.author.bot:
            return

        if not message.guild:
            return

        self.db.log_message(message.guild.id, message.author.id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Отслеживание активности в голосовых каналах"""
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
        elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            print(f"Voice channel switched: {member.name} {before.channel.name} -> {after.channel.name}")

    @commands.command(name='alfa_stats')
    @is_admin_or_whitelisted()
    async def stats(self, ctx, member: discord.Member = None, days: int = None):
        """Показать статистику пользователя. Формат: !alfa_stats [@user] [7/14/30]"""
        await ctx.message.delete()

        if member is None:
            member = ctx.author

        if days and days not in [7, 14, 30]:
            await ctx.send("❌ Допустимые периоды: 7, 14 или 30 дней")
            return

        embed = await self.get_user_stats_embed(ctx.guild, member, days)
        
        if not embed:
            await ctx.send(f"📊 Нет данных для {member.mention}")
            return

        await ctx.send(embed=embed)

    @commands.command(name='alfa_stats_export')
    @is_admin_or_whitelisted()
    async def stats_export(self, ctx, member: discord.Member = None, days: int = None):
        """Экспортировать статистику в CSV. Формат: !alfa_stats_export [@user] [7/14/30]"""
        await ctx.message.delete()

        if member is None:
            member = ctx.author

        if days and days not in [7, 14, 30]:
            await ctx.send("❌ Допустимые периоды: 7, 14 или 30 дней")
            return

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
        if days:
            writer.writerow(['Period Voice Time (seconds):', stats['period_voice_time']])
            writer.writerow(['Period Voice Time (hours):', round(stats['period_voice_time'] / 3600, 2)])
        writer.writerow(['Total Voice Time (seconds):', stats['total_voice_time']])
        writer.writerow(['Total Voice Time (hours):', round(stats['total_voice_time'] / 3600, 2)])

        csv_data = output.getvalue()

        file = discord.File(
            io.BytesIO(csv_data.encode('utf-8-sig')),
            filename=f'user_stats_{member.display_name}_{period_text}.csv'
        )

        await ctx.send(f"📊 Статистика {member.mention} экспортирована", file=file)

    @commands.command(name='alfa_leaderboard')
    @is_admin_or_whitelisted()
    async def leaderboard(self, ctx, days: int = 7):
        """Таблица лидеров. Формат: !alfa_leaderboard [7/14/30]"""
        await ctx.message.delete()

        if days not in [7, 14, 30]:
            await ctx.send("❌ Допустимые периоды: 7, 14 или 30 дней", delete_after=10)
            return

        embed = await self.get_leaderboard_embed(ctx.guild, days)
        
        if not embed:
            await ctx.send("📊 Нет данных для отображения", delete_after=10)
            return

        await ctx.send(embed=embed)

    @commands.command(name='alfa_inactive')
    @is_admin_or_whitelisted()
    async def inactive(self, ctx, days: int = 7, role: discord.Role = None):
        """Показать неактивных участников. Формат: !alfa_inactive [7/14/30] [@роль]"""
        await ctx.message.delete()

        if days not in [7, 14, 30]:
            await ctx.send("❌ Допустимые периоды: 7, 14 или 30 дней", delete_after=10)
            return

        all_members = [m for m in ctx.guild.members if not m.bot]
        
        if role:
            all_members = [m for m in all_members if role in m.roles]

        all_stats = self.db.get_all_users_stats(ctx.guild.id, days)

        active_user_ids = {
            stat['user_id'] for stat in all_stats 
            if stat['period_messages'] > 0 or stat['period_voice_time'] > 0
        }

        inactive_members = [m for m in all_members if m.id not in active_user_ids]

        if not inactive_members:
            role_text = f" с ролью **{role.name}**" if role else ""
            await ctx.send(f"✅ Все участники{role_text} активны за последние {days} дней!", delete_after=10)
            return

        title_suffix = f" (роль: {role.name})" if role else ""
        embed = discord.Embed(
            title=f"😴 Неактивные участники{title_suffix}",
            description=f"Участники без активности за последние **{days} дней**",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        chunk_size = 20
        for i in range(0, len(inactive_members), chunk_size):
            chunk = inactive_members[i:i + chunk_size]
            members_list = [f"• {m.mention} ({m.name})" for m in chunk]
            
            field_name = f"Неактивные участники ({i+1}-{min(i+chunk_size, len(inactive_members))})"
            embed.add_field(
                name=field_name,
                value="\n".join(members_list),
                inline=False
            )

        embed.set_footer(text=f"Всего неактивных: {len(inactive_members)}")

        await ctx.send(embed=embed)

    @commands.command(name='alfa_summary')
    @is_admin_or_whitelisted()
    async def summary(self, ctx, days: int = 7, role: discord.Role = None):
        """Сводка активности сервера. Формат: !alfa_summary [7/14/30] [@роль]"""
        await ctx.message.delete()
        
        if days not in [7, 14, 30]:
            await ctx.send("❌ Допустимые периоды: 7, 14 или 30 дней", delete_after=10)
            return
        
        all_members = [m for m in ctx.guild.members if not m.bot]
        
        if role:
            all_members = [m for m in all_members if role in m.roles]
        
        all_stats = self.db.get_all_users_stats(ctx.guild.id, days)
        
        if role:
            filtered_user_ids = {m.id for m in all_members}
            all_stats = [s for s in all_stats if s['user_id'] in filtered_user_ids]
        
        very_active = [s for s in all_stats if s['period_messages'] >= 100 or s['period_voice_time'] >= 3600*10]
        active = [s for s in all_stats if (s['period_messages'] >= 20 or s['period_voice_time'] >= 3600*2) and s not in very_active]
        low_active = [s for s in all_stats if (s['period_messages'] > 0 or s['period_voice_time'] > 0) and s not in very_active and s not in active]
        
        active_user_ids = {stat['user_id'] for stat in all_stats if stat['period_messages'] > 0 or stat['period_voice_time'] > 0}
        inactive_members = [m for m in all_members if m.id not in active_user_ids]
        
        total_messages = sum(s['period_messages'] for s in all_stats)
        total_voice_time = sum(s['period_voice_time'] for s in all_stats)
        
        title_suffix = f" (роль: {role.name})" if role else ""
        embed = discord.Embed(
            title=f"📊 Сводка активности сервера{title_suffix}",
            description=f"Анализ активности за последние **{days} дней**",
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )
        
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
        
        embed.add_field(
            name="🎯 Уровни активности",
            value=f"🔥 **Очень активные:** {len(very_active)}\n⚡ **Активные:** {len(active)}\n💬 **Низкая активность:** {len(low_active)}\n😴 **Неактивные:** {len(inactive_members)}",
            inline=False
        )
        
        total = len(all_members)
        if total > 0:
            very_active_pct = len(very_active) / total * 100
            active_pct = len(active) / total * 100
            low_active_pct = len(low_active) / total * 100
            inactive_pct = len(inactive_members) / total * 100
            
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

        all_stats = self.db.get_all_users_stats(ctx.guild.id, days)

        if not all_stats:
            await ctx.send("📊 Нет данных для экспорта", delete_after=10)
            return
        
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
    
    async def get_leaderboard_embed(self, guild, days: int = 7) -> discord.Embed:
        """Получить embed с топом пользователей (для переиспользования в panel)"""
        all_stats = self.db.get_all_users_stats(guild.id, days)
        
        if not all_stats:
            return None
        
        top_messages = sorted(all_stats, key=lambda x: x['period_messages'], reverse=True)[:10]
        top_voice = sorted(all_stats, key=lambda x: x['period_voice_time'], reverse=True)[:10]
        
        embed = discord.Embed(
            title=f"🏆 Топ пользователей сервера",
            description=f"Рейтинг за последние {days} дней",
            color=0xF1C40F,
            timestamp=datetime.utcnow()
        )
        
        messages_text = []
        for i, user_data in enumerate(top_messages, 1):
            member = guild.get_member(user_data['user_id'])
            if member:
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "▫️"
                messages_text.append(f"{emoji} **{member.display_name}**: {user_data['period_messages']} сообщений")
        
        if messages_text:
            embed.add_field(
                name="💬 Топ-10 по сообщениям",
                value="\n".join(messages_text),
                inline=False
            )
        
        voice_text = []
        for i, user_data in enumerate(top_voice, 1):
            member = guild.get_member(user_data['user_id'])
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
        
        return embed
    
    async def get_user_stats_embed(self, guild, user, days: int = None) -> discord.Embed:
        """Получить embed со статистикой пользователя (для переиспользования)"""
        stats = self.db.get_user_stats(guild.id, user.id, days)
        
        if not stats:
            return None
        
        period_text = f"за последние {days} дней" if days else "за все время"
        embed = discord.Embed(
            title=f"📊 Статистика {user.display_name}",
            description=f"Статистика активности {period_text}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        
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
        
        voice_time_period = stats['period_voice_time']
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
        
        return embed

    @commands.command(name='alfa_voice_debug')
    @commands.has_permissions(administrator=True)
    async def voice_debug(self, ctx):
        """[ADMIN] Показать активные голосовые сессии для отладки"""
        await ctx.message.delete()
        
        sessions = self.db.get_active_voice_sessions(ctx.guild.id)
        
        if not sessions:
            await ctx.send("✅ Нет активных голосовых сессий", delete_after=10)
            return
        
        embed = discord.Embed(
            title="🔧 Активные голосовые сессии",
            description=f"Найдено {len(sessions)} активных сессий",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )
        
        for session_id, guild_id, user_id, join_time, current_duration in sessions:
            member = ctx.guild.get_member(user_id)
            username = member.display_name if member else f"Unknown (ID: {user_id})"
            
            hours = int(current_duration // 3600)
            minutes = int((current_duration % 3600) // 60)
            
            embed.add_field(
                name=f"Session #{session_id}",
                value=f"**User:** {username}\n**Duration:** {hours}ч {minutes}м\n**Started:** {join_time}",
                inline=False
            )
        
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Stats(bot))