from discord.ext import commands
from flask import Flask, jsonify, request
import threading
import requests

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
        
        @self.flask_app.route('/api/guild/<int:guild_id>/stats/<int:days>')
        def get_guild_stats(guild_id, days):
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503
            
            if days not in [7, 14, 30]:
                return jsonify({'error': 'Invalid days parameter. Use 7, 14, or 30'}), 400
            
            try:
                stats = self.bot.db.get_all_users_stats(guild_id, days)
                return jsonify(stats)
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

        def verify_discord_admin(access_token: str, guild_id: int) -> bool:
            """Проверить является ли пользователь администратором сервера через Discord API"""
            try:
                headers = {'Authorization': f'Bearer {access_token}'}
                response = requests.get(
                    'https://discord.com/api/users/@me/guilds',
                    headers=headers,
                    timeout=10
                )

                if response.status_code != 200:
                    return False

                guilds = response.json()
                for guild in guilds:
                    if int(guild['id']) == guild_id:
                        permissions = int(guild.get('permissions', 0))
                        # Бит 0x8 = Administrator permission
                        return (permissions & 0x8) == 0x8

                return False
            except Exception as e:
                print(f"Error verifying Discord admin: {e}")
                return False

        @self.flask_app.route('/api/admin/guilds')
        def get_admin_guilds():
            """Получить серверы где пользователь является администратором"""
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503

            access_token = request.headers.get('Authorization', '').replace('Bearer ', '')
            if not access_token:
                return jsonify({'error': 'Authorization header required'}), 401

            try:
                # Получаем серверы пользователя из Discord API
                headers = {'Authorization': f'Bearer {access_token}'}
                response = requests.get(
                    'https://discord.com/api/users/@me/guilds',
                    headers=headers,
                    timeout=10
                )

                if response.status_code != 200:
                    return jsonify({'error': 'Failed to fetch user guilds from Discord'}), 401

                user_guilds = response.json()

                # Фильтруем: только серверы где юзер админ И бот присутствует
                bot_guild_ids = {g.id for g in self.bot.guilds}
                admin_guilds = []

                for guild in user_guilds:
                    guild_id = int(guild['id'])
                    permissions = int(guild.get('permissions', 0))
                    is_admin = (permissions & 0x8) == 0x8

                    if is_admin and guild_id in bot_guild_ids:
                        bot_guild = self.bot.get_guild(guild_id)
                        admin_guilds.append({
                            'id': guild_id,
                            'name': guild['name'],
                            'icon': f"https://cdn.discordapp.com/icons/{guild_id}/{guild['icon']}.png" if guild.get('icon') else None,
                            'member_count': bot_guild.member_count if bot_guild else 0
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

            # Проверяем что пользователь админ этого сервера
            if not verify_discord_admin(access_token, guild_id):
                return jsonify({'error': 'You must be an administrator of this server'}), 403

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

            # Проверяем что пользователь админ этого сервера
            if not verify_discord_admin(access_token, guild_id):
                return jsonify({'error': 'You must be an administrator of this server'}), 403

            try:
                success = self.bot.db.reset_guild_settings(guild_id)

                if success:
                    return jsonify({'success': True, 'message': 'Settings reset to defaults'})
                else:
                    return jsonify({'error': 'Failed to reset settings'}), 500
            except Exception as e:
                return jsonify({'error': str(e)}), 500

    def run_flask(self):
        """Запуск Flask сервера"""
        self.flask_app.run(host='127.0.0.1', port=5555, debug=False, use_reloader=False)


async def setup(bot):
    await bot.add_cog(APIServer(bot))
    print("✅ Загружен: APIServer (Flask API на порту 5555)")