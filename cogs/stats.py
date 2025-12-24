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
    async def stats_all(self, ctx, days: int = None):
        """Показать статистику всех пользователей. Формат: !stats_all [7/14/30]"""
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

        # Ограничиваем до топ-25 для отображения
        display_stats = all_stats[:25]

        period_text = f"за последние {days} дней" if days else "за все время"
        embed = discord.Embed(
            title=f"📊 Статистика пользователей сервера",
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

async def setup(bot):
    await bot.add_cog(Stats(bot))
