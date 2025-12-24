import discord
from discord.ext import commands
from datetime import datetime
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

class CreatePollModal(discord.ui.Modal, title="📊 Создать опрос"):
    """Модальное окно для создания опроса"""
    
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        
        self.question = discord.ui.TextInput(
            label="Вопрос опроса",
            placeholder="Например: Какой язык программирования лучший?",
            required=True,
            max_length=200
        )
        self.add_item(self.question)
        
        self.option1 = discord.ui.TextInput(
            label="Вариант 1",
            placeholder="Первый вариант ответа",
            required=True,
            max_length=100
        )
        self.add_item(self.option1)
        
        self.option2 = discord.ui.TextInput(
            label="Вариант 2",
            placeholder="Второй вариант ответа",
            required=True,
            max_length=100
        )
        self.add_item(self.option2)
        
        self.option3 = discord.ui.TextInput(
            label="Вариант 3 (необязательно)",
            placeholder="Третий вариант ответа",
            required=False,
            max_length=100
        )
        self.add_item(self.option3)
        
        self.option4 = discord.ui.TextInput(
            label="Вариант 4 (необязательно)",
            placeholder="Четвертый вариант ответа",
            required=False,
            max_length=100
        )
        self.add_item(self.option4)

    async def on_submit(self, interaction: discord.Interaction):
        # Собираем варианты ответов
        options = [self.option1.value, self.option2.value]
        if self.option3.value.strip():
            options.append(self.option3.value)
        if self.option4.value.strip():
            options.append(self.option4.value)
        
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        # Формируем описание
        description = ""
        for i, option in enumerate(options):
            description += f"{emojis[i]} {option}\n"
        
        # Создаем embed для опроса
        embed = discord.Embed(
            title="📊 Опрос", 
            description=f"**{self.question.value}**\n\n{description}",
            color=0x3498DB
        )
        
        # Отправляем опрос в канал
        channel = interaction.channel
        msg = await channel.send(embed=embed)
        
        # Добавляем реакции
        for i in range(len(options)):
            await msg.add_reaction(emojis[i])
        
        # Сохраняем в БД
        poll_id = self.bot.db.create_poll(
            guild_id=interaction.guild.id,
            channel_id=channel.id,
            message_id=msg.id,
            question=self.question.value,
            options=options,
            emojis=emojis[:len(options)],
            created_by=interaction.user.id
        )
        
        # Обновляем сообщение с ID
        if poll_id:
            embed.set_footer(text=f"ID опроса: {poll_id} | Создал: {interaction.user.name}")
            await msg.edit(embed=embed)
            
            # Уведомляем пользователя
            success_embed = discord.Embed(
                title="✅ Опрос создан!",
                description=f"**ID опроса:** `{poll_id}`\n**Вопрос:** {self.question.value}",
                color=0x2ECC71
            )
            success_embed.add_field(name="Канал", value=channel.mention, inline=True)
            success_embed.add_field(name="Вариантов", value=len(options), inline=True)
            await interaction.response.send_message(embed=success_embed, ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Ошибка при создании опроса", ephemeral=True)


class PollIDModal(discord.ui.Modal, title="🔍 Введите ID опроса"):
    """Модальное окно для ввода ID опроса"""
    
    def __init__(self, bot, action_type):
        super().__init__()
        self.bot = bot
        self.action_type = action_type  # "results", "close", "export", "chart"
        
        self.poll_id = discord.ui.TextInput(
            label="ID опроса",
            placeholder="Например: 12345",
            required=True,
            max_length=20
        )
        self.add_item(self.poll_id)

    async def on_submit(self, interaction: discord.Interaction):
        poll_id = self.poll_id.value.strip()
        
        if self.action_type == "results":
            await self.show_results(interaction, poll_id)
        elif self.action_type == "close":
            await self.close_poll(interaction, poll_id)
        elif self.action_type == "export":
            await self.export_poll(interaction, poll_id)
        elif self.action_type == "chart":
            await self.show_chart(interaction, poll_id)
    
    async def show_results(self, interaction: discord.Interaction, poll_id: str):
        """Показать результаты опроса"""
        results = self.bot.db.get_poll_results(poll_id)
        
        if not results:
            await interaction.response.send_message(f"❌ Опрос с ID `{poll_id}` не найден", ephemeral=True)
            return
        
        # Формируем embed с результатами
        status = "🔒 Закрыт" if results['is_closed'] else "🔓 Активен"
        embed = discord.Embed(
            title=f"📊 Результаты опроса {status}",
            description=f"**{results['question']}**",
            color=0xE74C3C if results['is_closed'] else 0x3498DB,
            timestamp=datetime.utcnow()
        )
        
        # Группируем голоса по вариантам
        votes_by_option = {}
        total_votes = 0
        for user_id, option_index, voted_at in results['votes']:
            if option_index not in votes_by_option:
                votes_by_option[option_index] = []
            votes_by_option[option_index].append(user_id)
            total_votes += 1
        
        # Выводим каждый вариант
        for option_index, option_text, emoji in results['options']:
            voters = votes_by_option.get(option_index, [])
            vote_count = len(voters)
            
            # Процент голосов
            percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
            
            # Визуальная полоса
            bar_length = int(percentage / 10)
            bar = "█" * bar_length + "░" * (10 - bar_length)
            
            # Формируем список пользователей (максимум 5)
            if voters:
                user_mentions = []
                for user_id in voters[:5]:
                    member = interaction.guild.get_member(user_id)
                    if member:
                        user_mentions.append(member.mention)
                    else:
                        user_mentions.append(f"<@{user_id}>")
                
                voters_text = ", ".join(user_mentions)
                if len(voters) > 5:
                    voters_text += f" и еще {len(voters) - 5}"
            else:
                voters_text = "Никто не проголосовал"
            
            embed.add_field(
                name=f"{emoji} {option_text}",
                value=f"**{vote_count}** голосов ({percentage:.1f}%)\n`{bar}`\n{voters_text}",
                inline=False
            )
        
        embed.set_footer(text=f"ID опроса: {poll_id} | Всего голосов: {total_votes}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def close_poll(self, interaction: discord.Interaction, poll_id: str):
        """Закрыть опрос"""
        # Проверяем, существует ли опрос
        results = self.bot.db.get_poll_results(poll_id)
        if not results:
            await interaction.response.send_message(f"❌ Опрос с ID `{poll_id}` не найден", ephemeral=True)
            return
        
        # Проверяем, не закрыт ли уже
        if results['is_closed']:
            await interaction.response.send_message(f"⚠️ Опрос `{poll_id}` уже закрыт", ephemeral=True)
            return
        
        # Закрываем опрос
        if self.bot.db.close_poll(poll_id):
            embed = discord.Embed(
                title="🔒 Опрос закрыт",
                description=f"**{results['question']}**\n\nОпрос успешно закрыт. Новые голоса не принимаются.",
                color=0xE74C3C,
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text=f"ID опроса: {poll_id}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Ошибка при закрытии опроса", ephemeral=True)
    
    async def export_poll(self, interaction: discord.Interaction, poll_id: str):
        """Экспортировать опрос в CSV"""
        await interaction.response.defer(ephemeral=True)
        
        # Получаем данные опроса
        csv_data = self.bot.db.export_poll_to_csv(poll_id, interaction.guild)
        
        if not csv_data:
            await interaction.followup.send(f"❌ Опрос с ID `{poll_id}` не найден", ephemeral=True)
            return
        
        # Создаем файл
        file = discord.File(
            io.BytesIO(csv_data.encode('utf-8-sig')),
            filename=f'poll_{poll_id}.csv'
        )
        
        embed = discord.Embed(
            title="📊 Экспорт опроса",
            description=f"Опрос `{poll_id}` экспортирован в CSV",
            color=0x2ECC71
        )
        
        await interaction.followup.send(embed=embed, file=file, ephemeral=True)
    
    async def show_chart(self, interaction: discord.Interaction, poll_id: str):
        """Показать график результатов"""
        await interaction.response.defer(ephemeral=True)
        
        results = self.bot.db.get_poll_results(poll_id)
        
        if not results:
            await interaction.followup.send(f"❌ Опрос с ID `{poll_id}` не найден", ephemeral=True)
            return
        
        # Подсчитываем голоса
        votes_by_option = {}
        for user_id, option_index, voted_at in results['votes']:
            votes_by_option[option_index] = votes_by_option.get(option_index, 0) + 1
        
        # Если нет голосов
        if not votes_by_option:
            await interaction.followup.send("📊 В этом опросе еще нет голосов", ephemeral=True)
            return
        
        # Подготавливаем данные для графика
        options = []
        vote_counts = []
        colors = ['#3498DB', '#E74C3C', '#2ECC71', '#F1C40F', '#9B59B6', '#E67E22', '#1ABC9C', '#34495E', '#E91E63', '#FF5722']
        
        for option_index, option_text, emoji in results['options']:
            count = votes_by_option.get(option_index, 0)
            # Обрезаем длинные названия
            if len(option_text) > 20:
                option_text = option_text[:17] + "..."
            options.append(f"{emoji} {option_text}")
            vote_counts.append(count)
        
        # Создаем график
        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor('#2C2F33')
        ax.set_facecolor('#23272A')
        
        # Столбчатая диаграмма
        bars = ax.barh(options, vote_counts, color=colors[:len(options)])
        
        # Настройка внешнего вида
        ax.set_xlabel('Голоса', color='white', fontsize=12, fontweight='bold')
        ax.set_title(f'Результаты опроса\n{results["question"]}', color='white', fontsize=14, fontweight='bold', pad=20)
        ax.tick_params(colors='white')
        
        # Добавляем значения на столбцы
        for i, (bar, count) in enumerate(zip(bars, vote_counts)):
            width = bar.get_width()
            total = sum(vote_counts)
            percentage = (count / total * 100) if total > 0 else 0
            ax.text(width, bar.get_y() + bar.get_height()/2,
                   f' {count} ({percentage:.1f}%)',
                   ha='left', va='center', color='white', fontsize=10, fontweight='bold')
        
        # Убираем рамки
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        
        plt.tight_layout()
        
        # Сохраняем в BytesIO
        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor='#2C2F33', dpi=150)
        buf.seek(0)
        plt.close()
        
        # Отправляем
        file = discord.File(buf, filename='poll_results.png')
        
        status = "🔒 Закрыт" if results['is_closed'] else "🔓 Активен"
        embed = discord.Embed(
            title=f"📊 График результатов {status}",
            description=f"Всего голосов: **{sum(vote_counts)}**",
            color=0xE74C3C if results['is_closed'] else 0x3498DB,
            timestamp=datetime.utcnow()
        )
        embed.set_image(url="attachment://poll_results.png")
        embed.set_footer(text=f"ID опроса: {poll_id}")
        
        await interaction.followup.send(embed=embed, file=file, ephemeral=True)


class PollListSelect(discord.ui.Select):
    """Select menu для выбора периода списка опросов"""
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label="За 7 дней", emoji="📅", value="7"),
            discord.SelectOption(label="За 14 дней", emoji="📆", value="14"),
            discord.SelectOption(label="За 30 дней", emoji="🗓️", value="30"),
            discord.SelectOption(label="За 90 дней", emoji="📊", value="90"),
        ]
        super().__init__(
            placeholder="Выберите период...",
            options=options,
            custom_id="poll_list_select"
        )
    
    async def callback(self, interaction: discord.Interaction):
        days = int(self.values[0])
        
        polls = self.bot.db.get_polls_by_date(interaction.guild.id, days)
        
        if not polls:
            await interaction.response.send_message(f"📋 Опросов за последние {days} дней не найдено", ephemeral=True)
            return
        
        # Разделяем на открытые и закрытые
        open_polls = [p for p in polls if not p[4]]
        closed_polls = [p for p in polls if p[4]]
        
        embed = discord.Embed(
            title=f"📋 Опросы за последние {days} дней",
            description=f"Всего опросов: **{len(polls)}** (🔓 Открытых: {len(open_polls)} | 🔒 Закрытых: {len(closed_polls)})",
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )
        
        # Открытые опросы
        if open_polls:
            open_text = ""
            for poll_id, question, created_by, created_at, is_closed in open_polls[:5]:
                creator = interaction.guild.get_member(created_by)
                creator_name = creator.name if creator else f"ID:{created_by}"
                # Обрезаем длинный вопрос
                short_question = question if len(question) <= 50 else question[:47] + "..."
                open_text += f"🔓 **{poll_id}** - {short_question}\n└ Создал: {creator_name}\n\n"
            
            if len(open_polls) > 5:
                open_text += f"_...и еще {len(open_polls) - 5} открытых опросов_"
            
            embed.add_field(name="🔓 Открытые опросы", value=open_text, inline=False)
        
        # Закрытые опросы
        if closed_polls:
            closed_text = ""
            for poll_id, question, created_by, created_at, is_closed in closed_polls[:5]:
                creator = interaction.guild.get_member(created_by)
                creator_name = creator.name if creator else f"ID:{created_by}"
                short_question = question if len(question) <= 50 else question[:47] + "..."
                closed_text += f"🔒 **{poll_id}** - {short_question}\n└ Создал: {creator_name}\n\n"
            
            if len(closed_polls) > 5:
                closed_text += f"_...и еще {len(closed_polls) - 5} закрытых опросов_"
            
            embed.add_field(name="🔒 Закрытые опросы", value=closed_text, inline=False)
        
        embed.set_footer(text="💡 Используйте ID опроса для просмотра результатов")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class PollsMenuView(discord.ui.View):
    """Расширенное меню управления опросами"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    @discord.ui.button(label="➕ Создать опрос", style=discord.ButtonStyle.green, custom_id="create_poll", row=0)
    async def create_poll(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = CreatePollModal(self.bot)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📊 Результаты", style=discord.ButtonStyle.blurple, custom_id="poll_results", row=0)
    async def poll_results(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PollIDModal(self.bot, "results")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📈 График", style=discord.ButtonStyle.blurple, custom_id="poll_chart", row=0)
    async def poll_chart(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PollIDModal(self.bot, "chart")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📋 Список опросов", style=discord.ButtonStyle.gray, custom_id="poll_list", row=1)
    async def poll_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View(timeout=180)
        view.add_item(PollListSelect(self.bot))
        
        embed = discord.Embed(
            title="📋 Список опросов",
            description="Выберите период для просмотра опросов:",
            color=0x95A5A6
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="🔒 Закрыть опрос", style=discord.ButtonStyle.red, custom_id="close_poll", row=1)
    async def close_poll(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PollIDModal(self.bot, "close")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📤 Экспорт", style=discord.ButtonStyle.gray, custom_id="export_poll", row=1)
    async def export_poll(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PollIDModal(self.bot, "export")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="⚡ Активные опросы", style=discord.ButtonStyle.green, custom_id="active_polls", row=2)
    async def active_polls(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Получаем все опросы и фильтруем открытые
        all_polls = self.bot.db.get_all_polls(interaction.guild.id)
        open_polls = [p for p in all_polls if not p[4]]  # p[4] - is_closed
        
        if not open_polls:
            await interaction.response.send_message("📋 На данный момент нет активных опросов", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="⚡ Активные опросы сервера",
            description=f"Всего активных опросов: **{len(open_polls)}**",
            color=0x2ECC71,
            timestamp=datetime.utcnow()
        )
        
        for poll_id, question, created_by, created_at, is_closed in open_polls[:10]:
            creator = interaction.guild.get_member(created_by)
            creator_name = creator.name if creator else f"ID:{created_by}"
            
            # Получаем количество голосов
            results = self.bot.db.get_poll_results(poll_id)
            vote_count = len(results['votes']) if results else 0
            
            embed.add_field(
                name=f"🔓 {poll_id}",
                value=f"**{question}**\nСоздал: {creator_name} | Голосов: {vote_count}",
                inline=False
            )
        
        if len(open_polls) > 10:
            embed.set_footer(text=f"Показано 10 из {len(open_polls)} активных опросов")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="🗑️ Закрыть все", style=discord.ButtonStyle.red, custom_id="close_all_polls", row=2)
    async def close_all_polls(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Проверка прав администратора
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⛔ Только администраторы могут закрыть все опросы", ephemeral=True)
            return
        
        # Подтверждение
        confirm_view = discord.ui.View(timeout=60)
        
        async def confirm_callback(inter: discord.Interaction):
            closed_count = self.bot.db.close_all_open_polls(inter.guild.id)
            
            if closed_count == 0:
                await inter.response.send_message("⚠️ Нет открытых опросов для закрытия", ephemeral=True)
            else:
                embed = discord.Embed(
                    title="🔒 Опросы закрыты",
                    description=f"Успешно закрыто опросов: **{closed_count}**\n\nВсе открытые опросы больше не принимают голоса.",
                    color=0xE74C3C,
                    timestamp=datetime.utcnow()
                )
                await inter.response.send_message(embed=embed, ephemeral=True)
        
        async def cancel_callback(inter: discord.Interaction):
            await inter.response.send_message("❌ Отменено", ephemeral=True)
        
        confirm_btn = discord.ui.Button(label="✅ Подтвердить", style=discord.ButtonStyle.red)
        confirm_btn.callback = confirm_callback
        
        cancel_btn = discord.ui.Button(label="❌ Отмена", style=discord.ButtonStyle.gray)
        cancel_btn.callback = cancel_callback
        
        confirm_view.add_item(confirm_btn)
        confirm_view.add_item(cancel_btn)
        
        embed = discord.Embed(
            title="⚠️ Подтверждение",
            description="Вы уверены, что хотите закрыть **все** открытые опросы на сервере?",
            color=0xE67E22
        )
        
        await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
    
    @discord.ui.button(label="🔙 Назад", style=discord.ButtonStyle.red, custom_id="back_to_main_from_polls", row=2)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Импортируем PanelView из cogs.panel
        try:
            # Попытка импорта из cogs
            import sys
            import importlib
            
            if 'cogs.panel' in sys.modules:
                panel_module = sys.modules['cogs.panel']
                importlib.reload(panel_module)
                PanelView = panel_module.PanelView
            else:
                from cogs.panel import PanelView
        except ImportError:
            try:
                # Запасной вариант - прямой импорт
                from panel import PanelView
            except ImportError:
                await interaction.response.send_message(
                    "❌ Ошибка: не удалось загрузить главную панель",
                    ephemeral=True
                )
                return
        
        embed = discord.Embed(
            title="🎛️ ALFA Bot Control Panel",
            description="Добро пожаловать в панель управления!\nВыберите нужный раздел, нажав на кнопку ниже.",
            color=0x2ECC71,
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        embed.set_footer(text="ALFA Bot • Панель управления", icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None)

        await interaction.response.edit_message(embed=embed, view=PanelView(self.bot))


class PollsExtension(commands.Cog):
    """Расширение панели для управления опросами"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @discord.app_commands.command(name="polls_menu", description="📊 Интерактивное меню управления опросами")
    async def polls_menu(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📊 Управление опросами",
            description="Интерактивная панель для создания и управления опросами",
            color=0x3498DB,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="➕ Создать опрос",
            value="Создайте новый опрос через удобную форму",
            inline=True
        )
        embed.add_field(
            name="📊 Результаты",
            value="Просмотрите результаты любого опроса",
            inline=True
        )
        embed.add_field(
            name="📈 График",
            value="Визуализация результатов опроса",
            inline=True
        )
        embed.add_field(
            name="📋 Список опросов",
            value="Все опросы за выбранный период",
            inline=True
        )
        embed.add_field(
            name="🔒 Закрыть опрос",
            value="Завершите голосование",
            inline=True
        )
        embed.add_field(
            name="📤 Экспорт",
            value="Экспортируйте результаты в CSV",
            inline=True
        )
        
        embed.set_footer(text="Выберите действие с помощью кнопок ниже")
        
        await interaction.response.send_message(
            embed=embed,
            view=PollsMenuView(self.bot),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(PollsExtension(bot))