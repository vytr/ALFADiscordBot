import sqlite3
import os
import uuid
import csv
from io import StringIO
from datetime import datetime, timedelta

class Database:
    """Класс для работы с базой данных"""

    def __init__(self, db_path='bot_database.db', polls_db_path='polls_database.db'):
        self.db_path = db_path
        self.polls_db_path = polls_db_path
        self.init_db()
        self.init_polls_db()
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
        """Инициализация основной базы данных"""
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

        # Таблица выговоров
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                warned_by INTEGER NOT NULL,
                warned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                is_active INTEGER DEFAULT 1,
                removed_at TIMESTAMP,
                removed_by INTEGER,
                removal_reason TEXT
            )
        ''')

        # Таблица статистики напитков
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS drink_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                drink_type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                drunk_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Старые таблицы опросов (оставляем для совместимости, но не используем)
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

        conn.commit()
        conn.close()

    def init_polls_db(self):
        """Инициализация отдельной БД для нативных опросов Discord"""
        conn = sqlite3.connect(self.polls_db_path)
        cursor = conn.cursor()
        
        # Таблица для отслеживания опросов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS polls (
                message_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица для вариантов ответов опросов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS poll_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                answer_id INTEGER NOT NULL,
                answer_text TEXT NOT NULL,
                FOREIGN KEY (message_id) REFERENCES polls(message_id),
                UNIQUE(message_id, answer_id)
            )
        ''')
        
        # Таблица голосов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS poll_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                answer_id INTEGER NOT NULL,
                voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id) REFERENCES polls(message_id),
                UNIQUE(message_id, user_id, answer_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ Polls database initialized")

    # ========================================
    # WHITELIST МЕТОДЫ
    # ========================================

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

    # ========================================
    # СТАТИСТИКА МЕТОДЫ
    # ========================================

    def log_message(self, guild_id: int, user_id: int):
        """Логировать сообщение пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Обновляем общую статистику
            cursor.execute('''
                INSERT INTO user_stats_total (guild_id, user_id, total_messages)
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                total_messages = total_messages + 1
            ''', (guild_id, user_id))

            # Обновляем дневную статистику
            cursor.execute('''
                INSERT INTO user_messages_daily (guild_id, user_id, message_date)
                VALUES (?, ?, DATE('now'))
                ON CONFLICT(guild_id, user_id, message_date) DO UPDATE SET
                message_count = message_count + 1
            ''', (guild_id, user_id))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error logging message: {e}")

    def start_voice_session(self, guild_id: int, user_id: int):
        """Начать новую голосовую сессию"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Проверяем, нет ли уже активной сессии
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

    def _distribute_voice_time_across_dates(self, cursor, guild_id: int, user_id: int, 
                                           join_time_str: str, leave_time_str: str, total_duration: int):
        """
        ИСПРАВЛЕНИЕ БАГА: Распределяет время голосовой сессии по датам.
        
        Если сессия пересекает полночь, время правильно распределяется между датами.
        Например: 23:00-02:00 (3 часа) → 17 января: 1 час, 18 января: 2 часа
        """
        try:
            # Парсим timestamps
            join_time = datetime.strptime(join_time_str, '%Y-%m-%d %H:%M:%S')
            leave_time = datetime.strptime(leave_time_str, '%Y-%m-%d %H:%M:%S')
            
            current_date = join_time.date()
            end_date = leave_time.date()
            
            remaining_duration = total_duration
            
            while current_date <= end_date:
                # Определяем границы текущего дня
                day_start = datetime.combine(current_date, datetime.min.time())
                day_end = datetime.combine(current_date, datetime.max.time())
                
                # Определяем фактическое начало и конец для этого дня
                actual_start = max(join_time, day_start)
                actual_end = min(leave_time, day_end)
                
                # Вычисляем длительность для этого дня
                day_duration = int((actual_end - actual_start).total_seconds())
                
                if day_duration > 0:
                    # Записываем время для текущей даты
                    cursor.execute('''
                        INSERT INTO user_voice_daily (guild_id, user_id, voice_date, voice_time)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(guild_id, user_id, voice_date) DO UPDATE SET
                        voice_time = voice_time + ?
                    ''', (guild_id, user_id, current_date.isoformat(), day_duration, day_duration))
                    
                    remaining_duration -= day_duration
                    print(f"📅 Distributed {day_duration}s to date {current_date}")
                
                # Переходим к следующему дню
                current_date += timedelta(days=1)
            
            # Проверка: всё время должно быть распределено
            if remaining_duration > 1:  # допуск 1 секунда на округления
                print(f"⚠️ Warning: {remaining_duration}s not distributed!")
                
        except Exception as e:
            print(f"❌ Error distributing voice time: {e}")
            raise

    def end_voice_session(self, guild_id: int, user_id: int):
        """Закончить голосовую сессию - ИСПРАВЛЕНО"""
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

            cursor.execute('SELECT duration, leave_time FROM user_voice_sessions WHERE id = ?', (session_id,))
            result = cursor.fetchone()
            duration, leave_time = result

            if duration is None or duration < 0:
                print(f"⚠️ Invalid duration calculated for session {session_id}")
                conn.rollback()
                conn.close()
                return False

            # Обновляем общую статистику
            cursor.execute('''
                INSERT INTO user_stats_total (guild_id, user_id, total_voice_time)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                total_voice_time = total_voice_time + ?
            ''', (guild_id, user_id, int(duration), int(duration)))

            # ИСПРАВЛЕНИЕ: Распределяем время по датам
            self._distribute_voice_time_across_dates(
                cursor, guild_id, user_id, join_time, leave_time, int(duration)
            )

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
                
                # Вычисляем leave_time
                leave_time_str = cursor.execute('''
                    SELECT datetime(?, '+' || ? || ' hours')
                ''', (join_time, max_duration_hours)).fetchone()[0]
                
                cursor.execute('''
                    UPDATE user_voice_sessions
                    SET leave_time = ?,
                        duration = ?
                    WHERE id = ?
                ''', (leave_time_str, max_duration_seconds, session_id))

                cursor.execute('''
                    INSERT INTO user_stats_total (guild_id, user_id, total_voice_time)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    total_voice_time = total_voice_time + ?
                ''', (guild_id, user_id, max_duration_seconds, max_duration_seconds))

                # ИСПРАВЛЕНИЕ: Распределяем время по датам
                self._distribute_voice_time_across_dates(
                    cursor, guild_id, user_id, join_time, leave_time_str, max_duration_seconds
                )

                closed_count += 1
                print(f"🔧 Closed hanging session {session_id} for user {user_id}")

            conn.commit()
            conn.close()
            
            return closed_count
        except Exception as e:
            print(f"❌ Error closing hanging sessions: {e}")
            return 0

    def force_end_all_voice_sessions(self):
        """Принудительно закрыть ВСЕ активные сессии (безопасный перезапуск)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

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

                cursor.execute('SELECT duration, leave_time FROM user_voice_sessions WHERE id = ?', (session_id,))
                result = cursor.fetchone()
                duration, leave_time = result

                if duration and duration > 0:
                    cursor.execute('''
                        INSERT INTO user_stats_total (guild_id, user_id, total_voice_time)
                        VALUES (?, ?, ?)
                        ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        total_voice_time = total_voice_time + ?
                    ''', (g_id, user_id, int(duration), int(duration)))
                    
                    # ИСПРАВЛЕНИЕ: Распределяем время по датам
                    self._distribute_voice_time_across_dates(
                        cursor, g_id, user_id, join_time, leave_time, int(duration)
                    )

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

            cursor.execute('''
                SELECT SUM(voice_time) FROM user_voice_daily
                WHERE guild_id = ? AND user_id = ?
                AND voice_date >= DATE('now', '-' || ? || ' days')
            ''', (guild_id, user_id, days))
            period_voice = cursor.fetchone()[0] or 0
        else:
            period_messages = total_messages
            period_voice = total_voice_time

        conn.close()

        return {
            'total_messages': total_messages,
            'total_voice_time': total_voice_time,
            'period_messages': period_messages,
            'period_voice_time': period_voice,
            'voice_by_channel': []  # Упрощенная версия без channel_id
        }

    def get_all_users_stats(self, guild_id: int, days: int = None, role_id: int = None) -> list:
        """Получить статистику всех пользователей"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if days:
            cursor.execute('''
                SELECT 
                    s.user_id,
                    s.total_messages,
                    s.total_voice_time,
                    COALESCE(SUM(m.message_count), 0) as period_messages,
                    COALESCE(SUM(v.voice_time), 0) as period_voice_time
                FROM user_stats_total s
                LEFT JOIN user_messages_daily m ON s.guild_id = m.guild_id 
                    AND s.user_id = m.user_id 
                    AND m.message_date >= DATE('now', '-' || ? || ' days')
                LEFT JOIN user_voice_daily v ON s.guild_id = v.guild_id 
                    AND s.user_id = v.user_id 
                    AND v.voice_date >= DATE('now', '-' || ? || ' days')
                WHERE s.guild_id = ?
                GROUP BY s.user_id
                ORDER BY period_voice_time DESC, period_messages DESC
            ''', (days, days, guild_id))
        else:
            cursor.execute('''
                SELECT user_id, total_messages, total_voice_time,
                       total_messages as period_messages,
                       total_voice_time as period_voice_time
                FROM user_stats_total
                WHERE guild_id = ?
                ORDER BY total_voice_time DESC, total_messages DESC
            ''', (guild_id,))

        results = cursor.fetchall()
        conn.close()

        return [
            {
                'user_id': r[0],
                'total_messages': r[1],
                'total_voice_time': r[2],
                'period_messages': r[3],
                'period_voice_time': r[4]
            }
            for r in results
        ]

    def get_inactive_users(self, guild_id: int, days: int) -> list:
        """Получить список неактивных пользователей"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT DISTINCT user_id FROM user_stats_total
            WHERE guild_id = ?
        ''', (guild_id,))
        
        all_users = {row[0] for row in cursor.fetchall()}

        cursor.execute('''
            SELECT DISTINCT user_id FROM user_messages_daily
            WHERE guild_id = ? AND message_date >= DATE('now', '-' || ? || ' days')
            UNION
            SELECT DISTINCT user_id FROM user_voice_daily
            WHERE guild_id = ? AND voice_date >= DATE('now', '-' || ? || ' days')
        ''', (guild_id, days, guild_id, days))

        active_users = {row[0] for row in cursor.fetchall()}
        conn.close()

        inactive_user_ids = list(all_users - active_users)
        return inactive_user_ids

    # ========================================
    # МЕТОДЫ ДЛЯ ВЫГОВОРОВ
    # ========================================

    def add_warning(self, guild_id: int, user_id: int, reason: str, warned_by: int, expires_at: datetime) -> int:
        """Добавить выговор"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO warnings (guild_id, user_id, reason, warned_by, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (guild_id, user_id, reason, warned_by, expires_at.strftime('%Y-%m-%d %H:%M:%S')))

            warning_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return warning_id
        except Exception as e:
            print(f"Error adding warning: {e}")
            return 0

    def remove_warning(self, warning_id: int, removed_by: int, reason: str = None) -> bool:
        """Снять выговор"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE warnings
                SET is_active = 0,
                    removed_at = CURRENT_TIMESTAMP,
                    removed_by = ?,
                    removal_reason = ?
                WHERE id = ? AND is_active = 1
            ''', (removed_by, reason, warning_id))

            success = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return success
        except Exception as e:
            print(f"Error removing warning: {e}")
            return False

    def get_user_warnings(self, guild_id: int, user_id: int) -> list:
        """Получить все выговоры пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, reason, warned_by, warned_at, expires_at, is_active, removed_at, removed_by, removal_reason
            FROM warnings
            WHERE guild_id = ? AND user_id = ?
            ORDER BY warned_at DESC
        ''', (guild_id, user_id))

        results = cursor.fetchall()
        conn.close()
        return results

    def expire_warnings(self) -> int:
        """Автоматически снять истёкшие выговоры"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE warnings
                SET is_active = 0
                WHERE is_active = 1 AND expires_at <= CURRENT_TIMESTAMP
            ''')

            expired_count = cursor.rowcount
            conn.commit()
            conn.close()
            return expired_count
        except Exception as e:
            print(f"Error expiring warnings: {e}")
            return 0

    def get_all_active_warnings(self, guild_id: int) -> list:
        """Получить все активные выговоры на сервере"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT user_id, COUNT(*) as warning_count
            FROM warnings
            WHERE guild_id = ? AND is_active = 1
            AND expires_at > CURRENT_TIMESTAMP
            GROUP BY user_id
            ORDER BY warning_count DESC
        ''', (guild_id,))

        results = cursor.fetchall()
        conn.close()
        return results

    # ========================================
    # МЕТОДЫ ДЛЯ НАПИТКОВ
    # ========================================

    def log_drink(self, guild_id: int, user_id: int, drink_type: str, amount: int) -> bool:
        """Залогировать выпитый напиток"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO drink_stats (guild_id, user_id, drink_type, amount)
                VALUES (?, ?, ?, ?)
            ''', (guild_id, user_id, drink_type, amount))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error logging drink: {e}")
            return False

    def get_user_drinks(self, guild_id: int, user_id: int, days: int = None) -> dict:
        """Получить статистику напитков пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if days:
            cursor.execute('''
                SELECT drink_type, SUM(amount) as total
                FROM drink_stats
                WHERE guild_id = ? AND user_id = ?
                AND drunk_at >= datetime('now', '-' || ? || ' days')
                GROUP BY drink_type
            ''', (guild_id, user_id, days))
        else:
            cursor.execute('''
                SELECT drink_type, SUM(amount) as total
                FROM drink_stats
                WHERE guild_id = ? AND user_id = ?
                GROUP BY drink_type
            ''', (guild_id, user_id))

        results = cursor.fetchall()
        conn.close()

        return {drink_type: total for drink_type, total in results}

    # ========================================
    # МЕТОДЫ ДЛЯ НАТИВНЫХ ОПРОСОВ DISCORD
    # ========================================

    def register_poll(self, message_id: int, guild_id: int, channel_id: int, 
                     question: str, answers: list) -> bool:
        """Зарегистрировать нативный опрос Discord"""
        try:
            conn = sqlite3.connect(self.polls_db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO polls (message_id, guild_id, channel_id, question)
                VALUES (?, ?, ?, ?)
            ''', (message_id, guild_id, channel_id, question))
            
            for answer_id, answer_text in enumerate(answers):
                cursor.execute('''
                    INSERT OR REPLACE INTO poll_options (message_id, answer_id, answer_text)
                    VALUES (?, ?, ?)
                ''', (message_id, answer_id, answer_text))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error registering poll: {e}")
            return False

    def get_poll(self, message_id: int) -> dict:
        """Получить информацию об опросе"""
        conn = sqlite3.connect(self.polls_db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT message_id, guild_id, channel_id, question, discovered_at
            FROM polls
            WHERE message_id = ?
        ''', (message_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return None
        
        return {
            'message_id': result[0],
            'guild_id': result[1],
            'channel_id': result[2],
            'question': result[3],
            'discovered_at': result[4]
        }

    def add_poll_vote(self, message_id: int, user_id: int, answer_id: int) -> bool:
        """Добавить голос в опросе"""
        try:
            conn = sqlite3.connect(self.polls_db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO poll_votes (message_id, user_id, answer_id)
                VALUES (?, ?, ?)
            ''', (message_id, user_id, answer_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error adding poll vote: {e}")
            return False

    def remove_poll_vote(self, message_id: int, user_id: int, answer_id: int) -> bool:
        """Удалить голос из опроса"""
        try:
            conn = sqlite3.connect(self.polls_db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM poll_votes
                WHERE message_id = ? AND user_id = ? AND answer_id = ?
            ''', (message_id, user_id, answer_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error removing poll vote: {e}")
            return False

    def get_poll_votes(self, message_id: int) -> list:
        """Получить все голоса в опросе"""
        conn = sqlite3.connect(self.polls_db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, answer_id, voted_at
            FROM poll_votes
            WHERE message_id = ?
            ORDER BY voted_at
        ''', (message_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        return results

    def get_all_polls(self, guild_id: int) -> list:
        """Получить все опросы сервера"""
        conn = sqlite3.connect(self.polls_db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT message_id, question, discovered_at
            FROM polls
            WHERE guild_id = ?
            ORDER BY discovered_at DESC
        ''', (guild_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        return [
            {
                'message_id': r[0],
                'question': r[1],
                'discovered_at': r[2]
            }
            for r in results
        ]

    def get_poll_options(self, message_id: int) -> list:
        """Получить варианты ответов опроса из БД"""
        conn = sqlite3.connect(self.polls_db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT answer_id, answer_text
            FROM poll_options
            WHERE message_id = ?
            ORDER BY answer_id
        ''', (message_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        return results