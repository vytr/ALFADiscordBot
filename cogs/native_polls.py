import discord
from discord.ext import commands
from datetime import datetime
import io
import csv
from io import StringIO
from utils import is_admin_or_whitelisted


class NativePollSystem(commands.Cog):
    """Автоматическое отслеживание ВСЕХ опросов Discord на сервере"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
    
    @commands.Cog.listener()
    async def on_raw_poll_vote_add(self, payload):
        """Отслеживание добавления голоса в ЛЮБОМ опросе (RAW событие - работает всегда!)"""
        try:
            # payload содержит: user_id, channel_id, message_id, guild_id, answer_id
            
            # Получаем сообщение с опросом
            channel = self.bot.get_channel(payload.channel_id)
            if not channel:
                return
            
            message = await channel.fetch_message(payload.message_id)
            poll = message.poll
            
            if not poll:
                return
            
            # Проверяем, зарегистрирован ли опрос
            poll_data = self.db.get_poll(payload.message_id)
            
            if not poll_data:
                # Первый голос - регистрируем опрос автоматически
                # Извлекаем варианты ответов из опроса
                options = [answer.text for answer in poll.answers] if poll.answers else None
                
                self.db.register_poll(
                    message_id=payload.message_id,
                    guild_id=payload.guild_id if payload.guild_id else 0,
                    channel_id=payload.channel_id,
                    question=poll.question,
                    answers=options
                )
                print(f"📊 New poll discovered: {payload.message_id} - {poll.question[:50]}")
                print(f"   Options: {options}")
            
            # Сохраняем голос
            self.db.add_poll_vote(
                message_id=payload.message_id,
                user_id=payload.user_id,
                answer_id=payload.answer_id
            )
            
            print(f"✅ Vote added: poll={payload.message_id}, user={payload.user_id}, answer={payload.answer_id}")
            
        except Exception as e:
            print(f"Error in on_raw_poll_vote_add: {e}")
            import traceback
            traceback.print_exc()
    
    @commands.Cog.listener()
    async def on_raw_poll_vote_remove(self, payload):
        """Отслеживание удаления голоса из ЛЮБОГО опроса (RAW событие - работает всегда!)"""
        try:
            # Удаляем голос из БД
            self.db.remove_poll_vote(
                message_id=payload.message_id,
                user_id=payload.user_id,
                answer_id=payload.answer_id
            )
            
            print(f"❌ Vote removed: poll={payload.message_id}, user={payload.user_id}, answer={payload.answer_id}")
            
        except Exception as e:
            print(f"Error in on_raw_poll_vote_remove: {e}")
            import traceback
            traceback.print_exc()
    
    @commands.command(name='poll_results')
    @is_admin_or_whitelisted()
    async def poll_results(self, ctx, message_id_or_link: str):
        """
        Показать результаты опроса с именами проголосовавших.
        
        Формат: 
        !poll_results <message_id>
        !poll_results <ссылка на сообщение>
        
        Как получить ссылку: ПКМ на опросе -> Копировать ссылку на сообщение
        """
        await ctx.message.delete()
        
        # Парсим ID из ссылки или используем как ID
        msg_id = None
        
        # Проверяем, это ссылка?
        if 'discord.com/channels/' in message_id_or_link or 'discordapp.com/channels/' in message_id_or_link:
            # Формат: https://discord.com/channels/GUILD_ID/CHANNEL_ID/MESSAGE_ID
            try:
                parts = message_id_or_link.rstrip('/').split('/')
                msg_id = int(parts[-1])  # Последняя часть - это message_id
                print(f"📎 Parsed message ID from link: {msg_id}")
            except (ValueError, IndexError):
                await ctx.send("❌ Неверный формат ссылки", delete_after=10)
                return
        else:
            # Это просто ID
            try:
                msg_id = int(message_id_or_link)
            except ValueError:
                await ctx.send("❌ Неверный формат ID или ссылки", delete_after=10)
                return
        
        poll_data = self.db.get_poll(msg_id)
        
        if not poll_data:
            await ctx.send(f"❌ Опрос не найден. Возможно, никто еще не голосовал.", delete_after=10)
            return
        
        # Получаем голоса из БД
        votes = self.db.get_poll_votes(msg_id)
        
        if not votes:
            await ctx.send(f"❌ В опросе нет голосов", delete_after=10)
            return
        
        # Пытаемся получить сообщение с опросом
        poll = None
        poll_question = poll_data['question']
        is_finalized = True  # По умолчанию считаем завершенным если сообщение недоступно
        poll_answers = []
        
        try:
            channel = self.bot.get_channel(poll_data['channel_id'])
            if channel:
                message = await channel.fetch_message(msg_id)
                poll = message.poll
                
                if poll:
                    poll_question = poll.question
                    is_finalized = poll.is_finalized()
                    poll_answers = poll.answers
        except discord.NotFound:
            # Сообщение удалено - работаем только с данными из БД
            print(f"⚠️ Poll message {msg_id} not found, using DB data only")
        except Exception as e:
            print(f"⚠️ Error fetching poll message: {e}")
        
        # Группируем голоса по вариантам
        votes_by_answer = {}  # {answer_id: [user_ids]}
        for user_id, answer_id, voted_at in votes:
            if answer_id not in votes_by_answer:
                votes_by_answer[answer_id] = []
            votes_by_answer[answer_id].append(user_id)
        
        # Формируем embed с результатами
        embed = discord.Embed(
            title=f"📊 Результаты опроса {'(завершен)' if is_finalized else '(активен)'}",
            description=f"**{poll_question}**",
            color=0xE74C3C if is_finalized else 0x3498DB,
            timestamp=datetime.utcnow()
        )
        
        total_votes = len(votes)
        
        # Если у нас есть данные из опроса - используем их
        if poll and poll_answers:
            for i, answer in enumerate(poll_answers):
                voters = votes_by_answer.get(answer.id, [])
                count = len(voters)
                percentage = (count / total_votes * 100) if total_votes > 0 else 0
                
                bar_length = int(percentage / 5)
                bar = "█" * bar_length + "░" * (20 - bar_length)
                
                if voters:
                    voter_names = []
                    for user_id in voters[:10]:
                        member = ctx.guild.get_member(user_id)
                        voter_names.append(member.mention if member else f"<@{user_id}>")
                    
                    voters_text = ", ".join(voter_names)
                    if len(voters) > 10:
                        voters_text += f" *+{len(voters) - 10}*"
                else:
                    voters_text = "*Нет голосов*"
                
                emoji = ["🥇", "🥈", "🥉"][i] if i < 3 and count > 0 else "📊"
                
                embed.add_field(
                    name=f"{emoji} {answer.text}",
                    value=f"`{bar}` **{count}** ({percentage:.1f}%)\n{voters_text}",
                    inline=False
                )
        else:
            # Опрос недоступен - показываем данные из БД
            poll_options = self.db.get_poll_options(msg_id)
            
            if poll_options:
                # Есть сохраненные варианты ответов
                for answer_id, answer_text in poll_options:
                    voters = votes_by_answer.get(answer_id, [])
                    count = len(voters)
                    percentage = (count / total_votes * 100) if total_votes > 0 else 0
                    
                    bar_length = int(percentage / 5)
                    bar = "█" * bar_length + "░" * (20 - bar_length)
                    
                    if voters:
                        voter_names = []
                        for user_id in voters[:10]:
                            member = ctx.guild.get_member(user_id)
                            voter_names.append(member.mention if member else f"<@{user_id}>")
                        
                        voters_text = ", ".join(voter_names)
                        if len(voters) > 10:
                            voters_text += f" *+{len(voters) - 10}*"
                    else:
                        voters_text = "*Нет голосов*"
                    
                    # Определяем emoji по количеству голосов
                    sorted_counts = sorted([(aid, len(votes_by_answer.get(aid, []))) for aid, _ in poll_options], key=lambda x: x[1], reverse=True)
                    rank = next((i for i, (aid, _) in enumerate(sorted_counts) if aid == answer_id), None)
                    emoji = ["🥇", "🥈", "🥉"][rank] if rank is not None and rank < 3 and count > 0 else "📊"
                    
                    embed.add_field(
                        name=f"{emoji} {answer_text}",
                        value=f"`{bar}` **{count}** ({percentage:.1f}%)\n{voters_text}",
                        inline=False
                    )
            else:
                # Нет сохраненных вариантов - показываем упрощенно
                embed.add_field(
                    name="⚠️ Опрос недоступен",
                    value="Сообщение с опросом было удалено. Показаны данные из базы:",
                    inline=False
                )
                
                # Группируем по answer_id и показываем кто проголосовал
                for answer_id in sorted(votes_by_answer.keys()):
                    voters = votes_by_answer[answer_id]
                    count = len(voters)
                    percentage = (count / total_votes * 100) if total_votes > 0 else 0
                    
                    bar_length = int(percentage / 5)
                    bar = "█" * bar_length + "░" * (20 - bar_length)
                    
                    voter_names = []
                    for user_id in voters[:10]:
                        member = ctx.guild.get_member(user_id)
                        voter_names.append(member.mention if member else f"<@{user_id}>")
                    
                    voters_text = ", ".join(voter_names)
                    if len(voters) > 10:
                        voters_text += f" *+{len(voters) - 10}*"
                    
                    embed.add_field(
                        name=f"📊 Вариант #{answer_id + 1}",
                        value=f"`{bar}` **{count}** ({percentage:.1f}%)\n{voters_text}",
                        inline=False
                    )
        
        # Статистика
        embed.add_field(name="📈 Всего", value=f"{total_votes} голосов", inline=True)
        embed.add_field(name="⏰ Статус", value="🔒 Завершен" if is_finalized else "🔓 Активен", inline=True)
        
        # Добавляем ссылку на опрос
        poll_link = f"https://discord.com/channels/{ctx.guild.id}/{poll_data['channel_id']}/{msg_id}"
        embed.add_field(name="🔗 Ссылка", value=f"[Перейти к опросу]({poll_link})", inline=True)
        
        embed.set_footer(text=f"ID: {msg_id} | {ctx.author.name}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='poll_export')
    @is_admin_or_whitelisted()
    async def poll_export(self, ctx, message_id_or_link: str):
        """
        Экспорт опроса в XLSX с форматированием.
        
        Формат: 
        !poll_export <message_id>
        !poll_export <ссылка>
        """
        await ctx.message.delete()
        
        # Парсим ID
        msg_id = None
        if 'discord.com/channels/' in message_id_or_link or 'discordapp.com/channels/' in message_id_or_link:
            try:
                parts = message_id_or_link.rstrip('/').split('/')
                msg_id = int(parts[-1])
            except (ValueError, IndexError):
                await ctx.send("❌ Неверный формат ссылки", delete_after=10)
                return
        else:
            try:
                msg_id = int(message_id_or_link)
            except ValueError:
                await ctx.send("❌ Неверный формат ID или ссылки", delete_after=10)
                return
        
        poll_data = self.db.get_poll(msg_id)
        
        if not poll_data:
            await ctx.send(f"❌ Опрос не найден", delete_after=10)
            return
        
        try:
            # Получаем опрос
            poll = None
            poll_question = poll_data['question']
            poll_answers = []
            
            try:
                channel = self.bot.get_channel(poll_data['channel_id'])
                if channel:
                    message = await channel.fetch_message(msg_id)
                    poll = message.poll
                    if poll:
                        poll_question = poll.question
                        poll_answers = poll.answers
            except:
                pass
            
            # Если опрос недоступен - берем из БД
            if not poll_answers:
                poll_options = self.db.get_poll_options(msg_id)
                if poll_options:
                    class FakeAnswer:
                        def __init__(self, answer_id, text):
                            self.id = answer_id
                            self.text = text
                    poll_answers = [FakeAnswer(aid, text) for aid, text in poll_options]
            
            votes = self.db.get_poll_votes(msg_id)
            
            votes_by_answer = {}
            for user_id, answer_id, voted_at in votes:
                if answer_id not in votes_by_answer:
                    votes_by_answer[answer_id] = []
                votes_by_answer[answer_id].append(user_id)
            
            # Используем openpyxl для создания Excel с форматированием
            try:
                from openpyxl import Workbook
                from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
                
                wb = Workbook()
                ws = wb.active
                ws.title = "Poll Results"
                
                # Заголовок
                ws['A1'] = 'Discord Poll Export'
                ws['A1'].font = Font(bold=True, size=14)
                
                ws['A2'] = 'Message ID:'
                ws['B2'] = msg_id
                ws['A3'] = 'Question:'
                ws['B3'] = poll_question
                ws['A4'] = 'Status:'
                ws['B4'] = 'Finalized' if poll and poll.is_finalized() else 'Active'
                
                total_votes = len(votes)
                ws['A6'] = 'Total Votes:'
                ws['B6'] = total_votes
                
                # Статистика
                ws['A8'] = 'Option'
                ws['B8'] = 'Votes'
                ws['C8'] = 'Percentage'
                ws['A8'].font = Font(bold=True)
                ws['B8'].font = Font(bold=True)
                ws['C8'].font = Font(bold=True)
                
                row = 9
                for answer in poll_answers:
                    count = len(votes_by_answer.get(answer.id, []))
                    percentage = (count / total_votes * 100) if total_votes > 0 else 0
                    ws[f'A{row}'] = answer.text
                    ws[f'B{row}'] = count
                    ws[f'C{row}'] = f"{percentage:.1f}%"
                    row += 1
                
                # ПУСТАЯ СТРОКА для визуального разделения
                row += 1
                
                # Заголовки вариантов (со смещением вправо - начинаем с колонки B)
                start_col = 1  # Колонка B (0=A, 1=B)
                header_row = row
                
                # Цвет для заголовков (желтый как на скрине)
                yellow_fill = PatternFill(start_color='FFD966', end_color='FFD966', fill_type='solid')
                thin_border = Border(
                    left=Side(style='thin'),
                    right=Side(style='thin'),
                    top=Side(style='thin'),
                    bottom=Side(style='thin')
                )
                
                for i, answer in enumerate(poll_answers):
                    col_letter = chr(ord('A') + start_col + i)
                    cell = ws[f'{col_letter}{header_row}']
                    
                    cell.value = answer.text
                    cell.fill = yellow_fill
                    cell.font = Font(bold=True, size=11)
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    cell.border = thin_border
                    
                    # Ширина колонки
                    ws.column_dimensions[col_letter].width = 30
                
                # Заполняем данные (голоса пользователей)
                max_votes = max([len(votes_by_answer.get(answer.id, [])) for answer in poll_answers], default=0)
                
                for row_index in range(max_votes):
                    data_row = header_row + 1 + row_index
                    
                    for i, answer in enumerate(poll_answers):
                        voters = votes_by_answer.get(answer.id, [])
                        col_letter = chr(ord('A') + start_col + i)
                        
                        if row_index < len(voters):
                            user_id = voters[row_index]
                            member = ctx.guild.get_member(user_id)
                            
                            cell = ws[f'{col_letter}{data_row}']
                            
                            if member:
                                # Создаем ссылку на профиль Discord
                                username = member.display_name
                                profile_link = f"https://discord.com/users/{user_id}"
                                
                                cell.value = username
                                cell.hyperlink = profile_link
                                cell.font = Font(color='0563C1', underline='single')  # Синий цвет ссылки
                            else:
                                cell.value = f"ID:{user_id}"
                            
                            cell.alignment = Alignment(vertical='center')
                            cell.border = thin_border
                
                # Сохраняем в BytesIO
                excel_file = io.BytesIO()
                wb.save(excel_file)
                excel_file.seek(0)
                
                file = discord.File(
                    excel_file,
                    filename=f'poll_{msg_id}.xlsx'
                )
                
                await ctx.send(f"📊 Экспорт ({total_votes} голосов)", file=file)
                
            except ImportError:
                await ctx.send("❌ Требуется установить openpyxl: `pip install openpyxl --break-system-packages`", delete_after=10)
            
        except Exception as e:
            await ctx.send(f"❌ Ошибка: {e}", delete_after=10)
            import traceback
            traceback.print_exc()
    
    @commands.command(name='poll_export_detail')
    @is_admin_or_whitelisted()
    async def poll_export_detail(self, ctx, message_id_or_link: str, days: int = 7):
        """
        Экспорт с статистикой активности в XLSX.
        
        Формат: 
        !poll_export_detail <message_id> [7/14/30]
        !poll_export_detail <ссылка> [7/14/30]
        """
        await ctx.message.delete()
        
        if days not in [7, 14, 30]:
            await ctx.send("❌ Период: 7, 14 или 30 дней", delete_after=10)
            return
        
        # Парсим ID
        msg_id = None
        if 'discord.com/channels/' in message_id_or_link or 'discordapp.com/channels/' in message_id_or_link:
            try:
                parts = message_id_or_link.rstrip('/').split('/')
                msg_id = int(parts[-1])
            except (ValueError, IndexError):
                await ctx.send("❌ Неверный формат ссылки", delete_after=10)
                return
        else:
            try:
                msg_id = int(message_id_or_link)
            except ValueError:
                await ctx.send("❌ Неверный формат ID или ссылки", delete_after=10)
                return
        
        poll_data = self.db.get_poll(msg_id)
        
        if not poll_data:
            await ctx.send(f"❌ Опрос не найден", delete_after=10)
            return
        
        try:
            # Получаем опрос
            poll = None
            poll_question = poll_data['question']
            poll_answers = []
            
            try:
                channel = self.bot.get_channel(poll_data['channel_id'])
                if channel:
                    message = await channel.fetch_message(msg_id)
                    poll = message.poll
                    if poll:
                        poll_question = poll.question
                        poll_answers = poll.answers
            except:
                pass
            
            # Если опрос недоступен - берем из БД
            if not poll_answers:
                poll_options = self.db.get_poll_options(msg_id)
                if poll_options:
                    class FakeAnswer:
                        def __init__(self, answer_id, text):
                            self.id = answer_id
                            self.text = text
                    poll_answers = [FakeAnswer(aid, text) for aid, text in poll_options]
            
            votes = self.db.get_poll_votes(msg_id)
            
            votes_by_answer = {}
            for user_id, answer_id, voted_at in votes:
                if answer_id not in votes_by_answer:
                    votes_by_answer[answer_id] = []
                votes_by_answer[answer_id].append(user_id)
            
            # Получаем статистику
            all_voters = set(user_id for user_id, _, _ in votes)
            user_stats = {}
            
            for user_id in all_voters:
                stats = self.db.get_user_stats(ctx.guild.id, user_id, days)
                if stats:
                    user_stats[user_id] = {
                        'messages': stats['period_messages'],
                        'voice_time': stats['period_voice_time']
                    }
                else:
                    user_stats[user_id] = {'messages': 0, 'voice_time': 0}
            
            # Сортируем по войсу
            sorted_votes_by_answer = {}
            for answer_id, voters in votes_by_answer.items():
                sorted_voters = sorted(
                    voters,
                    key=lambda uid: user_stats.get(uid, {}).get('voice_time', 0),
                    reverse=True
                )
                sorted_votes_by_answer[answer_id] = sorted_voters
            
            # Создаем Excel с форматированием
            try:
                from openpyxl import Workbook
                from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
                
                wb = Workbook()
                ws = wb.active
                ws.title = "Poll Results Detailed"
                
                # Заголовок
                ws['A1'] = 'Discord Poll Export (Detailed)'
                ws['A1'].font = Font(bold=True, size=14)
                
                ws['A2'] = 'Message ID:'
                ws['B2'] = msg_id
                ws['A3'] = 'Question:'
                ws['B3'] = poll_question
                ws['A4'] = 'Period:'
                ws['B4'] = f'{days} days'
                
                total_votes = len(votes)
                ws['A6'] = 'Total Votes:'
                ws['B6'] = total_votes
                
                # Статистика
                ws['A8'] = 'Option'
                ws['B8'] = 'Votes'
                ws['C8'] = 'Percentage'
                ws['A8'].font = Font(bold=True)
                ws['B8'].font = Font(bold=True)
                ws['C8'].font = Font(bold=True)
                
                row = 9
                for answer in poll_answers:
                    count = len(votes_by_answer.get(answer.id, []))
                    percentage = (count / total_votes * 100) if total_votes > 0 else 0
                    ws[f'A{row}'] = answer.text
                    ws[f'B{row}'] = count
                    ws[f'C{row}'] = f"{percentage:.1f}%"
                    row += 1
                
                # ПУСТАЯ СТРОКА
                row += 1
                
                # Заголовки вариантов (смещение вправо)
                start_col = 1  # Колонка B
                header_row = row
                
                yellow_fill = PatternFill(start_color='FFD966', end_color='FFD966', fill_type='solid')
                thin_border = Border(
                    left=Side(style='thin'),
                    right=Side(style='thin'),
                    top=Side(style='thin'),
                    bottom=Side(style='thin')
                )
                
                for i, answer in enumerate(poll_answers):
                    col_letter = chr(ord('A') + start_col + i)
                    cell = ws[f'{col_letter}{header_row}']
                    
                    cell.value = answer.text
                    cell.fill = yellow_fill
                    cell.font = Font(bold=True, size=11)
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    cell.border = thin_border
                    
                    ws.column_dimensions[col_letter].width = 35
                
                # Заполняем данные с статистикой
                max_votes = max([len(sorted_votes_by_answer.get(answer.id, [])) for answer in poll_answers], default=0)
                
                for row_index in range(max_votes):
                    data_row = header_row + 1 + row_index
                    
                    for i, answer in enumerate(poll_answers):
                        voters = sorted_votes_by_answer.get(answer.id, [])
                        col_letter = chr(ord('A') + start_col + i)
                        
                        if row_index < len(voters):
                            user_id = voters[row_index]
                            member = ctx.guild.get_member(user_id)
                            
                            cell = ws[f'{col_letter}{data_row}']
                            
                            if member:
                                username = member.display_name
                                profile_link = f"https://discord.com/users/{user_id}"
                                
                                stats = user_stats.get(user_id, {'messages': 0, 'voice_time': 0})
                                messages = stats['messages']
                                voice_hours = int(stats['voice_time'] // 3600)
                                voice_minutes = int((stats['voice_time'] % 3600) // 60)
                                
                                cell_value = f"{username} | {messages} msg | {voice_hours}h {voice_minutes}m"
                                
                                cell.value = cell_value
                                cell.hyperlink = profile_link
                                cell.font = Font(color='0563C1', underline='single')
                            else:
                                stats = user_stats.get(user_id, {'messages': 0, 'voice_time': 0})
                                messages = stats['messages']
                                voice_hours = int(stats['voice_time'] // 3600)
                                voice_minutes = int((stats['voice_time'] % 3600) // 60)
                                
                                cell.value = f"ID:{user_id} | {messages} msg | {voice_hours}h {voice_minutes}m"
                            
                            cell.alignment = Alignment(vertical='center')
                            cell.border = thin_border
                
                # Сохраняем
                excel_file = io.BytesIO()
                wb.save(excel_file)
                excel_file.seek(0)
                
                file = discord.File(
                    excel_file,
                    filename=f'poll_{msg_id}_detailed_{days}d.xlsx'
                )
                
                await ctx.send(f"📊 Детальный экспорт ({days}д, {total_votes} голосов)", file=file)
                
            except ImportError:
                await ctx.send("❌ Требуется установить openpyxl: `pip install openpyxl --break-system-packages`", delete_after=10)
            
        except Exception as e:
            await ctx.send(f"❌ Ошибка: {e}", delete_after=10)
            import traceback
            traceback.print_exc()
    
    @commands.command(name='poll_list')
    @is_admin_or_whitelisted()
    async def poll_list(self, ctx):
        """Список всех отслеженных опросов на сервере"""
        await ctx.message.delete()
        
        polls = self.db.get_all_polls(ctx.guild.id)
        
        if not polls:
            await ctx.send("📋 Нет отслеженных опросов", delete_after=10)
            return
        
        embed = discord.Embed(
            title=f"📋 Отслеженные опросы",
            description=f"Всего: **{len(polls)}**",
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )
        
        poll_list = []
        for poll in polls[:10]:
            question = poll['question']
            if len(question) > 50:
                question = question[:47] + "..."
            
            poll_list.append(f"**`{poll['message_id']}`** — {question}")
        
        if len(polls) > 10:
            poll_list.append(f"*...и еще {len(polls) - 10}*")
        
        embed.add_field(
            name="Опросы",
            value="\n".join(poll_list),
            inline=False
        )
        
        embed.set_footer(text="💡 !poll_results <ID> для просмотра")
        
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(NativePollSystem(bot))