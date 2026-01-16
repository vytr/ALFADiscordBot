import sqlite3
import os
import uuid
import csv
from io import StringIO
from datetime import datetime, timedelta

class Database:
    """Класс для работы с базой данных whitelist и опросов"""

    def __init__(self, db_path='bot_database.db'):
        self.db_path = db_path
        self.init_db()
        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: закрываем зависшие сессии при старте
        self._cleanup_on_init()

    def _cleanup_on_init(self):
        """Очистка при инициализации БД"""
        print("🔧 Initializing database cleanup...")
        
        # Закрываем все зависшие сессии
        hanging = self.close_hanging_voice_sessions(max_duration_hours=24)
        if hanging > 0:
            print(f"✅ Closed {hanging} hanging voice sessions")
        
        # Принудительно закрываем ВСЕ активные сессии (безопасный перезапуск)
        active = self.force_end_all_voice_sessions()
        if active > 0:
            print(f"✅ Force closed {active} active voice sessions")
        
        print("✅ Database cleanup complete")

    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Таблица whitelist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS whitelist (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                added_by INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')

        # Таблица опросов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS polls (
                poll_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_closed INTEGER DEFAULT 0
            )
        ''')

        # Таблица вариантов ответов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS poll_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id TEXT NOT NULL,
                option_index INTEGER NOT NULL,
                option_text TEXT NOT NULL,
                emoji TEXT NOT NULL,
                FOREIGN KEY (poll_id) REFERENCES polls(poll_id),
                UNIQUE(poll_id, option_index)
            )
        ''')

        # Таблица голосов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS poll_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                option_index INTEGER NOT NULL,
                voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (poll_id) REFERENCES polls(poll_id),
                UNIQUE(poll_id, user_id, option_index)
            )
        ''')

        # Таблица общей статистики пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_stats_total (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                total_messages INTEGER DEFAULT 0,
                total_voice_time INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')

        # Таблица сообщений по дням
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_messages_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                message_date DATE NOT NULL,
                message_count INTEGER DEFAULT 1,
                UNIQUE(guild_id, user_id, message_date)
            )
        ''')

        # Таблица времени в голосовых каналах (УПРОЩЕННАЯ - БЕЗ channel_id)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_voice_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                join_time TIMESTAMP NOT NULL,
                leave_time TIMESTAMP,
                duration INTEGER
            )
        ''')

        # Таблица ежедневного времени в войсе (для периодов)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_voice_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                voice_date DATE NOT NULL,
                voice_time INTEGER DEFAULT 0,
                UNIQUE(guild_id, user_id, voice_date)
            )
        ''')

        conn.commit()
        conn.close()

    def add_to_whitelist(self, guild_id: int, user_id: int, added_by: int) -> bool:
        """Добавить пользователя в whitelist"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO whitelist (guild_id, user_id, added_by)
                VALUES (?, ?, ?)
            ''', (guild_id, user_id, added_by))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error adding to whitelist: {e}")
            return False

    def remove_from_whitelist(self, guild_id: int, user_id: int) -> bool:
        """Удалить пользователя из whitelist"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                DELETE FROM whitelist
                WHERE guild_id = ? AND user_id = ?
            ''', (guild_id, user_id))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error removing from whitelist: {e}")
            return False

    def is_whitelisted(self, guild_id: int, user_id: int) -> bool:
        """Проверить, есть ли пользователь в whitelist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT 1 FROM whitelist
            WHERE guild_id = ? AND user_id = ?
        ''', (guild_id, user_id))

        result = cursor.fetchone() is not None
        conn.close()
        return result

    def get_whitelist(self, guild_id: int) -> list:
        """Получить список пользователей в whitelist для сервера"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT user_id, added_by, added_at FROM whitelist
            WHERE guild_id = ?
        ''', (guild_id,))

        results = cursor.fetchall()
        conn.close()
        return results

    # Методы для работы с опросами

    def create_poll(self, guild_id: int, channel_id: int, message_id: int,
                    question: str, options: list, emojis: list, created_by: int) -> str:
        """Создать новый опрос и вернуть его ID"""
        poll_id = str(uuid.uuid4())[:8]

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO polls (poll_id, guild_id, channel_id, message_id, question, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (poll_id, guild_id, channel_id, message_id, question, created_by))

            for i, (option, emoji) in enumerate(zip(options, emojis)):
                cursor.execute('''
                    INSERT INTO poll_options (poll_id, option_index, option_text, emoji)
                    VALUES (?, ?, ?, ?)
                ''', (poll_id, i, option, emoji))

            conn.commit()
            conn.close()
            return poll_id
        except Exception as e:
            print(f"Error creating poll: {e}")
            return None

    def add_vote(self, poll_id: str, user_id: int, option_index: int) -> bool:
        """Добавить голос пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO poll_votes (poll_id, user_id, option_index)
                VALUES (?, ?, ?)
            ''', (poll_id, user_id, option_index))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error adding vote: {e}")
            return False

    def remove_vote(self, poll_id: str, user_id: int, option_index: int) -> bool:
        """Удалить голос пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                DELETE FROM poll_votes
                WHERE poll_id = ? AND user_id = ? AND option_index = ?
            ''', (poll_id, user_id, option_index))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error removing vote: {e}")
            return False

    def get_poll_by_message(self, message_id: int):
        """Получить информацию об опросе по ID сообщения"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM polls WHERE message_id = ?
        ''', (message_id,))

        result = cursor.fetchone()
        conn.close()
        return result

    def get_poll_options(self, poll_id: str) -> list:
        """Получить варианты ответов для опроса"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT option_index, option_text, emoji FROM poll_options
            WHERE poll_id = ?
            ORDER BY option_index
        ''', (poll_id,))

        results = cursor.fetchall()
        conn.close()
        return results

    def get_poll_results(self, poll_id: str) -> dict:
        """Получить результаты голосования"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT question, is_closed FROM polls WHERE poll_id = ?
        ''', (poll_id,))
        poll_info = cursor.fetchone()

        if not poll_info:
            conn.close()
            return None

        question, is_closed = poll_info

        options = self.get_poll_options(poll_id)

        cursor.execute('''
            SELECT user_id, option_index, voted_at FROM poll_votes
            WHERE poll_id = ?
            ORDER BY voted_at
        ''', (poll_id,))
        
        votes = cursor.fetchall()
        conn.close()

        return {
            'poll_id': poll_id,
            'question': question,
            'is_closed': bool(is_closed),
            'options': options,
            'votes': votes
        }

    def close_poll(self, poll_id: str) -> bool:
        """Закрыть опрос"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE polls
                SET is_closed = 1
                WHERE poll_id = ?
            ''', (poll_id,))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error closing poll: {e}")
            return False

    def is_poll_closed(self, poll_id: str) -> bool:
        """Проверить, закрыт ли опрос"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT is_closed FROM polls WHERE poll_id = ?
        ''', (poll_id,))

        result = cursor.fetchone()
        conn.close()

        return bool(result[0]) if result else False

    def get_polls_by_date(self, guild_id: int, days: int) -> list:
        """Получить опросы за последние N дней"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT poll_id, question, created_by, created_at, is_closed FROM polls
            WHERE guild_id = ?
            AND created_at >= datetime('now', '-' || ? || ' days')
            ORDER BY created_at DESC
        ''', (guild_id, days))

        results = cursor.fetchall()
        conn.close()
        return results

    def get_all_polls(self, guild_id: int) -> list:
        """Получить все опросы сервера"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT poll_id, question, created_by, created_at, is_closed FROM polls
            WHERE guild_id = ?
            ORDER BY created_at DESC
        ''', (guild_id,))

        results = cursor.fetchall()
        conn.close()
        return results

    def close_all_open_polls(self, guild_id: int) -> int:
        """Закрыть все открытые опросы на сервере"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE polls
                SET is_closed = 1
                WHERE guild_id = ? AND is_closed = 0
            ''', (guild_id,))

            closed_count = cursor.rowcount
            conn.commit()
            conn.close()
            return closed_count
        except Exception as e:
            print(f"Error closing all polls: {e}")
            return 0

    def export_poll_to_csv(self, poll_id: str, guild=None) -> str:
        """Экспортировать результаты опроса в CSV (колоночный формат)"""
        results = self.get_poll_results(poll_id)
        if not results:
            return None

        output = StringIO()
        writer = csv.writer(output)

        # Шапка (оставляем как было)
        writer.writerow(['Poll Results Export'])
        writer.writerow(['Poll ID:', poll_id])
        writer.writerow(['Question:', results['question']])
        writer.writerow(['Status:', 'Closed' if results['is_closed'] else 'Open'])
        writer.writerow([])

        # Подсчитываем голоса и группируем по вариантам
        votes_by_option = {}  # {option_index: [user_ids]}
        total_votes = 0
        
        for user_id, option_index, voted_at in results['votes']:
            if option_index not in votes_by_option:
                votes_by_option[option_index] = []
            votes_by_option[option_index].append(user_id)
            total_votes += 1

        writer.writerow(['Total Votes:', total_votes])
        writer.writerow([])

        # Статистика по вариантам (краткая)
        writer.writerow(['Option', 'Votes', 'Percentage'])
        for option_index, option_text, emoji in results['options']:
            vote_count = len(votes_by_option.get(option_index, []))
            percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
            writer.writerow([
                f"{emoji} {option_text}",
                vote_count,
                f"{percentage:.1f}%"
            ])

        writer.writerow([])
        writer.writerow([])

        # НОВЫЙ ФОРМАТ: Колоночное представление голосов
        if guild:
            # Заголовки колонок - названия вариантов
            headers = []
            for option_index, option_text, emoji in results['options']:
                headers.append(f"{emoji} {option_text}")
            writer.writerow(headers)

            # Находим максимальное количество голосов в одном варианте
            max_votes = max([len(votes_by_option.get(opt[0], [])) for opt in results['options']], default=0)

            # Заполняем данные построчно
            for row_index in range(max_votes):
                row = []
                for option_index, option_text, emoji in results['options']:
                    voters = votes_by_option.get(option_index, [])
                    
                    if row_index < len(voters):
                        user_id = voters[row_index]
                        member = guild.get_member(user_id)
                        username = member.display_name if member else f"Unknown (ID: {user_id})"
                        row.append(username)
                    else:
                        row.append('')  # Пустая ячейка если голосов меньше
                
                writer.writerow(row)

        return output.getvalue()

    def export_polls_to_csv(self, poll_ids: list, guild=None) -> str:
        """Экспортировать несколько опросов в один CSV"""
        output = StringIO()
        writer = csv.writer(output)

        writer.writerow(['Multiple Polls Export'])
        writer.writerow(['Total Polls:', len(poll_ids)])
        writer.writerow([])

        for poll_id in poll_ids:
            results = self.get_poll_results(poll_id)
            if not results:
                continue

            writer.writerow([])
            writer.writerow(['=' * 50])
            writer.writerow(['Poll ID:', poll_id])
            writer.writerow(['Question:', results['question']])
            writer.writerow(['Status:', 'Closed' if results['is_closed'] else 'Open'])
            
            votes_by_option = {}
            total_votes = 0
            for user_id, option_index, voted_at in results['votes']:
                votes_by_option[option_index] = votes_by_option.get(option_index, 0) + 1
                total_votes += 1
            
            writer.writerow(['Total Votes:', total_votes])
            writer.writerow([])

            writer.writerow(['Option', 'Votes', 'Percentage'])
            for option_index, option_text, emoji in results['options']:
                vote_count = votes_by_option.get(option_index, 0)
                percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
                writer.writerow([
                    f"{emoji} {option_text}",
                    vote_count,
                    f"{percentage:.1f}%"
                ])

            writer.writerow([])

        return output.getvalue()

    # Методы для работы со статистикой

    def log_message(self, guild_id: int, user_id: int):
        """Логировать сообщение пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO user_stats_total (guild_id, user_id, total_messages)
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                total_messages = total_messages + 1
            ''', (guild_id, user_id))

            cursor.execute('''
                INSERT INTO user_messages_daily (guild_id, user_id, message_date, message_count)
                VALUES (?, ?, DATE('now'), 1)
                ON CONFLICT(guild_id, user_id, message_date) DO UPDATE SET
                message_count = message_count + 1
            ''', (guild_id, user_id))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error logging message: {e}")
            return False

    # ========== ГОЛОСОВЫЕ СЕССИИ ==========

    def start_voice_session(self, guild_id: int, user_id: int):
        """Начать голосовую сессию"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Проверяем, есть ли уже открытая сессия
            cursor.execute('''
                SELECT id FROM user_voice_sessions
                WHERE guild_id = ? AND user_id = ? AND leave_time IS NULL
            ''', (guild_id, user_id))
            
            existing_session = cursor.fetchone()
            
            if existing_session:
                print(f"⚠️ User {user_id} already has an active voice session")
                conn.close()
                return existing_session[0]

            cursor.execute('''
                INSERT INTO user_voice_sessions (guild_id, user_id, join_time)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (guild_id, user_id))

            conn.commit()
            session_id = cursor.lastrowid
            conn.close()
            
            print(f"✅ Voice session started for user {user_id}, session_id: {session_id}")
            return session_id
        except Exception as e:
            print(f"❌ Error starting voice session: {e}")
            return None

    def end_voice_session(self, guild_id: int, user_id: int):
        """Закончить голосовую сессию"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id, join_time FROM user_voice_sessions
                WHERE guild_id = ? AND user_id = ? AND leave_time IS NULL
                ORDER BY join_time DESC LIMIT 1
            ''', (guild_id, user_id))

            session = cursor.fetchone()
            if not session:
                print(f"⚠️ No active voice session found for user {user_id}")
                conn.close()
                return False

            session_id, join_time = session

            cursor.execute('''
                UPDATE user_voice_sessions
                SET leave_time = CURRENT_TIMESTAMP,
                    duration = (julianday(CURRENT_TIMESTAMP) - julianday(join_time)) * 86400
                WHERE id = ?
            ''', (session_id,))

            cursor.execute('SELECT duration FROM user_voice_sessions WHERE id = ?', (session_id,))
            duration = cursor.fetchone()[0]

            if duration is None or duration < 0:
                print(f"⚠️ Invalid duration calculated for session {session_id}")
                conn.rollback()
                conn.close()
                return False

            # Обновляем статистику
            cursor.execute('''
                INSERT INTO user_stats_total (guild_id, user_id, total_voice_time)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                total_voice_time = total_voice_time + ?
            ''', (guild_id, user_id, int(duration), int(duration)))

            cursor.execute('''
                INSERT INTO user_voice_daily (guild_id, user_id, voice_date, voice_time)
                VALUES (?, ?, DATE('now'), ?)
                ON CONFLICT(guild_id, user_id, voice_date) DO UPDATE SET
                voice_time = voice_time + ?
            ''', (guild_id, user_id, int(duration), int(duration)))

            conn.commit()
            conn.close()
            
            print(f"✅ Voice session ended for user {user_id}, duration: {int(duration)}s")
            return True
        except Exception as e:
            print(f"❌ Error ending voice session: {e}")
            return False

    def close_hanging_voice_sessions(self, max_duration_hours: int = 24):
        """Закрыть все зависшие голосовые сессии"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id, guild_id, user_id, join_time 
                FROM user_voice_sessions
                WHERE leave_time IS NULL
                AND julianday(CURRENT_TIMESTAMP) - julianday(join_time) > ?
            ''', (max_duration_hours / 24,))

            hanging_sessions = cursor.fetchall()
            
            if not hanging_sessions:
                conn.close()
                return 0

            closed_count = 0
            for session_id, guild_id, user_id, join_time in hanging_sessions:
                max_duration_seconds = max_duration_hours * 3600
                
                cursor.execute('''
                    UPDATE user_voice_sessions
                    SET leave_time = datetime(join_time, '+' || ? || ' hours'),
                        duration = ?
                    WHERE id = ?
                ''', (max_duration_hours, max_duration_seconds, session_id))

                cursor.execute('''
                    INSERT INTO user_stats_total (guild_id, user_id, total_voice_time)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    total_voice_time = total_voice_time + ?
                ''', (guild_id, user_id, max_duration_seconds, max_duration_seconds))

                closed_count += 1
                print(f"🔧 Closed hanging session {session_id} for user {user_id}")

            conn.commit()
            conn.close()
            
            return closed_count
        except Exception as e:
            print(f"❌ Error closing hanging sessions: {e}")
            return 0

    def force_end_all_voice_sessions(self, guild_id: int = None):
        """Принудительно закрыть ВСЕ активные голосовые сессии"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            if guild_id:
                cursor.execute('''
                    SELECT id, guild_id, user_id, join_time 
                    FROM user_voice_sessions
                    WHERE guild_id = ? AND leave_time IS NULL
                ''', (guild_id,))
            else:
                cursor.execute('''
                    SELECT id, guild_id, user_id, join_time 
                    FROM user_voice_sessions
                    WHERE leave_time IS NULL
                ''')

            active_sessions = cursor.fetchall()
            
            if not active_sessions:
                conn.close()
                return 0

            closed_count = 0
            for session_id, g_id, user_id, join_time in active_sessions:
                cursor.execute('''
                    UPDATE user_voice_sessions
                    SET leave_time = CURRENT_TIMESTAMP,
                        duration = (julianday(CURRENT_TIMESTAMP) - julianday(join_time)) * 86400
                    WHERE id = ?
                ''', (session_id,))

                cursor.execute('SELECT duration FROM user_voice_sessions WHERE id = ?', (session_id,))
                duration = cursor.fetchone()[0]

                if duration and duration > 0:
                    cursor.execute('''
                        INSERT INTO user_stats_total (guild_id, user_id, total_voice_time)
                        VALUES (?, ?, ?)
                        ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        total_voice_time = total_voice_time + ?
                    ''', (g_id, user_id, int(duration), int(duration)))

                closed_count += 1
                print(f"🔧 Force closed session {session_id} for user {user_id}")

            conn.commit()
            conn.close()
            
            return closed_count
        except Exception as e:
            print(f"❌ Error force closing sessions: {e}")
            return 0

    def get_active_voice_sessions(self, guild_id: int = None) -> list:
        """Получить список всех активных голосовых сессий"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            if guild_id:
                cursor.execute('''
                    SELECT id, guild_id, user_id, join_time,
                           (julianday(CURRENT_TIMESTAMP) - julianday(join_time)) * 86400 as current_duration
                    FROM user_voice_sessions
                    WHERE guild_id = ? AND leave_time IS NULL
                    ORDER BY join_time DESC
                ''', (guild_id,))
            else:
                cursor.execute('''
                    SELECT id, guild_id, user_id, join_time,
                           (julianday(CURRENT_TIMESTAMP) - julianday(join_time)) * 86400 as current_duration
                    FROM user_voice_sessions
                    WHERE leave_time IS NULL
                    ORDER BY join_time DESC
                ''')

            sessions = cursor.fetchall()
            conn.close()
            return sessions
        except Exception as e:
            print(f"❌ Error getting active sessions: {e}")
            return []

    def cleanup_old_data(self):
        """Удалить данные старше 30 дней"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                DELETE FROM user_messages_daily
                WHERE message_date < DATE('now', '-30 days')
            ''')
            deleted_messages = cursor.rowcount

            cursor.execute('''
                DELETE FROM user_voice_sessions
                WHERE join_time < DATETIME('now', '-30 days')
            ''')
            deleted_voice = cursor.rowcount

            cursor.execute('''
                DELETE FROM user_voice_daily
                WHERE voice_date < DATE('now', '-30 days')
            ''')
            deleted_voice_daily = cursor.rowcount

            conn.commit()
            conn.close()
            
            total_deleted = deleted_messages + deleted_voice + deleted_voice_daily
            print(f"🧹 Cleanup: deleted {deleted_messages} message records, {deleted_voice} voice sessions, {deleted_voice_daily} voice daily records")
            return total_deleted
        except Exception as e:
            print(f"❌ Error cleaning up old data: {e}")
            return 0

    def get_user_stats(self, guild_id: int, user_id: int, days: int = None) -> dict:
        """Получить статистику пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT total_messages, total_voice_time FROM user_stats_total
            WHERE guild_id = ? AND user_id = ?
        ''', (guild_id, user_id))
        total_stats = cursor.fetchone()

        if not total_stats:
            conn.close()
            return None

        total_messages, total_voice_time = total_stats

        if days:
            cursor.execute('''
                SELECT SUM(message_count) FROM user_messages_daily
                WHERE guild_id = ? AND user_id = ?
                AND message_date >= DATE('now', '-' || ? || ' days')
            ''', (guild_id, user_id, days))
            period_messages = cursor.fetchone()[0] or 0
        else:
            period_messages = total_messages

        if days:
            cursor.execute('''
                SELECT SUM(voice_time) FROM user_voice_daily
                WHERE guild_id = ? AND user_id = ?
                AND voice_date >= DATE('now', '-' || ? || ' days')
            ''', (guild_id, user_id, days))
            period_voice_time = cursor.fetchone()[0] or 0
        else:
            period_voice_time = total_voice_time or 0

        conn.close()

        return {
            'total_messages': total_messages,
            'total_voice_time': total_voice_time or 0,
            'period_messages': period_messages,
            'period_voice_time': int(period_voice_time),
            'voice_by_channel': []
        }

    def get_all_users_stats(self, guild_id: int, days: int = None) -> list:
        """Получить статистику всех пользователей сервера"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT user_id, total_messages, total_voice_time
            FROM user_stats_total
            WHERE guild_id = ?
            ORDER BY total_messages DESC
        ''', (guild_id,))

        users_total = cursor.fetchall()

        if not users_total:
            conn.close()
            return []

        result = []

        for user_id, total_messages, total_voice_time in users_total:
            if days:
                cursor.execute('''
                    SELECT SUM(message_count) FROM user_messages_daily
                    WHERE guild_id = ? AND user_id = ?
                    AND message_date >= DATE('now', '-' || ? || ' days')
                ''', (guild_id, user_id, days))
                period_messages = cursor.fetchone()[0] or 0
            else:
                period_messages = total_messages

            if days:
                cursor.execute('''
                    SELECT SUM(voice_time) FROM user_voice_daily
                    WHERE guild_id = ? AND user_id = ?
                    AND voice_date >= DATE('now', '-' || ? || ' days')
                ''', (guild_id, user_id, days))
                period_voice = cursor.fetchone()[0] or 0
            else:
                period_voice = total_voice_time or 0

            result.append({
                'user_id': user_id,
                'total_messages': total_messages,
                'total_voice_time': total_voice_time or 0,
                'period_messages': period_messages,
                'period_voice_time': int(period_voice)
            })

        conn.close()
        return result