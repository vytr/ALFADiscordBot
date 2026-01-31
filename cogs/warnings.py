import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from utils import is_admin_or_whitelisted, t

class WarningSystem(commands.Cog):
    """Система выговоров для модерации сервера"""

    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

        # Инициализируем таблицу в БД
        self.init_warnings_table()

        # Запускаем задачу автоматического снятия выговоров
        self.auto_remove_warnings.start()

    def cog_unload(self):
        self.auto_remove_warnings.cancel()

    def init_warnings_table(self):
        """Создание таблицы для выговоров"""
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                warned_by INTEGER NOT NULL,
                reason TEXT NOT NULL,
                warned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                is_active INTEGER DEFAULT 1,
                removed_at TIMESTAMP,
                removed_by INTEGER,
                removal_reason TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def get_active_warnings_count(self, guild_id: int, user_id: int) -> int:
        """Получить количество активных выговоров"""
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT COUNT(*) FROM warnings
            WHERE guild_id = ? AND user_id = ? AND is_active = 1
        ''', (guild_id, user_id))

        count = cursor.fetchone()[0]
        conn.close()
        return count

    def add_warning(self, guild_id: int, user_id: int, warned_by: int, reason: str) -> tuple:
        """Добавить выговор. Возвращает (успех, warning_id или сообщение об ошибке)"""
        import sqlite3

        # Проверяем количество активных выговоров
        current_warnings = self.get_active_warnings_count(guild_id, user_id)

        if current_warnings >= 3:
            return (False, t('warn_max_reached', user=""))

        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()

            # Выговор истекает через 7 дней
            expires_at = datetime.utcnow() + timedelta(days=7)

            cursor.execute('''
                INSERT INTO warnings (guild_id, user_id, warned_by, reason, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (guild_id, user_id, warned_by, reason, expires_at.isoformat()))

            warning_id = cursor.lastrowid
            conn.commit()
            conn.close()

            return (True, warning_id)
        except Exception as e:
            print(f"Error adding warning: {e}")
            return (False, str(e))

    def remove_warning(self, warning_id: int, removed_by: int, reason: str = None) -> bool:
        """Снять выговор вручную"""
        import sqlite3
        if reason is None:
            reason = t('unwarn_removal_reason')
        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE warnings
                SET is_active = 0, removed_at = CURRENT_TIMESTAMP,
                    removed_by = ?, removal_reason = ?
                WHERE id = ? AND is_active = 1
            ''', (removed_by, reason, warning_id))

            affected = cursor.rowcount
            conn.commit()
            conn.close()

            return affected > 0
        except Exception as e:
            print(f"Error removing warning: {e}")
            return False

    def get_user_warnings(self, guild_id: int, user_id: int, active_only: bool = False):
        """Получить все выговоры пользователя"""
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        if active_only:
            cursor.execute('''
                SELECT id, warned_by, reason, warned_at, expires_at
                FROM warnings
                WHERE guild_id = ? AND user_id = ? AND is_active = 1
                ORDER BY warned_at DESC
            ''', (guild_id, user_id))
        else:
            cursor.execute('''
                SELECT id, warned_by, reason, warned_at, expires_at, is_active,
                       removed_at, removed_by, removal_reason
                FROM warnings
                WHERE guild_id = ? AND user_id = ?
                ORDER BY warned_at DESC
            ''', (guild_id, user_id))

        results = cursor.fetchall()
        conn.close()
        return results

    def get_all_warnings(self, guild_id: int, active_only: bool = True):
        """Получить все выговоры на сервере"""
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        if active_only:
            cursor.execute('''
                SELECT user_id, COUNT(*) as warning_count
                FROM warnings
                WHERE guild_id = ? AND is_active = 1
                GROUP BY user_id
                ORDER BY warning_count DESC, user_id
            ''', (guild_id,))
        else:
            cursor.execute('''
                SELECT user_id,
                       SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active_count,
                       COUNT(*) as total_count
                FROM warnings
                WHERE guild_id = ?
                GROUP BY user_id
                ORDER BY active_count DESC, total_count DESC
            ''', (guild_id,))

        results = cursor.fetchall()
        conn.close()
        return results

    @tasks.loop(hours=1)
    async def auto_remove_warnings(self):
        """Автоматическое снятие просроченных выговоров (каждый час)"""
        import sqlite3
        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()

            # Находим просроченные выговоры
            cursor.execute('''
                SELECT id, guild_id, user_id FROM warnings
                WHERE is_active = 1 AND expires_at <= CURRENT_TIMESTAMP
            ''')

            expired = cursor.fetchall()

            if expired:
                # Снимаем их
                cursor.execute('''
                    UPDATE warnings
                    SET is_active = 0, removed_at = CURRENT_TIMESTAMP,
                        removal_reason = ?
                    WHERE is_active = 1 AND expires_at <= CURRENT_TIMESTAMP
                ''', (t('warnings_auto_removed'),))

                conn.commit()
                print(f"🔄 Автоматически снято {len(expired)} выговоров")

                # Опционально: уведомить пользователей в DM
                for warning_id, guild_id, user_id in expired:
                    try:
                        guild = self.bot.get_guild(guild_id)
                        if guild:
                            member = guild.get_member(user_id)
                            if member:
                                embed = discord.Embed(
                                    title=t('warnings_auto_removed'),
                                    description=t('warnings_auto_removed_dm', server=guild.name),
                                    color=0x2ECC71,
                                    timestamp=datetime.utcnow()
                                )

                                # Проверяем сколько осталось
                                remaining = self.get_active_warnings_count(guild_id, user_id)
                                embed.add_field(
                                    name=t('unwarn_dm_status'),
                                    value=t('unwarn_dm_status_value', count=remaining),
                                    inline=False
                                )

                                await member.send(embed=embed)
                    except:
                        pass  # Если не удалось отправить DM - не критично

            conn.close()
        except Exception as e:
            print(f"Error in auto_remove_warnings: {e}")

    @auto_remove_warnings.before_loop
    async def before_auto_remove(self):
        await self.bot.wait_until_ready()

    @commands.command(name='warn')
    @is_admin_or_whitelisted()
    async def warn_user(self, ctx, member: discord.Member, *, reason: str):
        """Выдать выговор пользователю. Формат: !warn @пользователь причина"""
        guild_id = ctx.guild.id

        # Нельзя выдать выговор самому себе
        if member.id == ctx.author.id:
            await ctx.send(t('warn_self_error', guild_id=guild_id))
            return

        # Нельзя выдать выговор боту
        if member.bot:
            await ctx.send(t('warn_bot_error', guild_id=guild_id))
            return

        # Проверяем текущее количество выговоров
        current_warnings = self.get_active_warnings_count(guild_id, member.id)

        if current_warnings >= 3:
            await ctx.send(t('warn_max_reached', guild_id=guild_id, user=member.mention))
            return

        # Добавляем выговор
        success, result = self.add_warning(guild_id, member.id, ctx.author.id, reason)

        if not success:
            await ctx.send(t('warn_error', guild_id=guild_id, error=result))
            return

        warning_id = result
        new_count = current_warnings + 1

        # Формируем embed
        embed = discord.Embed(
            title=t('warn_title', guild_id=guild_id),
            description=t('warn_description', guild_id=guild_id, user=member.mention),
            color=0xE67E22 if new_count < 3 else 0xE74C3C,
            timestamp=datetime.utcnow()
        )

        embed.add_field(
            name=t('warn_user', guild_id=guild_id),
            value=f"{member.mention}\n`{member.name}`",
            inline=True
        )

        embed.add_field(
            name=t('warn_issued_by', guild_id=guild_id),
            value=f"{ctx.author.mention}\n`{ctx.author.name}`",
            inline=True
        )

        embed.add_field(
            name=t('warn_status', guild_id=guild_id),
            value=t('warn_status_value', guild_id=guild_id, count=new_count),
            inline=True
        )

        embed.add_field(
            name=t('warn_reason', guild_id=guild_id),
            value=reason,
            inline=False
        )

        embed.add_field(
            name=t('warn_duration', guild_id=guild_id),
            value=t('warn_duration_value', guild_id=guild_id),
            inline=False
        )

        embed.set_footer(text=t('warn_footer', guild_id=guild_id, id=warning_id))

        # Предупреждение при 3 выговорах
        if new_count == 3:
            embed.add_field(
                name=t('warn_critical', guild_id=guild_id),
                value=t('warn_critical_message', guild_id=guild_id),
                inline=False
            )

        await ctx.send(embed=embed)

        # Пытаемся отправить DM пользователю
        try:
            dm_embed = discord.Embed(
                title=t('warn_dm_title', guild_id=guild_id),
                description=t('warn_dm_description', guild_id=guild_id, server=ctx.guild.name),
                color=0xE67E22 if new_count < 3 else 0xE74C3C,
                timestamp=datetime.utcnow()
            )

            dm_embed.add_field(
                name=t('warn_reason', guild_id=guild_id),
                value=reason,
                inline=False
            )

            dm_embed.add_field(
                name=t('warn_dm_status', guild_id=guild_id),
                value=t('warn_dm_status_value', guild_id=guild_id, count=new_count),
                inline=True
            )

            dm_embed.add_field(
                name=t('warn_dm_info', guild_id=guild_id),
                value=t('warn_dm_info_value', guild_id=guild_id),
                inline=True
            )

            if new_count == 3:
                dm_embed.add_field(
                    name=t('warn_dm_critical', guild_id=guild_id),
                    value=t('warn_dm_critical_message', guild_id=guild_id),
                    inline=False
                )

            await member.send(embed=dm_embed)
        except:
            await ctx.send(t('warn_dm_failed', guild_id=guild_id))

    @commands.command(name='unwarn')
    @is_admin_or_whitelisted()
    async def unwarn_user(self, ctx, warning_id: int, *, reason: str = None):
        """Снять выговор по ID. Формат: !unwarn ID [причина]"""
        guild_id = ctx.guild.id

        # Получаем информацию о выговоре
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT user_id, warned_by, reason, is_active
            FROM warnings
            WHERE id = ?
        ''', (warning_id,))

        warning_data = cursor.fetchone()
        conn.close()

        if not warning_data:
            await ctx.send(t('unwarn_not_found', guild_id=guild_id, id=warning_id))
            return

        user_id, warned_by, warn_reason, is_active = warning_data

        if not is_active:
            await ctx.send(t('unwarn_already_removed', guild_id=guild_id, id=warning_id))
            return

        # Снимаем выговор
        if self.remove_warning(warning_id, ctx.author.id, reason):
            member = ctx.guild.get_member(user_id)
            member_name = member.mention if member else f"ID:{user_id}"

            # Получаем новое количество выговоров
            remaining = self.get_active_warnings_count(guild_id, user_id)

            embed = discord.Embed(
                title=t('unwarn_title', guild_id=guild_id),
                description=t('unwarn_description', guild_id=guild_id, id=warning_id, user=member_name),
                color=0x2ECC71,
                timestamp=datetime.utcnow()
            )

            embed.add_field(
                name=t('warn_user', guild_id=guild_id),
                value=member_name,
                inline=True
            )

            embed.add_field(
                name=t('unwarn_removed_by', guild_id=guild_id),
                value=f"{ctx.author.mention}\n`{ctx.author.name}`",
                inline=True
            )

            embed.add_field(
                name=t('unwarn_remaining', guild_id=guild_id),
                value=t('unwarn_remaining_value', guild_id=guild_id, count=remaining),
                inline=True
            )

            embed.add_field(
                name=t('unwarn_removal_reason', guild_id=guild_id),
                value=reason or t('unwarn_removal_reason', guild_id=guild_id),
                inline=False
            )

            embed.add_field(
                name=t('unwarn_original_reason', guild_id=guild_id),
                value=warn_reason,
                inline=False
            )

            await ctx.send(embed=embed)

            # Уведомляем пользователя
            if member:
                try:
                    dm_embed = discord.Embed(
                        title=t('unwarn_dm_title', guild_id=guild_id),
                        description=t('unwarn_dm_description', guild_id=guild_id, server=ctx.guild.name),
                        color=0x2ECC71,
                        timestamp=datetime.utcnow()
                    )

                    dm_embed.add_field(
                        name=t('unwarn_dm_status', guild_id=guild_id),
                        value=t('unwarn_dm_status_value', guild_id=guild_id, count=remaining),
                        inline=False
                    )

                    await member.send(embed=dm_embed)
                except:
                    pass
        else:
            await ctx.send(t('unwarn_error', guild_id=guild_id, id=warning_id))

    @commands.command(name='warnings')
    async def check_warnings(self, ctx, member: discord.Member = None):
        """Посмотреть выговоры пользователя. Формат: !warnings [@пользователь]"""
        guild_id = ctx.guild.id

        target = member or ctx.author

        # Обычные пользователи могут смотреть только свои выговоры
        if target != ctx.author:
            # Проверяем права
            if not (ctx.author.guild_permissions.administrator or self.bot.db.is_whitelisted(guild_id, ctx.author.id)):
                await ctx.send(t('warnings_no_permission', guild_id=guild_id))
                return

        # Получаем все выговоры
        warnings = self.get_user_warnings(guild_id, target.id)

        if not warnings:
            if target == ctx.author:
                await ctx.send(t('warnings_none_self', guild_id=guild_id))
            else:
                await ctx.send(t('warnings_none_user', guild_id=guild_id, user=target.mention))
            return

        # Считаем активные
        active_count = sum(1 for w in warnings if (len(w) == 5 or w[5] == 1))

        embed = discord.Embed(
            title=t('warnings_title', guild_id=guild_id),
            description=f"{target.mention}",
            color=0xE67E22 if active_count > 0 else 0x2ECC71,
            timestamp=datetime.utcnow()
        )

        embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)

        embed.add_field(
            name=t('warn_status', guild_id=guild_id),
            value=t('warnings_status_value', guild_id=guild_id, active=active_count, total=len(warnings)),
            inline=False
        )

        # Показываем активные выговоры
        active_warnings = [w for w in warnings if (len(w) == 5 or w[5] == 1)]

        if active_warnings:
            for w in active_warnings[:5]:  # Максимум 5
                warning_id = w[0]
                warned_by_id = w[1]
                reason = w[2]
                warned_at = datetime.fromisoformat(w[3])
                expires_at = datetime.fromisoformat(w[4])

                warner = ctx.guild.get_member(warned_by_id)
                warner_name = warner.name if warner else f"ID:{warned_by_id}"

                time_left = expires_at - datetime.utcnow()
                days_left = time_left.days
                hours_left = int(time_left.seconds // 3600)

                embed.add_field(
                    name=t('warnings_active_entry', guild_id=guild_id, id=warning_id),
                    value=t('warnings_active_info', guild_id=guild_id, reason=reason, issuer=warner_name, date=warned_at.strftime('%d.%m.%Y %H:%M'), days=days_left, hours=hours_left),
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
                    name=t('warnings_history', guild_id=guild_id),
                    value="\n".join(history_text),
                    inline=False
                )

        embed.set_footer(text=t('warnings_footer', guild_id=guild_id, user=ctx.author.name))

        await ctx.send(embed=embed)

    @commands.command(name='warnings_list')
    @is_admin_or_whitelisted()
    async def warnings_list(self, ctx):
        """Список всех пользователей с выговорами на сервере"""
        guild_id = ctx.guild.id

        warnings_data = self.get_all_warnings(guild_id, active_only=True)

        if not warnings_data:
            await ctx.send(t('warnings_list_none', guild_id=guild_id))
            return

        embed = discord.Embed(
            title=t('warnings_list_title', guild_id=guild_id),
            description=t('warnings_list_description', guild_id=guild_id, count=len(warnings_data)),
            color=0xE67E22,
            timestamp=datetime.utcnow()
        )

        # Группируем по количеству выговоров
        three_warns = []
        two_warns = []
        one_warn = []

        for user_id, count in warnings_data:
            member = ctx.guild.get_member(user_id)
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
                name=t('warnings_list_3', guild_id=guild_id),
                value="\n".join(three_warns[:10]),
                inline=False
            )

        if two_warns:
            embed.add_field(
                name=t('warnings_list_2', guild_id=guild_id),
                value="\n".join(two_warns[:15]),
                inline=False
            )

        if one_warn:
            # Показываем только первых 10 с 1 выговором
            value = "\n".join(one_warn[:10])
            if len(one_warn) > 10:
                value += f"\n{t('warnings_list_more', guild_id=guild_id, count=len(one_warn)-10)}"
            embed.add_field(
                name=t('warnings_list_1', guild_id=guild_id),
                value=value,
                inline=False
            )

        embed.set_footer(text=t('warnings_list_footer', guild_id=guild_id))

        await ctx.send(embed=embed)

    @commands.command(name='warnings_active')
    @is_admin_or_whitelisted()
    async def warnings_active_stats(self, ctx):
        """Статистика активных выговоров на сервере"""
        guild_id = ctx.guild.id

        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        # Общая статистика
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                COUNT(DISTINCT user_id) as unique_users
            FROM warnings
            WHERE guild_id = ? AND is_active = 1
        ''', (guild_id,))

        stats = cursor.fetchone()
        total_warnings, unique_users = stats

        # Топ нарушителей
        cursor.execute('''
            SELECT user_id, COUNT(*) as warning_count
            FROM warnings
            WHERE guild_id = ? AND is_active = 1
            GROUP BY user_id
            ORDER BY warning_count DESC
            LIMIT 100
        ''', (guild_id,))

        top_offenders = cursor.fetchall()

        conn.close()

        embed = discord.Embed(
            title=t('warnings_stats_title', guild_id=guild_id),
            description=t('warnings_stats_description', guild_id=guild_id),
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )

        embed.add_field(
            name=t('warnings_stats_total', guild_id=guild_id),
            value=t('warnings_stats_total_value', guild_id=guild_id, total=total_warnings, users=unique_users),
            inline=False
        )

        if top_offenders:
            offenders_text = []
            for i, (user_id, count) in enumerate(top_offenders, 1):
                member = ctx.guild.get_member(user_id)
                name = member.mention if member else f"ID:{user_id}"
                offenders_text.append(f"{i}. {name} - **{count}**/3 выговоров")

            embed.add_field(
                name=t('warnings_stats_offenders', guild_id=guild_id),
                value="\n".join(offenders_text),
                inline=False
            )

        embed.set_footer(text=t('warnings_stats_footer', guild_id=guild_id))

        await ctx.send(embed=embed)

    @commands.command(name='warnings_all')
    @is_admin_or_whitelisted()
    async def warnings_all_stats(self, ctx):
        """Полная статистика выговоров на сервере"""
        guild_id = ctx.guild.id

        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        # Общая статистика
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active,
                COUNT(DISTINCT user_id) as unique_users
            FROM warnings
            WHERE guild_id = ?
        ''', (guild_id,))

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
        ''', (guild_id,))

        top_offenders = cursor.fetchall()

        # Топ модераторов
        cursor.execute('''
            SELECT warned_by, COUNT(*) as warnings_given
            FROM warnings
            WHERE guild_id = ?
            GROUP BY warned_by
            ORDER BY warnings_given DESC
            LIMIT 5
        ''', (guild_id,))

        top_moderators = cursor.fetchall()

        conn.close()

        embed = discord.Embed(
            title=t('warnings_all_title', guild_id=guild_id),
            description=t('warnings_all_description', guild_id=guild_id),
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )

        embed.add_field(
            name=t('warnings_stats_total', guild_id=guild_id),
            value=t('warnings_all_total_value', guild_id=guild_id, total=total_warnings, active=active_warnings, users=unique_users),
            inline=False
        )

        if top_offenders:
            offenders_text = []
            for i, (user_id, count) in enumerate(top_offenders, 1):
                member = ctx.guild.get_member(user_id)
                name = member.mention if member else f"ID:{user_id}"
                offenders_text.append(f"{i}. {name} - **{count}** выговоров")

            embed.add_field(
                name=t('warnings_all_top_offenders', guild_id=guild_id),
                value="\n".join(offenders_text),
                inline=False
            )

        if top_moderators:
            mods_text = []
            for i, (mod_id, count) in enumerate(top_moderators, 1):
                member = ctx.guild.get_member(mod_id)
                name = member.mention if member else f"ID:{mod_id}"
                mods_text.append(f"{i}. {name} - **{count}** выданных")

            embed.add_field(
                name=t('warnings_all_top_mods', guild_id=guild_id),
                value="\n".join(mods_text),
                inline=False
            )

        embed.set_footer(text=t('warnings_stats_footer', guild_id=guild_id))

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(WarningSystem(bot))
