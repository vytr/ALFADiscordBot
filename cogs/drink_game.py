import discord
from discord.ext import commands
from datetime import datetime, timedelta
import random
from utils import is_admin_or_whitelisted

class DrinkGame(commands.Cog):
    """Шуточная игра с напитками"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        
        # Инициализируем таблицу в БД
        self.init_drink_table()
    
    def init_drink_table(self):
        """Создание таблицы для статистики напитков"""
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS drink_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                drink_type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                drunk_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, user_id, drunk_at)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_last_drink_time(self, guild_id: int, user_id: int):
        """Получить время последнего напитка"""
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT drunk_at FROM drink_stats
            WHERE guild_id = ? AND user_id = ?
            ORDER BY drunk_at DESC LIMIT 1
        ''', (guild_id, user_id))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return datetime.fromisoformat(result[0])
        return None
    
    def add_drink(self, guild_id: int, user_id: int, drink_type: str, amount: int):
        """Добавить напиток в статистику"""
        import sqlite3
        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO drink_stats (guild_id, user_id, drink_type, amount)
                VALUES (?, ?, ?, ?)
            ''', (guild_id, user_id, drink_type, amount))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error adding drink: {e}")
            return False
    
    def get_user_stats(self, guild_id: int, user_id: int):
        """Получить статистику пользователя"""
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT drink_type, SUM(amount) as total
            FROM drink_stats
            WHERE guild_id = ? AND user_id = ?
            GROUP BY drink_type
        ''', (guild_id, user_id))
        
        results = cursor.fetchall()
        conn.close()
        
        return {drink_type: total for drink_type, total in results}
    
    def get_top_drinkers(self, guild_id: int, limit: int = 10):
        """Получить топ любителей выпить"""
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, SUM(amount) as total_amount
            FROM drink_stats
            WHERE guild_id = ?
            GROUP BY user_id
            ORDER BY total_amount DESC
            LIMIT ?
        ''', (guild_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def pluralize_liters(self, amount: int) -> str:
        """Склонение слова 'литр'"""
        if amount % 10 == 1 and amount % 100 != 11:
            return "литр"
        elif amount % 10 in [2, 3, 4] and amount % 100 not in [12, 13, 14]:
            return "литра"
        else:
            return "литров"
    
    def pluralize_drink(self, drink_type: str, amount: int) -> str:
        """Склонение названия напитка"""
        declensions = {
            "чай": {
                1: "чая",
                2: "чая",
                5: "чая"
            },
            "пиво": {
                1: "пива",
                2: "пива",
                5: "пива"
            },
            "виски": {
                1: "виски",
                2: "виски",
                5: "виски"
            }
        }
        
        if amount % 10 == 1 and amount % 100 != 11:
            key = 1
        elif amount % 10 in [2, 3, 4] and amount % 100 not in [12, 13, 14]:
            key = 2
        else:
            key = 5
        
        return declensions.get(drink_type, {}).get(key, drink_type)
    
    @commands.command(name='drink')
    async def drink(self, ctx):
        """Выпить случайный напиток! Доступно раз в 8 часов."""
        
        # Проверяем cooldown
        last_drink = self.get_last_drink_time(ctx.guild.id, ctx.author.id)
        
        if last_drink:
            time_passed = datetime.utcnow() - last_drink
            cooldown = timedelta(hours=8)
            
            if time_passed < cooldown:
                time_left = cooldown - time_passed
                hours = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)
                
                await ctx.send(f"🍺 {ctx.author.mention}, вы уже пили! Следующий напиток будет доступен через **{hours}ч {minutes}м**")
                return
        
        # Генерируем случайные данные
        drinks = ["чай", "пиво", "виски"]
        drink_type = random.choice(drinks)
        amount = random.randint(1, 10)
        
        # Добавляем в статистику
        self.add_drink(ctx.guild.id, ctx.author.id, drink_type, amount)
        
        # Получаем общую статистику пользователя
        user_stats = self.get_user_stats(ctx.guild.id, ctx.author.id)
        
        # Формируем красивое сообщение
        liters_word = self.pluralize_liters(amount)
        drink_word = self.pluralize_drink(drink_type, amount)
        
        # Эмодзи для напитков
        drink_emoji = {
            "чай": "🍵",
            "пиво": "🍺",
            "виски": "🥃"
        }
        
        embed = discord.Embed(
            title=f"{drink_emoji.get(drink_type, '🍷')} Напиток подан!",
            description=f"{ctx.author.mention} выпил **{amount} {liters_word} {drink_word}**!",
            color=0xF1C40F,
            timestamp=datetime.utcnow()
        )
        
        # Добавляем общую статистику
        if user_stats:
            stats_text = []
            total_all = 0
            
            for drink, total in sorted(user_stats.items(), key=lambda x: x[1], reverse=True):
                emoji = drink_emoji.get(drink, "🍷")
                liters = self.pluralize_liters(total)
                stats_text.append(f"{emoji} **{drink.capitalize()}:** {total} {liters}")
                total_all += total
            
            embed.add_field(
                name="📊 Ваша статистика",
                value="\n".join(stats_text) + f"\n\n**Всего выпито:** {total_all} {self.pluralize_liters(total_all)}",
                inline=False
            )
        
        # Случайные комментарии
        comments = [
            "Отличный выбор! 🎉",
            "За здоровье! 🥂",
            "Пейте ответственно! 😄",
            "Ещё по одной? Нет, через 8 часов! ⏰",
            "Вкусно? 😋",
            "Классно пошло! 👌",
            "Приятного аппетита! 🍻",
            "Налил от души! 💪"
        ]
        
        embed.set_footer(text=random.choice(comments))
        
        await ctx.send(embed=embed)
    
    @commands.command(name='drink_top')
    @is_admin_or_whitelisted()
    async def drink_top(self, ctx, limit: int = 10):
        """Топ любителей выпить. Формат: !drink_top [количество]"""
        
        if limit < 1 or limit > 50:
            await ctx.send("❌ Укажите число от 1 до 50")
            return
        
        top_drinkers = self.get_top_drinkers(ctx.guild.id, limit)
        
        if not top_drinkers:
            await ctx.send("📊 Пока никто ничего не пил!")
            return
        
        embed = discord.Embed(
            title=f"🏆 Топ-{len(top_drinkers)} любителей выпить",
            description=f"Самые активные участники команды **/drink** на сервере!",
            color=0xE67E22,
            timestamp=datetime.utcnow()
        )
        
        top_text = []
        for i, (user_id, total_amount) in enumerate(top_drinkers, 1):
            member = ctx.guild.get_member(user_id)
            
            if member:
                # Медали для топ-3
                if i == 1:
                    medal = "🥇"
                elif i == 2:
                    medal = "🥈"
                elif i == 3:
                    medal = "🥉"
                else:
                    medal = f"`{i}.`"
                
                liters = self.pluralize_liters(total_amount)
                
                # Получаем детальную статистику
                import sqlite3
                conn = sqlite3.connect(self.db.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT drink_type, SUM(amount) as total
                    FROM drink_stats
                    WHERE guild_id = ? AND user_id = ?
                    GROUP BY drink_type
                    ORDER BY total DESC
                ''', (ctx.guild.id, user_id))
                
                drinks = cursor.fetchall()
                conn.close()
                
                # Формируем строку с любимым напитком
                if drinks:
                    favorite_drink = drinks[0][0]
                    drink_emoji = {"чай": "🍵", "пиво": "🍺", "виски": "🥃"}
                    favorite_emoji = drink_emoji.get(favorite_drink, "🍷")
                    top_text.append(f"{medal} **{member.display_name}**: {total_amount} {liters} {favorite_emoji}")
                else:
                    top_text.append(f"{medal} **{member.display_name}**: {total_amount} {liters}")
        
        embed.add_field(
            name="📋 Рейтинг",
            value="\n".join(top_text) if top_text else "Пусто",
            inline=False
        )
        
        # Общая статистика сервера
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT drink_type, SUM(amount) as total
            FROM drink_stats
            WHERE guild_id = ?
            GROUP BY drink_type
            ORDER BY total DESC
        ''', (ctx.guild.id,))
        
        server_drinks = cursor.fetchall()
        conn.close()
        
        if server_drinks:
            drink_emoji = {"чай": "🍵", "пиво": "🍺", "виски": "🥃"}
            server_stats = []
            total_server = 0
            
            for drink_type, total in server_drinks:
                emoji = drink_emoji.get(drink_type, "🍷")
                liters = self.pluralize_liters(total)
                server_stats.append(f"{emoji} **{drink_type.capitalize()}**: {total} {liters}")
                total_server += total
            
            embed.add_field(
                name="📊 Статистика сервера",
                value="\n".join(server_stats) + f"\n\n🍻 **Всего выпито:** {total_server} {self.pluralize_liters(total_server)}",
                inline=False
            )
        
        embed.set_footer(text="💡 Используйте !drink чтобы участвовать!")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='drink_stats')
    async def drink_stats(self, ctx, member: discord.Member = None):
        """Посмотреть статистику напитков пользователя. Формат: !drink_stats [@пользователь]"""
        
        target = member or ctx.author
        
        # Получаем статистику
        user_stats = self.get_user_stats(ctx.guild.id, target.id)
        
        if not user_stats:
            if target == ctx.author:
                await ctx.send(f"🍺 {ctx.author.mention}, вы еще ничего не пили! Используйте `!drink`")
            else:
                await ctx.send(f"🍺 {target.mention} еще ничего не пил!")
            return
        
        embed = discord.Embed(
            title=f"📊 Статистика напитков",
            description=f"Данные пользователя {target.mention}",
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )
        
        embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)
        
        # Статистика по напиткам
        drink_emoji = {"чай": "🍵", "пиво": "🍺", "виски": "🥃"}
        stats_text = []
        total_all = 0
        
        for drink, total in sorted(user_stats.items(), key=lambda x: x[1], reverse=True):
            emoji = drink_emoji.get(drink, "🍷")
            liters = self.pluralize_liters(total)
            
            # Визуальная полоса
            max_amount = max(user_stats.values())
            bar_length = int((total / max_amount) * 10) if max_amount > 0 else 0
            bar = "█" * bar_length + "░" * (10 - bar_length)
            
            stats_text.append(f"{emoji} **{drink.capitalize()}**\n`{bar}` {total} {liters}")
            total_all += total
        
        embed.add_field(
            name="🍻 По напиткам",
            value="\n\n".join(stats_text),
            inline=False
        )
        
        embed.add_field(
            name="📈 Всего выпито",
            value=f"**{total_all}** {self.pluralize_liters(total_all)}",
            inline=True
        )
        
        # Любимый напиток
        favorite = max(user_stats.items(), key=lambda x: x[1])
        favorite_emoji = drink_emoji.get(favorite[0], "🍷")
        embed.add_field(
            name="⭐ Любимый напиток",
            value=f"{favorite_emoji} **{favorite[0].capitalize()}**",
            inline=True
        )
        
        # Место в рейтинге
        top_drinkers = self.get_top_drinkers(ctx.guild.id, 1000)
        user_rank = None
        for i, (user_id, _) in enumerate(top_drinkers, 1):
            if user_id == target.id:
                user_rank = i
                break
        
        if user_rank:
            embed.add_field(
                name="🏆 Место в рейтинге",
                value=f"**#{user_rank}** из {len(top_drinkers)}",
                inline=True
            )
        
        # Проверяем cooldown
        last_drink = self.get_last_drink_time(ctx.guild.id, target.id)
        if last_drink and target == ctx.author:
            time_passed = datetime.utcnow() - last_drink
            cooldown = timedelta(hours=8)
            
            if time_passed < cooldown:
                time_left = cooldown - time_passed
                hours = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)
                embed.set_footer(text=f"⏰ Следующий напиток через {hours}ч {minutes}м")
            else:
                embed.set_footer(text="✅ Можно выпить снова! Используйте !drink")
        
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(DrinkGame(bot))
