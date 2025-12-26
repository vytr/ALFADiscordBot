import discord
from discord.ext import commands
from datetime import datetime

class RoleManager(commands.Cog):
    """Управление ролями сервера"""
    
    def __init__(self, bot):
        self.bot = bot
    
    def is_admin_or_whitelisted(self, ctx):
        """Проверка прав: администратор или в whitelist"""
        if ctx.author.guild_permissions.administrator:
            return True
        return self.bot.db.is_whitelisted(ctx.guild.id, ctx.author.id)
    
    @commands.command(name='a_create_role')
    async def create_role(self, ctx, *, args):
        """
        Создать новую роль с правами
        
        Использование:
        !a_create_role название | permission1 | permission2 | ...
        
        Пример:
        !a_create_role VIP | send_messages | attach_files | connect | speak
        
        Доступные права:
        - administrator: Полные права администратора
        - manage_guild: Управление сервером
        - manage_roles: Управление ролями
        - manage_channels: Управление каналами
        - kick_members: Выгонять участников
        - ban_members: Банить участников
        - view_channel: Просматривать каналы
        - send_messages: Отправлять сообщения
        - embed_links: Встраивать ссылки
        - attach_files: Прикреплять файлы
        - add_reactions: Добавлять реакции
        - use_external_emojis: Использовать внешние эмодзи
        - mention_everyone: Упоминать @everyone
        - manage_messages: Управлять сообщениями
        - read_message_history: Читать историю сообщений
        - use_application_commands: Использовать команды приложений
        - connect: Подключаться к голосовым
        - speak: Говорить в голосовых
        - mute_members: Заглушать участников
        - deafen_members: Отключать звук участникам
        - move_members: Перемещать участников
        - use_voice_activation: Голосовая активность
        - manage_nicknames: Управлять никнеймами
        - change_nickname: Изменять свой никнейм
        """
        
        # Проверка прав
        if not self.is_admin_or_whitelisted(ctx):
            await ctx.send("❌ У вас нет прав для использования этой команды!")
            return
        
        # Проверка прав бота
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("❌ У бота нет прав **Управление ролями**!")
            return
        
        # Парсим аргументы
        try:
            parts = [p.strip() for p in args.split('|')]
            if len(parts) < 1:
                await ctx.send("❌ Укажите название роли!\n**Использование:** `!a_create_role название | permission1 | permission2`")
                return
            
            role_name = parts[0]
            permissions_list = parts[1:] if len(parts) > 1 else []
            
        except Exception as e:
            await ctx.send(f"❌ Ошибка парсинга команды: {e}\n**Использование:** `!a_create_role название | permission1 | permission2`")
            return
        
        # Проверяем что роль с таким именем не существует
        existing_role = discord.utils.get(ctx.guild.roles, name=role_name)
        if existing_role:
            await ctx.send(f"❌ Роль с именем **{role_name}** уже существует!")
            return
        
        # Создаем словарь прав
        permissions_dict = {}
        
        # Если права не указаны, создаем роль без специальных прав (базовые)
        if not permissions_list:
            permissions_dict = {
                'view_channel': True,
                'read_message_history': True,
            }
        else:
            # Парсим права из списка
            for perm in permissions_list:
                perm = perm.strip().lower()
                
                # Проверяем что право существует
                if hasattr(discord.Permissions, perm):
                    permissions_dict[perm] = True
                else:
                    await ctx.send(f"⚠️ Неизвестное право: `{perm}` (пропущено)")
        
        try:
            # Создаем объект прав
            permissions = discord.Permissions(**permissions_dict)
            
            # Создаем роль
            new_role = await ctx.guild.create_role(
                name=role_name,
                permissions=permissions,
                reason=f"Создано {ctx.author.name} через команду бота"
            )
            
            # Формируем embed с результатом
            embed = discord.Embed(
                title="✅ Роль создана",
                description=f"Роль {new_role.mention} успешно создана!",
                color=new_role.color if new_role.color.value != 0 else discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="📋 Информация",
                value=(
                    f"**Название:** {new_role.name}\n"
                    f"**ID:** `{new_role.id}`\n"
                    f"**Позиция:** {new_role.position}\n"
                    f"**Упоминаемая:** {'Да' if new_role.mentionable else 'Нет'}"
                ),
                inline=False
            )
            
            # Показываем установленные права
            if permissions_dict:
                perms_text = []
                for perm_name, perm_value in permissions_dict.items():
                    if perm_value:
                        # Форматируем имя права
                        readable_name = perm_name.replace('_', ' ').title()
                        perms_text.append(f"✅ {readable_name}")
                
                if perms_text:
                    # Разбиваем на части если много прав
                    if len(perms_text) <= 10:
                        embed.add_field(
                            name="🔐 Права роли",
                            value="\n".join(perms_text),
                            inline=False
                        )
                    else:
                        # Первые 10
                        embed.add_field(
                            name=f"🔐 Права роли (показаны первые 10 из {len(perms_text)})",
                            value="\n".join(perms_text[:10]),
                            inline=False
                        )
            else:
                embed.add_field(
                    name="🔐 Права роли",
                    value="Базовые права (просмотр каналов)",
                    inline=False
                )
            
            embed.set_footer(text=f"Создал: {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
            
            await ctx.send(embed=embed)
            
        except discord.Forbidden:
            await ctx.send("❌ У бота недостаточно прав для создания роли!")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Ошибка при создании роли: {e}")
        except Exception as e:
            await ctx.send(f"❌ Неожиданная ошибка: {e}")
    
    @commands.command(name='a_give_role')
    async def give_role(self, ctx, member: discord.Member, *, role_name: str):
        """
        Выдать роль пользователю
        
        Использование:
        !a_give_role @пользователь название_роли
        
        Примеры:
        !a_give_role @User VIP
        !a_give_role @User Moderator
        """
        
        # Проверка прав
        if not self.is_admin_or_whitelisted(ctx):
            await ctx.send("❌ У вас нет прав для использования этой команды!")
            return
        
        # Проверка прав бота
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("❌ У бота нет прав **Управление ролями**!")
            return
        
        # Ищем роль
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        
        if not role:
            # Попробуем найти роль по упоминанию
            if role_name.startswith('<@&') and role_name.endswith('>'):
                role_id = int(role_name[3:-1])
                role = ctx.guild.get_role(role_id)
            
            if not role:
                await ctx.send(f"❌ Роль **{role_name}** не найдена на сервере!")
                return
        
        # Проверяем что роль не выше роли бота
        if role.position >= ctx.guild.me.top_role.position:
            await ctx.send(f"❌ Роль {role.mention} выше роли бота! Я не могу её выдать.")
            return
        
        # Проверяем что роль не выше роли пользователя который выдает
        if role.position >= ctx.author.top_role.position and not ctx.author.guild_permissions.administrator:
            await ctx.send(f"❌ Роль {role.mention} выше вашей роли!")
            return
        
        # Проверяем что у пользователя уже нет этой роли
        if role in member.roles:
            await ctx.send(f"⚠️ У {member.mention} уже есть роль {role.mention}!")
            return
        
        try:
            # Выдаем роль
            await member.add_roles(role, reason=f"Выдано {ctx.author.name} через команду бота")
            
            # Формируем embed
            embed = discord.Embed(
                title="✅ Роль выдана",
                description=f"Роль {role.mention} выдана пользователю {member.mention}",
                color=role.color if role.color.value != 0 else discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="👤 Пользователь",
                value=f"{member.mention}\n`{member.name}` (ID: {member.id})",
                inline=True
            )
            
            embed.add_field(
                name="🎭 Роль",
                value=f"{role.mention}\n`{role.name}` (ID: {role.id})",
                inline=True
            )
            
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Выдал: {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
            
            await ctx.send(embed=embed)
            
        except discord.Forbidden:
            await ctx.send("❌ У бота недостаточно прав для выдачи этой роли!")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Ошибка при выдаче роли: {e}")
    
    @commands.command(name='a_remove_role')
    async def remove_role(self, ctx, member: discord.Member, *, role_name: str):
        """
        Забрать роль у пользователя
        
        Использование:
        !a_remove_role @пользователь название_роли
        
        Примеры:
        !a_remove_role @User VIP
        !a_remove_role @User Moderator
        """
        
        # Проверка прав
        if not self.is_admin_or_whitelisted(ctx):
            await ctx.send("❌ У вас нет прав для использования этой команды!")
            return
        
        # Проверка прав бота
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("❌ У бота нет прав **Управление ролями**!")
            return
        
        # Ищем роль
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        
        if not role:
            # Попробуем найти роль по упоминанию
            if role_name.startswith('<@&') and role_name.endswith('>'):
                role_id = int(role_name[3:-1])
                role = ctx.guild.get_role(role_id)
            
            if not role:
                await ctx.send(f"❌ Роль **{role_name}** не найдена на сервере!")
                return
        
        # Проверяем что роль не выше роли бота
        if role.position >= ctx.guild.me.top_role.position:
            await ctx.send(f"❌ Роль {role.mention} выше роли бота! Я не могу её забрать.")
            return
        
        # Проверяем что роль не выше роли пользователя который забирает
        if role.position >= ctx.author.top_role.position and not ctx.author.guild_permissions.administrator:
            await ctx.send(f"❌ Роль {role.mention} выше вашей роли!")
            return
        
        # Проверяем что у пользователя есть эта роль
        if role not in member.roles:
            await ctx.send(f"⚠️ У {member.mention} нет роли {role.mention}!")
            return
        
        try:
            # Забираем роль
            await member.remove_roles(role, reason=f"Забрано {ctx.author.name} через команду бота")
            
            # Формируем embed
            embed = discord.Embed(
                title="✅ Роль забрана",
                description=f"Роль {role.mention} забрана у пользователя {member.mention}",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="👤 Пользователь",
                value=f"{member.mention}\n`{member.name}` (ID: {member.id})",
                inline=True
            )
            
            embed.add_field(
                name="🎭 Роль",
                value=f"{role.mention}\n`{role.name}` (ID: {role.id})",
                inline=True
            )
            
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Забрал: {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
            
            await ctx.send(embed=embed)
            
        except discord.Forbidden:
            await ctx.send("❌ У бота недостаточно прав для снятия этой роли!")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Ошибка при снятии роли: {e}")

    @commands.command(name='a_edit_role_permissions')
    async def edit_role_permissions(self, ctx, role: discord.Role, *, args):
        """
        Добавить или убрать права у существующей роли        
        Использование:
        !a_edit_role_permissions @роль add | permission1 | permission2 | ...
        !a_edit_role_permissions @роль remove | permission1 | permission2 | ...
            
        Примеры:
        !a_edit_role_permissions @VIP add | manage_messages | kick_members
        !a_edit_role_permissions @Модератор remove | ban_members | administrator
        """
            
        # Проверка прав
        if not self.is_admin_or_whitelisted(ctx):
            await ctx.send("❌ У вас нет прав для использования этой команды!")
            return
            
        # Проверка прав бота
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("❌ У бота нет прав **Управление ролями**!")
            return
            
        # Проверяем что роль не выше роли бота
        if role.position >= ctx.guild.me.top_role.position:
            await ctx.send(f"❌ Роль {role.mention} выше роли бота! Я не могу её редактировать.")
            return
            
        # Проверяем что роль не выше роли пользователя
        if role.position >= ctx.author.top_role.position and not ctx.author.guild_permissions.administrator:
            await ctx.send(f"❌ Роль {role.mention} выше вашей роли!")
            return
            
        # Парсим аргументы
        try:
            parts = [p.strip() for p in args.split('|')]
            if len(parts) < 2:
                await ctx.send(
                    "❌ Неверный формат команды!\n"
                    "**Использование:**\n"
                    "`!a_edit_role_permissions @роль add | permission1 | permission2`\n"                   
                    "`!a_edit_role_permissions @роль remove | permission1 | permission2`"
                )
                return
                
            action = parts[0].lower()
            permissions_list = parts[1:]
                
            if action not in ['add', 'remove']:
                await ctx.send("❌ Действие должно быть `add` (добавить) или `remove` (убрать)!")
                return
                
        except Exception as e:
            await ctx.send(f"❌ Ошибка парсинга команды: {e}")
            return
            
        # Получаем текущие права роли
        current_permissions = role.permissions
            
        # Создаем словарь для изменения прав
        permissions_dict = {}
        invalid_perms = []
            
        for perm in permissions_list:
            perm = perm.strip().lower()
                
            # Проверяем что право существует
            if hasattr(discord.Permissions, perm):
                if action == 'add':
                    permissions_dict[perm] = True
                else:  # remove
                    permissions_dict[perm] = False
            else:
                invalid_perms.append(perm)
            
        if invalid_perms:
            await ctx.send(f"⚠️ Неизвестные права (пропущены): {', '.join([f'`{p}`' for p in invalid_perms])}")
            
        if not permissions_dict:
            await ctx.send("❌ Не указано ни одного валидного права!")
            return
            
        try:
            # Применяем изменения к текущим правам
            new_permissions = current_permissions
            for perm_name, perm_value in permissions_dict.items():
                setattr(new_permissions, perm_name, perm_value)
                
            # Обновляем роль
            await role.edit(
                permissions=new_permissions,
                reason=f"Изменено {ctx.author.name} через команду бота"
            )
                
            # Формируем embed с результатом
            action_text = "добавлены к" if action == 'add' else "убраны из"
            action_emoji = "➕" if action == 'add' else "➖"
                
            embed = discord.Embed(
                title=f"{action_emoji} Права роли изменены",
                description=f"Права {action_text} роли {role.mention}",
                color=role.color if role.color.value != 0 else discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
                
            embed.add_field(
                name="🎭 Роль",
                value=f"{role.mention}\n`{role.name}` (ID: {role.id})",
                inline=False
            )
                
            # Показываем измененные права
            perms_text = []
            for perm_name, perm_value in permissions_dict.items():
                readable_name = perm_name.replace('_', ' ').title()
                if action == 'add':
                    perms_text.append(f"➕ {readable_name}")
                else:
                    perms_text.append(f"➖ {readable_name}")
                
            embed.add_field(
                name=f"📝 Изменения ({len(perms_text)})",
                value="\n".join(perms_text) if len(perms_text) <= 15 else "\n".join(perms_text[:15]) + f"\n... и еще {len(perms_text) - 15}",
                inline=False
            )
                
            embed.set_footer(
                text=f"Изменил: {ctx.author.name}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else None
            )
                
            await ctx.send(embed=embed)
                
        except discord.Forbidden:
            await ctx.send("❌ У бота недостаточно прав для редактирования этой роли!")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Ошибка при редактировании роли: {e}")
        except Exception as e:
            await ctx.send(f"❌ Неожиданная ошибка: {e}")

async def setup(bot):
    await bot.add_cog(RoleManager(bot))
    print("✅ Загружен: RoleManager (управление ролями)")
