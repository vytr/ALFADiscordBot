import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from utils import is_admin_or_whitelisted

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
            return (False, "У пользователя уже 3 активных выговора (максимум)")
        
        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            
            # Выговор истекает через 7 дней
            
            expires_at = datetime.now(datetime.timezone.utc) + timedelta(days=7)
            
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
    
    def remove_warning(self, warning_id: int, removed_by: int, reason: str = "Снят вручную") -> bool:
        """Снять выговор вручную"""
        import sqlite3
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
                        removal_reason = 'Автоматически снят по истечении срока'
                    WHERE is_active = 1 AND expires_at <= CURRENT_TIMESTAMP
                ''')
                
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
                                    title="✅ Выговор снят",
                                    description=f"С вас автоматически снят один выговор на сервере **{guild.name}**",
                                    color=0x2ECC71,
                                    timestamp=datetime.utcnow()
                                )
                                
                                # Проверяем сколько осталось
                                remaining = self.get_active_warnings_count(guild_id, user_id)
                                embed.add_field(
                                    name="📊 Текущий статус",
                                    value=f"Активных выговоров: **{remaining}**/3",
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
        
        # Нельзя выдать выговор самому себе
        if member.id == ctx.author.id:
            await ctx.send("❌ Вы не можете выдать выговор самому себе!")
            return
        
        # Нельзя выдать выговор боту
        if member.bot:
            await ctx.send("❌ Нельзя выдать выговор боту!")
            return
        
        # Проверяем текущее количество выговоров
        current_warnings = self.get_active_warnings_count(ctx.guild.id, member.id)
        
        if current_warnings >= 3:
            await ctx.send(f"⚠️ У {member.mention} уже **3** активных выговора (максимум)!")
            return
        
        # Добавляем выговор
        success, result = self.add_warning(ctx.guild.id, member.id, ctx.author.id, reason)
        
        if not success:
            await ctx.send(f"❌ Ошибка при выдаче выговора: {result}")
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
            value=f"{ctx.author.mention}\n`{ctx.author.name}`",
            inline=True
        )
        
        embed.add_field(
            name="📊 Статус",
            value=f"**{new_count}**/3 выговора",
            inline=True
        )
        
        embed.add_field(
            name="📝 Причина",
            value=reason,
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
        
        await ctx.send(embed=embed)
        
        # Пытаемся отправить DM пользователю
        try:
            dm_embed = discord.Embed(
                title="⚠️ Вы получили выговор",
                description=f"Вам выдан выговор на сервере **{ctx.guild.name}**",
                color=0xE67E22 if new_count < 3 else 0xE74C3C,
                timestamp=datetime.utcnow()
            )
            
            dm_embed.add_field(
                name="📝 Причина",
                value=reason,
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
            await ctx.send("⚠️ Не удалось отправить уведомление пользователю в DM")
    
    @commands.command(name='unwarn')
    @is_admin_or_whitelisted()
    async def unwarn_user(self, ctx, warning_id: int, *, reason: str = "Снят модератором"):
        """Снять выговор по ID. Формат: !unwarn ID [причина]"""
        
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
            await ctx.send(f"❌ Выговор с ID `{warning_id}` не найден")
            return
        
        user_id, warned_by, warn_reason, is_active = warning_data
        
        if not is_active:
            await ctx.send(f"⚠️ Выговор `{warning_id}` уже снят")
            return
        
        # Снимаем выговор
        if self.remove_warning(warning_id, ctx.author.id, reason):
            member = ctx.guild.get_member(user_id)
            member_name = member.mention if member else f"ID:{user_id}"
            
            # Получаем новое количество выговоров
            remaining = self.get_active_warnings_count(ctx.guild.id, user_id)
            
            embed = discord.Embed(
                title="✅ Выговор снят",
                description=f"Выговор `{warning_id}` снят с пользователя {member_name}",
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
                value=f"{ctx.author.mention}\n`{ctx.author.name}`",
                inline=True
            )
            
            embed.add_field(
                name="📊 Осталось",
                value=f"**{remaining}**/3 выговора",
                inline=True
            )
            
            embed.add_field(
                name="📝 Причина снятия",
                value=reason,
                inline=False
            )
            
            embed.add_field(
                name="📋 Был выдан за",
                value=warn_reason,
                inline=False
            )
            
            await ctx.send(embed=embed)
            
            # Уведомляем пользователя
            if member:
                try:
                    dm_embed = discord.Embed(
                        title="✅ Выговор снят",
                        description=f"С вас снят выговор на сервере **{ctx.guild.name}**",
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
            await ctx.send(f"❌ Не удалось снять выговор `{warning_id}`")
    
    @commands.command(name='warnings')
    async def check_warnings(self, ctx, member: discord.Member = None):
        """Посмотреть выговоры пользователя. Формат: !warnings [@пользователь]"""
        
        target = member or ctx.author
        
        # Обычные пользователи могут смотреть только свои выговоры
        if target != ctx.author:
            # Проверяем права
            if not (ctx.author.guild_permissions.administrator or self.bot.db.is_whitelisted(ctx.guild.id, ctx.author.id)):
                await ctx.send("❌ Вы можете смотреть только свои выговоры!")
                return
        
        # Получаем все выговоры
        warnings = self.get_user_warnings(ctx.guild.id, target.id)
        
        if not warnings:
            if target == ctx.author:
                await ctx.send("✅ У вас нет выговоров!")
            else:
                await ctx.send(f"✅ У {target.mention} нет выговоров!")
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
        
        embed.set_footer(text=f"Запросил: {ctx.author.name}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='warnings_list')
    @is_admin_or_whitelisted()
    async def warnings_list(self, ctx):
        """Список всех пользователей с выговорами на сервере"""
        
        warnings_data = self.get_all_warnings(ctx.guild.id, active_only=True)
        
        if not warnings_data:
            await ctx.send("✅ На сервере нет пользователей с активными выговорами!")
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
            # Показываем только первых 10 с 1 выговором
            embed.add_field(
                name="⚡ 1 выговор",
                value="\n".join(one_warn[:10]) + (f"\n*...и еще {len(one_warn)-10}*" if len(one_warn) > 10 else ""),
                inline=False
            )
        
        embed.set_footer(text="💡 Используйте !warnings @пользователь для деталей")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='warnings_all')
    @is_admin_or_whitelisted()
    async def warnings_all_stats(self, ctx):
        """Полная статистика выговоров на сервере"""
        
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
        ''', (ctx.guild.id,))
        
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
        ''', (ctx.guild.id,))
        
        top_offenders = cursor.fetchall()
        
        # Топ модераторов
        cursor.execute('''
            SELECT warned_by, COUNT(*) as warnings_given
            FROM warnings
            WHERE guild_id = ?
            GROUP BY warned_by
            ORDER BY warnings_given DESC
            LIMIT 5
        ''', (ctx.guild.id,))
        
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
                member = ctx.guild.get_member(user_id)
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
                member = ctx.guild.get_member(mod_id)
                name = member.mention if member else f"ID:{mod_id}"
                mods_text.append(f"{i}. {name} - **{count}** выданных")
            
            embed.add_field(
                name="👮 Топ-5 модераторов",
                value="\n".join(mods_text),
                inline=False
            )
        
        embed.set_footer(text="💡 Выговоры снимаются автоматически через 7 дней")
        
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(WarningSystem(bot))
