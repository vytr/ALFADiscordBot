from discord.ext import commands
from flask import Flask, jsonify, request, send_from_directory
import threading
import requests
import os
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
 
# Загружаем .env из корня проекта
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
# Папка для загрузки логотипов
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads', 'logos')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

class APIServer(commands.Cog):
    """Flask API для dashboard"""
    
    def __init__(self, bot):
        self.bot = bot
        self.flask_app = Flask(__name__)
        self.setup_routes()
        
        # Запускаем Flask в отдельном потоке
        self.flask_thread = threading.Thread(target=self.run_flask, daemon=True)
        self.flask_thread.start()
    
    def setup_routes(self):
        """Настройка всех API эндпоинтов"""
        
        @self.flask_app.route('/stats')
        def stats():
            from datetime import datetime
            try:
                uptime = str(datetime.now() - self.bot.start_time).split('.')[0] if hasattr(self.bot, 'start_time') else "Unknown"
                
                stats_data = {
                    'status': 'online' if self.bot.is_ready() else 'starting',
                    'uptime': uptime,
                    'servers': len(self.bot.guilds) if self.bot.is_ready() else 0,
                    'users': sum(guild.member_count for guild in self.bot.guilds) if self.bot.is_ready() else 0,
                    'latency': round(self.bot.latency * 1000, 2) if self.bot.is_ready() else 0,
                    'commands': getattr(self.bot, 'command_count', 0)
                }
                
                return jsonify(stats_data)
            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @self.flask_app.route('/api/guilds')
        def get_guilds():
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503
            
            guilds = [
                {
                    'id': g.id,
                    'name': g.name,
                    'icon': str(g.icon.url) if g.icon else None,
                    'member_count': g.member_count
                }
                for g in self.bot.guilds
            ]
            return jsonify(guilds)
        
        @self.flask_app.route('/api/guild/<int:guild_id>/roles')
        def get_guild_roles(guild_id):
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return jsonify({'error': 'Guild not found'}), 404
            
            roles = [
                {
                    'id': r.id,
                    'name': r.name,
                    'color': str(r.color),
                    'position': r.position
                }
                for r in guild.roles
                if r.name != "@everyone"
            ]
            
            roles.sort(key=lambda x: x['position'], reverse=True)
            
            return jsonify(roles)
        
        @self.flask_app.route('/api/guild/<int:guild_id>/members')
        def get_guild_members(guild_id):
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return jsonify({'error': 'Guild not found'}), 404
            
            members = [
                {
                    'id': m.id,
                    'name': m.name,
                    'display_name': m.display_name,
                    'avatar': str(m.avatar.url) if m.avatar else None,
                    'bot': m.bot,
                    'roles': [r.id for r in m.roles if r.name != "@everyone"]
                }
                for m in guild.members
            ]
            
            return jsonify(members)
        
        @self.flask_app.route('/api/guild/<int:guild_id>/users-stats')
        def get_guild_users_stats(guild_id):
            """Get full user stats with filters for admin panel"""
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503

            guild = self.bot.get_guild(guild_id)
            if not guild:
                return jsonify({'error': 'Guild not found'}), 404

            try:
                from datetime import datetime

                # Get filter parameters
                include_roles = request.args.getlist('include_roles', type=int)
                exclude_roles = request.args.getlist('exclude_roles', type=int)
                since_date = request.args.get('since_date')  # Format: YYYY-MM-DD
                sort_by = request.args.get('sort_by', 'voice')  # 'voice' or 'messages'

                # Parse since_date if provided
                filter_date = None
                if since_date:
                    try:
                        filter_date = datetime.strptime(since_date, '%Y-%m-%d').date()
                    except ValueError:
                        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

                # Get all non-bot members with their roles
                members_data = {}
                for member in guild.members:
                    if member.bot:
                        continue

                    member_role_ids = [r.id for r in member.roles if r.name != "@everyone"]

                    # Apply role filters
                    if include_roles:
                        if not any(role_id in member_role_ids for role_id in include_roles):
                            continue

                    if exclude_roles:
                        if any(role_id in member_role_ids for role_id in exclude_roles):
                            continue

                    members_data[member.id] = {
                        'user_id': member.id,
                        'username': member.name,
                        'display_name': member.display_name,
                        'avatar': str(member.avatar.url) if member.avatar else None,
                        'roles': member_role_ids,
                        'total_messages': 0,
                        'total_voice_time': 0,
                        'period_messages': 0,
                        'period_voice_time': 0
                    }

                # Get stats from database
                import sqlite3
                conn = sqlite3.connect(self.bot.db.db_path)
                cursor = conn.cursor()

                # Get total stats
                cursor.execute('''
                    SELECT user_id, total_messages, total_voice_time
                    FROM user_stats_total
                    WHERE guild_id = ?
                ''', (guild_id,))

                for row in cursor.fetchall():
                    user_id, total_messages, total_voice_time = row
                    if user_id in members_data:
                        members_data[user_id]['total_messages'] = total_messages or 0
                        members_data[user_id]['total_voice_time'] = total_voice_time or 0

                # Get period stats based on filter_date
                if filter_date:
                    # Messages since date
                    cursor.execute('''
                        SELECT user_id, SUM(message_count) as period_messages
                        FROM user_messages_daily
                        WHERE guild_id = ? AND message_date >= ?
                        GROUP BY user_id
                    ''', (guild_id, filter_date.isoformat()))

                    for row in cursor.fetchall():
                        user_id, period_messages = row
                        if user_id in members_data:
                            members_data[user_id]['period_messages'] = period_messages or 0

                    # Voice time since date
                    cursor.execute('''
                        SELECT user_id, SUM(voice_time) as period_voice_time
                        FROM user_voice_daily
                        WHERE guild_id = ? AND voice_date >= ?
                        GROUP BY user_id
                    ''', (guild_id, filter_date.isoformat()))

                    for row in cursor.fetchall():
                        user_id, period_voice_time = row
                        if user_id in members_data:
                            members_data[user_id]['period_voice_time'] = period_voice_time or 0
                else:
                    # No date filter - period stats = total stats
                    for user_id in members_data:
                        members_data[user_id]['period_messages'] = members_data[user_id]['total_messages']
                        members_data[user_id]['period_voice_time'] = members_data[user_id]['total_voice_time']

                conn.close()

                # Convert to list and sort
                result = list(members_data.values())
                if sort_by == 'messages':
                    result.sort(key=lambda x: (x['period_messages'], x['period_voice_time']), reverse=True)
                else:  # default: voice
                    result.sort(key=lambda x: (x['period_voice_time'], x['period_messages']), reverse=True)

                return jsonify({
                    'users': result,
                    'total_count': len(result),
                    'filters': {
                        'include_roles': include_roles,
                        'exclude_roles': exclude_roles,
                        'since_date': since_date,
                        'sort_by': sort_by
                    }
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        @self.flask_app.route('/api/guild/<int:guild_id>/inactive/<int:days>/<activity_type>')
        def get_inactive_users(guild_id, days, activity_type):
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503
            
            if days not in [7, 14, 30]:
                return jsonify({'error': 'Invalid days parameter'}), 400
            
            if activity_type not in ['messages', 'voice', 'both']:
                return jsonify({'error': 'Invalid activity_type. Use: messages, voice, or both'}), 400
            
            try:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    return jsonify({'error': 'Guild not found'}), 404
                
                # Все пользователи сервера (не боты)
                all_members = [m.id for m in guild.members if not m.bot]
                
                # Получаем статистику
                all_stats = self.bot.db.get_all_users_stats(guild_id, days)
                
                # Определяем активных по типу активности
                active_user_ids = set()
                
                for stat in all_stats:
                    if activity_type == 'messages':
                        # Активен если есть сообщения
                        if stat['period_messages'] > 0:
                            active_user_ids.add(stat['user_id'])
                    
                    elif activity_type == 'voice':
                        # Активен если есть время в войсе
                        if stat['period_voice_time'] > 0:
                            active_user_ids.add(stat['user_id'])
                    
                    elif activity_type == 'both':
                        # Активен если есть И сообщения И войс
                        if stat['period_messages'] > 0 and stat['period_voice_time'] > 0:
                            active_user_ids.add(stat['user_id'])
                
                # Неактивные = все - активные
                inactive_ids = [uid for uid in all_members if uid not in active_user_ids]
                
                return jsonify({
                    'total_members': len(all_members),
                    'active_members': len(active_user_ids),
                    'inactive_members': len(inactive_ids),
                    'inactive_user_ids': inactive_ids,
                    'activity_type': activity_type
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        @self.flask_app.route('/api/guild/<int:guild_id>/warnings')
        def get_warnings(guild_id):
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503
            
            try:
                import sqlite3
                
                conn = sqlite3.connect(self.bot.db.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total_warnings,
                        SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active_warnings,
                        COUNT(DISTINCT user_id) as unique_users
                    FROM warnings
                    WHERE guild_id = ?
                ''', (guild_id,))
                
                stats = cursor.fetchone()
                
                cursor.execute('''
                    SELECT user_id, COUNT(*) as warning_count
                    FROM warnings
                    WHERE guild_id = ? AND is_active = 1
                    GROUP BY user_id
                    ORDER BY warning_count DESC
                    LIMIT 10
                ''', (guild_id,))
                
                top_offenders = [
                    {'user_id': row[0], 'warning_count': row[1]}
                    for row in cursor.fetchall()
                ]
                
                conn.close()
                
                return jsonify({
                    'total_warnings': stats[0],
                    'active_warnings': stats[1],
                    'unique_users': stats[2],
                    'top_offenders': top_offenders
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        # ==================== НОВЫЕ ЭНДПОИНТЫ ДЛЯ АВТОРИЗАЦИИ ====================
        
        @self.flask_app.route('/api/whitelist/check/<int:guild_id>/<int:user_id>')
        def check_whitelist(guild_id, user_id):
            """Проверка whitelist для пользователя"""
            try:
                from database import Database
                db = Database()
                is_whitelisted = db.is_whitelisted(guild_id, user_id)
                
                return jsonify({
                    'guild_id': guild_id,
                    'user_id': user_id,
                    'is_whitelisted': is_whitelisted
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        @self.flask_app.route('/api/user/guilds/<int:user_id>')
        def get_user_guilds(user_id):
            """Получить серверы где пользователь в whitelist"""
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503
            
            try:
                from database import Database
                db = Database()
                
                whitelisted_guilds = []
                
                for guild in self.bot.guilds:
                    if db.is_whitelisted(guild.id, user_id):
                        whitelisted_guilds.append({
                            'id': guild.id,
                            'name': guild.name,
                            'icon': str(guild.icon.url) if guild.icon else None,
                            'member_count': guild.member_count
                        })
                
                return jsonify({
                    'user_id': user_id,
                    'guilds': whitelisted_guilds
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        # ==================== ADMIN PANEL ENDPOINTS ====================

        def get_user_id_from_token(access_token: str) -> int | None:
            """Получить user_id из Discord access token"""
            try:
                headers = {'Authorization': f'Bearer {access_token}'}
                response = requests.get(
                    'https://discord.com/api/users/@me',
                    headers=headers,
                    timeout=10
                )
                if response.status_code == 200:
                    return int(response.json()['id'])
                return None
            except:
                return None

        @self.flask_app.route('/api/admin/guilds')
        def get_admin_guilds():
            """Получить серверы где пользователь в whitelist"""
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503

            access_token = request.headers.get('Authorization', '').replace('Bearer ', '')
            if not access_token:
                return jsonify({'error': 'Authorization header required'}), 401

            try:
                # Получаем user_id из Discord API
                headers = {'Authorization': f'Bearer {access_token}'}
                response = requests.get(
                    'https://discord.com/api/users/@me',
                    headers=headers,
                    timeout=10
                )

                if response.status_code != 200:
                    return jsonify({'error': 'Failed to fetch user from Discord'}), 401

                user_data = response.json()
                user_id = int(user_data['id'])

                # Получаем серверы бота и проверяем whitelist
                admin_guilds = []

                for bot_guild in self.bot.guilds:
                    if self.bot.db.is_whitelisted(bot_guild.id, user_id):
                        admin_guilds.append({
                            'id': bot_guild.id,
                            'name': bot_guild.name,
                            'icon': str(bot_guild.icon.url) if bot_guild.icon else None,
                            'member_count': bot_guild.member_count
                        })

                return jsonify({'guilds': admin_guilds})
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.flask_app.route('/api/admin/guild/<int:guild_id>/settings', methods=['GET'])
        def get_guild_settings(guild_id):
            """Получить настройки сервера"""
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503

            try:
                settings = self.bot.db.get_guild_settings(guild_id)
                return jsonify(settings)
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.flask_app.route('/api/admin/guild/<int:guild_id>/settings', methods=['PUT'])
        def update_guild_settings(guild_id):
            """Обновить настройки сервера (требует токен администратора)"""
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503

            access_token = request.headers.get('Authorization', '').replace('Bearer ', '')
            if not access_token:
                return jsonify({'error': 'Authorization header required'}), 401

            # Получаем user_id и проверяем whitelist
            user_id = get_user_id_from_token(access_token)
            if not user_id or not self.bot.db.is_whitelisted(guild_id, user_id):
                return jsonify({'error': 'Access denied'}), 403

            try:
                data = request.get_json()
                if not data:
                    return jsonify({'error': 'No data provided'}), 400

                # Разрешённые поля для обновления
                allowed_fields = [
                    'bot_name', 'primary_color', 'secondary_color',
                    'panel_title', 'welcome_message', 'logo_url', 'footer_text'
                ]

                # Фильтруем только разрешённые поля
                filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

                if not filtered_data:
                    return jsonify({'error': 'No valid fields provided'}), 400

                success = self.bot.db.update_guild_settings(guild_id, **filtered_data)

                if success:
                    return jsonify({'success': True, 'message': 'Settings updated'})
                else:
                    return jsonify({'error': 'Failed to update settings'}), 500
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.flask_app.route('/api/admin/guild/<int:guild_id>/settings', methods=['DELETE'])
        def reset_guild_settings(guild_id):
            """Сбросить настройки сервера к дефолтным"""
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503

            access_token = request.headers.get('Authorization', '').replace('Bearer ', '')
            if not access_token:
                return jsonify({'error': 'Authorization header required'}), 401

            # Получаем user_id и проверяем whitelist
            user_id = get_user_id_from_token(access_token)
            if not user_id or not self.bot.db.is_whitelisted(guild_id, user_id):
                return jsonify({'error': 'Access denied'}), 403

            try:
                success = self.bot.db.reset_guild_settings(guild_id)

                if success:
                    return jsonify({'success': True, 'message': 'Settings reset to defaults'})
                else:
                    return jsonify({'error': 'Failed to reset settings'}), 500
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        # ==================== LOGO UPLOAD ====================

        def allowed_file(filename):
            return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

        @self.flask_app.route('/api/admin/guild/<int:guild_id>/logo', methods=['POST'])
        def upload_logo(guild_id):
            """Загрузить логотип для сервера"""
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503

            access_token = request.headers.get('Authorization', '').replace('Bearer ', '')
            if not access_token:
                return jsonify({'error': 'Authorization header required'}), 401

            # Проверяем whitelist
            user_id = get_user_id_from_token(access_token)
            if not user_id or not self.bot.db.is_whitelisted(guild_id, user_id):
                return jsonify({'error': 'Access denied'}), 403

            if 'file' not in request.files:
                return jsonify({'error': 'No file provided'}), 400

            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400

            if not allowed_file(file.filename):
                return jsonify({'error': 'Invalid file type. Allowed: png, jpg, jpeg, gif, webp'}), 400

            # Проверяем размер файла
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)

            if file_size > MAX_FILE_SIZE:
                return jsonify({'error': 'File too large. Maximum size: 10 MB'}), 400

            try:
                # Создаём папку если не существует
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)

                # Удаляем старый логотип если есть
                for old_file in os.listdir(UPLOAD_FOLDER):
                    if old_file.startswith(f"{guild_id}."):
                        os.remove(os.path.join(UPLOAD_FOLDER, old_file))

                # Сохраняем новый файл
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = f"{guild_id}.{ext}"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)

                # Формируем URL для логотипа
                logo_url = f"/uploads/logos/{filename}"

                # Обновляем настройки в БД
                self.bot.db.update_guild_settings(guild_id, logo_url=logo_url)

                return jsonify({
                    'success': True,
                    'logo_url': logo_url,
                    'message': 'Logo uploaded successfully'
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.flask_app.route('/api/admin/guild/<int:guild_id>/logo', methods=['DELETE'])
        def delete_logo(guild_id):
            """Удалить логотип сервера"""
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503

            access_token = request.headers.get('Authorization', '').replace('Bearer ', '')
            if not access_token:
                return jsonify({'error': 'Authorization header required'}), 401

            # Проверяем whitelist
            user_id = get_user_id_from_token(access_token)
            if not user_id or not self.bot.db.is_whitelisted(guild_id, user_id):
                return jsonify({'error': 'Access denied'}), 403

            try:
                # Удаляем файл
                for old_file in os.listdir(UPLOAD_FOLDER):
                    if old_file.startswith(f"{guild_id}."):
                        os.remove(os.path.join(UPLOAD_FOLDER, old_file))

                # Очищаем URL в БД
                self.bot.db.update_guild_settings(guild_id, logo_url=None)

                return jsonify({'success': True, 'message': 'Logo deleted'})
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.flask_app.route('/uploads/logos/<filename>')
        def serve_logo(filename):
            """Отдаём файл логотипа"""
            return send_from_directory(UPLOAD_FOLDER, filename)

        @self.flask_app.route('/api/admin/guild/<int:guild_id>/bot-avatar', methods=['POST'])
        def apply_bot_avatar(guild_id):
            """Применить загруженный логотип как серверную аватарку бота"""
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503

            access_token = request.headers.get('Authorization', '').replace('Bearer ', '')
            if not access_token:
                return jsonify({'error': 'Authorization header required'}), 401

            # Проверяем whitelist
            user_id = get_user_id_from_token(access_token)
            if not user_id or not self.bot.db.is_whitelisted(guild_id, user_id):
                return jsonify({'error': 'Access denied'}), 403

            # Проверяем что гильдия существует
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return jsonify({'error': 'Guild not found'}), 404

            # Получаем текущий логотип из настроек
            settings = self.bot.db.get_guild_settings(guild_id)
            logo_url = settings.get('logo_url')

            if not logo_url:
                return jsonify({'error': 'No logo uploaded. Please upload a logo first.'}), 400

            try:
                import base64
                import asyncio

                # Определяем путь к файлу логотипа
                if logo_url.startswith('/uploads/logos/'):
                    filename = logo_url.split('/')[-1]
                    filepath = os.path.join(UPLOAD_FOLDER, filename)

                    if not os.path.exists(filepath):
                        return jsonify({'error': 'Logo file not found'}), 404

                    # Читаем файл и конвертируем в base64
                    with open(filepath, 'rb') as f:
                        image_data = f.read()
                else:
                    # Внешний URL - скачиваем изображение
                    try:
                        response = requests.get(logo_url, timeout=10)
                        if response.status_code != 200:
                            return jsonify({'error': 'Failed to fetch logo from URL'}), 400
                        image_data = response.content
                    except Exception as e:
                        return jsonify({'error': f'Failed to fetch logo: {str(e)}'}), 400

                # Ресайзим изображение для Discord (макс 256x256, рекомендуется PNG)
                from PIL import Image
                import io as io_module

                # Открываем изображение
                img = Image.open(io_module.BytesIO(image_data))

                # Конвертируем в RGB если нужно (для RGBA/P режимов)
                if img.mode in ('RGBA', 'P'):
                    # Сохраняем альфа-канал для PNG
                    img = img.convert('RGBA')
                else:
                    img = img.convert('RGB')

                # Ресайзим до 256x256 (Discord рекомендует квадратные аватарки)
                max_size = 256
                if img.width > max_size or img.height > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

                # Сохраняем в PNG формат
                output_buffer = io_module.BytesIO()
                if img.mode == 'RGBA':
                    img.save(output_buffer, format='PNG', optimize=True)
                    mime_type = 'image/png'
                else:
                    img.save(output_buffer, format='PNG', optimize=True)
                    mime_type = 'image/png'

                image_data = output_buffer.getvalue()

                # Формируем data URI для Discord API
                base64_image = base64.b64encode(image_data).decode('utf-8')
                avatar_data = f"data:{mime_type};base64,{base64_image}"

                # Используем Discord API для установки серверной аватарки бота
                # PATCH /guilds/{guild.id}/members/@me
                bot_token = os.getenv('DISCORD_TOKEN')
                if not bot_token:
                    return jsonify({'error': 'Bot token not configured'}), 500

                headers = {
                    'Authorization': f'Bot {bot_token}',
                    'Content-Type': 'application/json'
                }

                api_response = requests.patch(
                    f'https://discord.com/api/v10/guilds/{guild_id}/members/@me',
                    headers=headers,
                    json={'avatar': avatar_data},
                    timeout=30
                )

                if api_response.status_code == 200:
                    return jsonify({
                        'success': True,
                        'message': 'Bot avatar updated successfully for this server'
                    })
                elif api_response.status_code == 400:
                    error_data = api_response.json()
                    # Показываем полную информацию об ошибке
                    error_msg = error_data.get('message', 'Bad request')
                    errors_detail = error_data.get('errors', {})
                    return jsonify({'error': f"Discord API error: {error_msg}", 'details': errors_detail}), 400
                elif api_response.status_code == 403:
                    return jsonify({'error': 'Bot does not have permission to change avatar on this server'}), 403
                elif api_response.status_code == 429:
                    return jsonify({'error': 'Rate limited. Please try again later.'}), 429
                else:
                    return jsonify({'error': f'Discord API returned status {api_response.status_code}'}), 500

            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.flask_app.route('/api/admin/guild/<int:guild_id>/bot-avatar', methods=['DELETE'])
        def reset_bot_avatar(guild_id):
            """Сбросить серверную аватарку бота (использовать глобальную)"""
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503

            access_token = request.headers.get('Authorization', '').replace('Bearer ', '')
            if not access_token:
                return jsonify({'error': 'Authorization header required'}), 401

            # Проверяем whitelist
            user_id = get_user_id_from_token(access_token)
            if not user_id or not self.bot.db.is_whitelisted(guild_id, user_id):
                return jsonify({'error': 'Access denied'}), 403

            # Проверяем что гильдия существует
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return jsonify({'error': 'Guild not found'}), 404

            try:
                bot_token = os.getenv('DISCORD_TOKEN')
                if not bot_token:
                    return jsonify({'error': 'Bot token not configured'}), 500

                headers = {
                    'Authorization': f'Bot {bot_token}',
                    'Content-Type': 'application/json'
                }

                # Отправляем null чтобы сбросить к глобальной аватарке
                api_response = requests.patch(
                    f'https://discord.com/api/v10/guilds/{guild_id}/members/@me',
                    headers=headers,
                    json={'avatar': None},
                    timeout=30
                )

                if api_response.status_code == 200:
                    return jsonify({
                        'success': True,
                        'message': 'Bot avatar reset to default for this server'
                    })
                else:
                    return jsonify({'error': f'Discord API returned status {api_response.status_code}'}), 500

            except Exception as e:
                return jsonify({'error': str(e)}), 500

    def run_flask(self):
        """Запуск Flask сервера"""
        self.flask_app.run(host='0.0.0.0', port=5555, debug=False, use_reloader=False)


async def setup(bot):
    await bot.add_cog(APIServer(bot))
    print("✅ Загружен: APIServer (Flask API на порту 5555)")
