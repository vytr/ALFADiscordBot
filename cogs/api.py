from discord.ext import commands
from flask import Flask, jsonify
import threading

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
                    'bot': m.bot
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
        
        @self.flask_app.route('/api/guild/<int:guild_id>/inactive/<int:days>')
        def get_inactive_users(guild_id, days):
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503
            
            if days not in [7, 14, 30]:
                return jsonify({'error': 'Invalid days parameter'}), 400
            
            try:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    return jsonify({'error': 'Guild not found'}), 404
                
                # Все пользователи сервера (не боты)
                all_members = [m.id for m in guild.members if not m.bot]
                
                # Получаем активных
                all_stats = self.bot.db.get_all_users_stats(guild_id, days)
                active_user_ids = {
                    stat['user_id'] for stat in all_stats 
                    if stat['period_messages'] > 0 or stat['period_voice_time'] > 0
                }
                
                # Неактивные = все - активные
                inactive_ids = [uid for uid in all_members if uid not in active_user_ids]
                
                return jsonify({
                    'total_members': len(all_members),
                    'active_members': len(active_user_ids),
                    'inactive_members': len(inactive_ids),
                    'inactive_user_ids': inactive_ids
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
                
                # Топ нарушителей
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
            
        @self.flask_app.route('/api/guild/<int:guild_id>/roles')
        def get_guild_roles(guild_id):
            if not self.bot.is_ready():
                return jsonify({'error': 'Bot not ready'}), 503
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return jsonify({'error': 'Guild not found'}), 404
            
            # Получаем все роли кроме @everyone
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
            
            # Сортируем по позиции (важные роли выше)
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
                    'roles': [r.id for r in m.roles if r.name != "@everyone"]  # ← ДОБАВИЛИ РОЛИ
                }
                for m in guild.members
            ]
            return jsonify(members)
    
    def run_flask(self):
        """Запуск Flask сервера"""
        self.flask_app.run(host='0.0.0.0', port=5555, debug=False, use_reloader=False)


async def setup(bot):
    await bot.add_cog(APIServer(bot))
    print("✅ Загружен: APIServer (Flask API на порту 5555)")