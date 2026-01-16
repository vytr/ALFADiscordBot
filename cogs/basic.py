import discord
from discord.ext import commands
from datetime import datetime
from utils import is_admin_or_whitelisted
import io
import random

class Basic(commands.Cog):
    """Базовые команды для бота"""

    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.command(name='alfa_ping')
    @is_admin_or_whitelisted()
    async def ping(self, ctx):
        """Проверка задержки бота"""
        print("ping call")
        await ctx.message.delete()
        latency = round(self.bot.latency * 1000)
        await ctx.send(f'🏓 Понг! Задержка: {latency}ms')

    @commands.command(name='alfa_info')
    @is_admin_or_whitelisted()
    async def info(self, ctx):
        """Информация о боте"""
        await ctx.message.delete()
        embed = discord.Embed(
            title="Информация о боте",
            description="Discord бот на Python",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="Серверов", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="Пользователей", value=len(self.bot.users), inline=True)
        embed.add_field(name="Версия Discord.py", value=discord.__version__, inline=True)

        embed.set_footer(text=f"Запрошено {ctx.author}", icon_url=ctx.author.display_avatar.url)

        await ctx.send(embed=embed)

    @commands.command(name='alfa_hello')
    @is_admin_or_whitelisted()
    async def hello(self, ctx):
        """Поздороваться с ботом"""
        await ctx.message.delete()
        await ctx.send(f'Привет, {ctx.author.mention}! 👋')

    @commands.command(name='alfa_say')
    @is_admin_or_whitelisted()
    async def say(self, ctx, *, message: str):
        print("say call")
        """Заставить бота повторить сообщение"""
        await ctx.message.delete()
        await ctx.send(message)

    # @commands.Cog.listener()
    # async def on_member_join(self, member):
    #     """Приветствие новых участников"""
    #     channel = member.guild.system_channel
    #     if channel is not None:
    #         embed = discord.Embed(
    #             description=f'Добро пожаловать на сервер, {member.mention}!',
    #             color=discord.Color.green()
    #         )
    #         await channel.send(embed=embed)

    @commands.command(name='alfa_duel')
    async def duel(self,ctx, opponent: discord.Member):
        if opponent == ctx.author:
            await ctx.send("Вы не можете драться сами с собой!")
            return

        await ctx.send(f"{ctx.author.mention} вызывает {opponent.mention} на дуэль!")

        # Генерируем случайные силы для обоих участников
        player1_power = random.randint(1, 100)
        player2_power = random.randint(1, 100)

        await ctx.send(f"Сила {ctx.author.mention}: {player1_power}")
        await ctx.send(f"Сила {opponent.mention}: {player2_power}")

        # Определяем победителя
        if player1_power > player2_power:
            await ctx.send(f"{ctx.author.mention} выигрывает дуэль!")
        elif player1_power < player2_power:
            await ctx.send(f"{opponent.mention} выигрывает дуэль!")
        else:
            await ctx.send("Дуэль окончилась вничью!")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Обработка добавления реакции на опрос"""
        # Игнорируем реакции от самого бота
        if payload.user_id == self.bot.user.id:
            return

        # Проверяем, является ли сообщение опросом
        poll_data = self.db.get_poll_by_message(payload.message_id)
        if not poll_data:
            return

        poll_id = poll_data[0]

        # Проверяем, закрыт ли опрос
        if self.db.is_poll_closed(poll_id):
            # Удаляем реакцию на закрытый опрос
            channel = self.bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            await message.remove_reaction(payload.emoji, payload.member)
            return

        # Получаем допустимые эмодзи для этого опроса
        poll_options = self.db.get_poll_options(poll_id)
        valid_emojis = {option[2]: option[0] for option in poll_options}  # emoji -> option_index

        # Проверяем, является ли эмодзи допустимым для этого опроса
        emoji_str = str(payload.emoji)
        if emoji_str not in valid_emojis:
            # Удаляем недопустимую реакцию
            channel = self.bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            await message.remove_reaction(payload.emoji, payload.member)
            return

        # Сохраняем голос в БД
        option_index = valid_emojis[emoji_str]
        self.db.add_vote(poll_id, payload.user_id, option_index)
        print(f"Vote added: poll_id={poll_id}, user_id={payload.user_id}, option={option_index}")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """Обработка удаления реакции с опроса"""
        # Игнорируем реакции от самого бота
        if payload.user_id == self.bot.user.id:
            return

        # Проверяем, является ли сообщение опросом
        poll_data = self.db.get_poll_by_message(payload.message_id)
        if not poll_data:
            return

        poll_id = poll_data[0]

        # Проверяем, закрыт ли опрос
        if self.db.is_poll_closed(poll_id):
            # Не обрабатываем удаление реакций на закрытый опрос
            print(f"Vote removal ignored for closed poll: poll_id={poll_id}")
            return

        # Получаем допустимые эмодзи для этого опроса
        poll_options = self.db.get_poll_options(poll_id)
        valid_emojis = {option[2]: option[0] for option in poll_options}

        # Проверяем, является ли эмодзи допустимым
        emoji_str = str(payload.emoji)
        if emoji_str not in valid_emojis:
            return

        # Удаляем голос из БД
        option_index = valid_emojis[emoji_str]
        self.db.remove_vote(poll_id, payload.user_id, option_index)
        print(f"Vote removed: poll_id={poll_id}, user_id={payload.user_id}, option={option_index}")

    @commands.command(name='alfa_poll')
    @is_admin_or_whitelisted()
    async def poll(self, ctx, *, question):
        """Создание опроса формата: !poll Вопрос | Вариант1 | Вариант2 | ... МАКСИМУМ 10 ВАРИАНТОВ"""
        await ctx.message.delete()
        parts = [p.strip() for p in question.split("|")]
        if len(parts) < 3:
            await ctx.send("Формат: !poll Вопрос | Вариант1 | Вариант2")
            return

        q = parts[0]
        options = parts[1:]

        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

        if len(options) > len(emojis):
            await ctx.send(f"Максимум {len(emojis)} вариантов ответа!")
            return

        description = ""
        for i, option in enumerate(options):
            description += f"{emojis[i]} {option}\n"

        # Сначала отправляем сообщение без ID
        embed = discord.Embed(title="📊 Опрос", description=f"**{q}**\n\n{description}")
        msg = await ctx.send(embed=embed)

        # Добавляем реакции
        for i in range(len(options)):
            await msg.add_reaction(emojis[i])

        # Сохраняем опрос в БД и получаем ID
        poll_id = self.db.create_poll(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            message_id=msg.id,
            question=q,
            options=options,
            emojis=emojis[:len(options)],
            created_by=ctx.author.id
        )

        # Обновляем сообщение с ID опроса
        if poll_id:
            embed.set_footer(text=f"ID опроса: {poll_id}")
            await msg.edit(embed=embed)
        else:
            await ctx.send("⚠️ Ошибка при сохранении опроса в БД")

    @commands.command(name='alfa_poll_results')
    @is_admin_or_whitelisted()
    async def poll_results(self, ctx, poll_id: str):
        """Показать результаты опроса по ID"""
        await ctx.message.delete()
        results = self.db.get_poll_results(poll_id)

        if not results:
            await ctx.send(f"❌ Опрос с ID `{poll_id}` не найден")
            return

        # Формируем embed с результатами
        status = "🔒 Закрыт" if results['is_closed'] else "🔓 Активен"
        embed = discord.Embed(
            title=f"📊 Результаты опроса {status}",
            description=f"**{results['question']}**",
            color=discord.Color.red() if results['is_closed'] else discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        # Группируем голоса по вариантам ответа
        votes_by_option = {}
        for user_id, option_index, voted_at in results['votes']:
            if option_index not in votes_by_option:
                votes_by_option[option_index] = []
            votes_by_option[option_index].append(user_id)

        # Выводим каждый вариант с пользователями
        for option_index, option_text, emoji in results['options']:
            voters = votes_by_option.get(option_index, [])
            vote_count = len(voters)

            # Формируем список пользователей
            if voters:
                user_mentions = []
                for user_id in voters:
                    member = ctx.guild.get_member(user_id)
                    if member:
                        user_mentions.append(member.mention)
                    else:
                        user_mentions.append(f"<@{user_id}>")

                voters_text = ", ".join(user_mentions)
            else:
                voters_text = "Никто не проголосовал"

            embed.add_field(
                name=f"{emoji} {option_text} — {vote_count} голосов",
                value=voters_text,
                inline=False
            )

        embed.set_footer(text=f"ID опроса: {poll_id}")
        await ctx.send(embed=embed)

    @commands.command(name='alfa_poll_close')
    @is_admin_or_whitelisted()
    async def poll_close(self, ctx, poll_id: str):
        """Закрыть опрос по ID (новые голоса не будут учитываться)"""
        await ctx.message.delete()
        # Проверяем, существует ли опрос
        results = self.db.get_poll_results(poll_id)
        if not results:
            await ctx.send(f"❌ Опрос с ID `{poll_id}` не найден")
            return

        # Проверяем, не закрыт ли уже
        if results['is_closed']:
            await ctx.send(f"⚠️ Опрос `{poll_id}` уже закрыт")
            return

        # Закрываем опрос
        if self.db.close_poll(poll_id):
            embed = discord.Embed(
                title="🔒 Опрос закрыт",
                description=f"**{results['question']}**\n\nОпрос закрыт. Новые голоса не принимаются.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"ID опроса: {poll_id}")
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Ошибка при закрытии опроса")

    @commands.command(name='alfa_poll_close_all')
    @is_admin_or_whitelisted()
    async def poll_close_all(self, ctx):
        """Закрыть все открытые опросы на сервере"""
        await ctx.message.delete()

        # Закрываем все опросы
        closed_count = self.db.close_all_open_polls(ctx.guild.id)

        if closed_count == 0:
            await ctx.send("⚠️ Нет открытых опросов для закрытия")
            return

        embed = discord.Embed(
            title="🔒 Опросы закрыты",
            description=f"Закрыто опросов: **{closed_count}**\n\nВсе открытые опросы больше не принимают голоса.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @commands.command(name='alfa_poll_list')
    @is_admin_or_whitelisted()
    async def poll_list(self, ctx, days: int = 7):
        await ctx.message.delete()
        """Показать список опросов за последние N дней (7/14/30/90)"""
        # Проверяем допустимые значения
        if days not in [7, 14, 30, 90]:
            await ctx.send("❌ Допустимые значения: 7, 14, 30 или 90 дней")
            return

        polls = self.db.get_polls_by_date(ctx.guild.id, days)

        if not polls:
            await ctx.send(f"📋 Опросов за последние {days} дней не найдено")
            return

        # Формируем embed со списком опросов
        embed = discord.Embed(
            title=f"📋 Опросы за последние {days} дней",
            description=f"Всего опросов: {len(polls)}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        for poll_id, question, created_by, created_at, is_closed in polls:
            status = "🔒" if is_closed else "🔓"
            creator = ctx.guild.get_member(created_by)
            creator_name = creator.name if creator else f"ID:{created_by}"

            embed.add_field(
                name=f"{status} {poll_id}",
                value=f"**{question}**\nСоздал: {creator_name}\nДата: {created_at}",
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.command(name='alfa_poll_export')
    @is_admin_or_whitelisted()
    async def poll_export(self, ctx, poll_id: str):
        """Экспортировать опрос в CSV файл"""
        await ctx.message.delete()
        # Получаем данные опроса
        csv_data = self.db.export_poll_to_csv(poll_id, ctx.guild)

        if not csv_data:
            await ctx.send(f"❌ Опрос с ID `{poll_id}` не найден")
            return

        # Создаем файл
        file = discord.File(
            io.BytesIO(csv_data.encode('utf-8-sig')),  # utf-8-sig для правильного отображения в Excel
            filename=f'poll_{poll_id}.csv'
        )

        await ctx.send(f"📊 Экспорт опроса `{poll_id}`", file=file)
    
    @commands.command(name='alfa_poll_export_detail')
    @is_admin_or_whitelisted()
    async def poll_export_detail(self, ctx, poll_id: str, days: int = 7):
        """
        Экспортировать опрос с детальной статистикой активности. 
        Формат: !alfa_poll_export_detail ID [период_в_днях]
        
        Пример: !alfa_poll_export_detail abc123 7
        """
        await ctx.message.delete()
        
        # Проверяем период
        if days not in [7, 14, 30]:
            await ctx.send("❌ Допустимые периоды: 7, 14 или 30 дней", delete_after=10)
            return
        
        # Получаем данные опроса с детальной статистикой
        csv_data = self.db.export_poll_to_csv_detailed(poll_id, ctx.guild, days)

        if not csv_data:
            await ctx.send(f"❌ Опрос с ID `{poll_id}` не найден", delete_after=10)
            return

        # Создаем файл
        file = discord.File(
            io.BytesIO(csv_data.encode('utf-8-sig')),
            filename=f'poll_{poll_id}_detailed_{days}days.csv'
        )

        embed = discord.Embed(
            title="📊 Детальный экспорт опроса",
            description=f"Опрос `{poll_id}` с статистикой активности за **{days} дней**",
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📋 Что в файле?",
            value=(
                f"• Результаты голосования\n"
                f"• Статистика активности каждого пользователя:\n"
                f"  - Количество сообщений за {days} дней\n"
                f"  - Время в голосовых каналах за {days} дней\n"
                f"• Сортировка: по времени в войсе (больше → меньше)\n"
                f"• Формат: Username | X msg | Yh Zm"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Запросил: {ctx.author.name}")

        await ctx.send(embed=embed, file=file)

    @commands.command(name='alfa_poll_export_batch')
    @is_admin_or_whitelisted()
    async def poll_export_batch(self, ctx, period: str = "all"):
        """Экспортировать опросы за период (7/14/30/90/all)"""
        await ctx.message.delete()
        # Определяем период
        if period == "all":
            polls = self.db.get_all_polls(ctx.guild.id)
            period_text = "все время"
        elif period in ["7", "14", "30", "90"]:
            days = int(period)
            polls = self.db.get_polls_by_date(ctx.guild.id, days)
            period_text = f"последние {days} дней"
        else:
            await ctx.send("❌ Допустимые значения: 7, 14, 30, 90 или all")
            return

        if not polls:
            await ctx.send(f"📋 Опросов за {period_text} не найдено")
            return

        # Получаем ID всех опросов
        poll_ids = [poll[0] for poll in polls]

        # Экспортируем все опросы
        csv_data = self.db.export_polls_to_csv(poll_ids, ctx.guild)

        if not csv_data:
            await ctx.send(f"❌ Не удалось экспортировать опросы")
            return

        # Создаем файл
        file = discord.File(
            io.BytesIO(csv_data.encode('utf-8-sig')),  # utf-8-sig для правильного отображения в Excel
            filename=f'polls_{period}.csv'
        )

        await ctx.send(f"📊 Экспорт опросов за {period_text} (всего: {len(poll_ids)})", file=file)

async def setup(bot):
    await bot.add_cog(Basic(bot))
