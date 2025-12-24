import sqlite3
import os
import uuid
import csv
from io import StringIO

class Database:
    """Класс для работы с базой данных whitelist и опросов"""

    def __init__(self, db_path='bot_database.db'):
        self.db_path = db_path
        self.init_db()

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

        # Таблица времени в голосовых каналах
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_voice_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                join_time TIMESTAMP NOT NULL,
                leave_time TIMESTAMP,
                duration INTEGER
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
        poll_id = str(uuid.uuid4())[:8]  # Короткий ID

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Сохраняем опрос
            cursor.execute('''
                INSERT INTO polls (poll_id, guild_id, channel_id, message_id, question, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (poll_id, guild_id, channel_id, message_id, question, created_by))

            # Сохраняем варианты ответов
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
        """Получить опрос по ID сообщения"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT poll_id, question FROM polls
            WHERE message_id = ?
        ''', (message_id,))

        result = cursor.fetchone()
        conn.close()
        return result

    def get_poll_options(self, poll_id: str) -> list:
        """Получить варианты ответов опроса"""
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
        """Получить результаты опроса с информацией о проголосовавших"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Получаем информацию об опросе
        cursor.execute('''
            SELECT question, created_by, created_at, is_closed FROM polls
            WHERE poll_id = ?
        ''', (poll_id,))
        poll_info = cursor.fetchone()

        if not poll_info:
            conn.close()
            return None

        # Получаем варианты ответов
        cursor.execute('''
            SELECT option_index, option_text, emoji FROM poll_options
            WHERE poll_id = ?
            ORDER BY option_index
        ''', (poll_id,))
        options = cursor.fetchall()

        # Получаем голоса
        cursor.execute('''
            SELECT user_id, option_index, voted_at FROM poll_votes
            WHERE poll_id = ?
            ORDER BY voted_at
        ''', (poll_id,))
        votes = cursor.fetchall()

        conn.close()

        return {
            'poll_id': poll_id,
            'question': poll_info[0],
            'created_by': poll_info[1],
            'created_at': poll_info[2],
            'is_closed': poll_info[3],
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

            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()
            return rows_affected > 0
        except Exception as e:
            print(f"Error closing poll: {e}")
            return False

    def is_poll_closed(self, poll_id: str) -> bool:
        """Проверить, закрыт ли опрос"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT is_closed FROM polls
            WHERE poll_id = ?
        ''', (poll_id,))

        result = cursor.fetchone()
        conn.close()

        return result[0] == 1 if result else False

    def get_polls_by_date(self, guild_id: int, days: int) -> list:
        """Получить список опросов за последние N дней"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT poll_id, question, created_by, created_at, is_closed
            FROM polls
            WHERE guild_id = ?
            AND datetime(created_at) >= datetime('now', '-' || ? || ' days')
            ORDER BY created_at DESC
        ''', (guild_id, days))

        results = cursor.fetchall()
        conn.close()
        return results

    def get_all_polls(self, guild_id: int) -> list:
        """Получить все опросы для сервера"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT poll_id, question, created_by, created_at, is_closed
            FROM polls
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
        """Экспортировать данные опроса в CSV формат"""
        results = self.get_poll_results(poll_id)
        if not results:
            return None

        output = StringIO()
        writer = csv.writer(output)

        # Заголовок с информацией об опросе
        writer.writerow(['Poll ID:', results['poll_id']])
        writer.writerow(['Question:', results['question']])
        writer.writerow(['Created At:', results['created_at']])
        writer.writerow(['Status:', 'Закрыт' if results['is_closed'] else 'Активен'])
        writer.writerow([])  # Пустая строка

        # Группируем голоса по вариантам ответа
        votes_by_option = {}
        for user_id, option_index, voted_at in results['votes']:
            if option_index not in votes_by_option:
                votes_by_option[option_index] = []
            votes_by_option[option_index].append((user_id, voted_at))

        # Создаем заголовок с вариантами ответов
        headers = []
        for option_index, option_text, emoji in results['options']:
            headers.append(f"{emoji} {option_text}")
        writer.writerow(headers)

        # Находим максимальное количество голосов в одном варианте
        max_votes = max([len(votes_by_option.get(opt[0], [])) for opt in results['options']], default=0)

        # Записываем пользователей построчно
        for i in range(max_votes):
            row = []
            for option_index, option_text, emoji in results['options']:
                voters = votes_by_option.get(option_index, [])
                if i < len(voters):
                    user_id, voted_at = voters[i]
                    # Пытаемся получить серверный ник пользователя
                    if guild:
                        member = guild.get_member(user_id)
                        user_name = member.display_name if member else f"User ID: {user_id}"
                    else:
                        user_name = f"User ID: {user_id}"
                    row.append(f"{user_name}")
                else:
                    row.append('')
            writer.writerow(row)

        return output.getvalue()

    def export_polls_to_csv(self, poll_ids: list, guild=None) -> str:
        """Экспортировать несколько опросов в один CSV файл"""
        output = StringIO()
        writer = csv.writer(output)

        for idx, poll_id in enumerate(poll_ids):
            results = self.get_poll_results(poll_id)
            if not results:
                continue

            # Разделитель между опросами
            if idx > 0:
                writer.writerow([])
                writer.writerow(['=' * 50])
                writer.writerow([])

            # Заголовок с информацией об опросе
            writer.writerow(['Poll ID:', results['poll_id']])
            writer.writerow(['Question:', results['question']])
            writer.writerow(['Created At:', results['created_at']])
            writer.writerow(['Status:', 'Закрыт' if results['is_closed'] else 'Активен'])
            writer.writerow([])

            # Группируем голоса по вариантам ответа
            votes_by_option = {}
            for user_id, option_index, voted_at in results['votes']:
                if option_index not in votes_by_option:
                    votes_by_option[option_index] = []
                votes_by_option[option_index].append((user_id, voted_at))

            # Создаем заголовок с вариантами ответов
            headers = []
            for option_index, option_text, emoji in results['options']:
                headers.append(f"{emoji} {option_text}")
            writer.writerow(headers)

            # Находим максимальное количество голосов в одном варианте
            max_votes = max([len(votes_by_option.get(opt[0], [])) for opt in results['options']], default=0)

            # Записываем пользователей построчно
            for i in range(max_votes):
                row = []
                for option_index, option_text, emoji in results['options']:
                    voters = votes_by_option.get(option_index, [])
                    if i < len(voters):
                        user_id, voted_at = voters[i]
                        # Пытаемся получить серверный ник пользователя
                        if guild:
                            member = guild.get_member(user_id)
                            user_name = member.display_name if member else f"User ID: {user_id}"
                        else:
                            user_name = f"User ID: {user_id}"
                        row.append(f"{user_name}")
                    else:
                        row.append('')
                writer.writerow(row)

        return output.getvalue()

    # Методы для работы со статистикой пользователей

    def log_message(self, guild_id: int, user_id: int):
        """Записать сообщение пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Увеличиваем общий счетчик
            cursor.execute('''
                INSERT INTO user_stats_total (guild_id, user_id, total_messages)
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                total_messages = total_messages + 1
            ''', (guild_id, user_id))

            # Увеличиваем счетчик за сегодня
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

    def start_voice_session(self, guild_id: int, user_id: int, channel_id: int):
        """Начать голосовую сессию"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO user_voice_sessions (guild_id, user_id, channel_id, join_time)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (guild_id, user_id, channel_id))

            conn.commit()
            session_id = cursor.lastrowid
            conn.close()
            return session_id
        except Exception as e:
            print(f"Error starting voice session: {e}")
            return None

    def end_voice_session(self, guild_id: int, user_id: int, channel_id: int):
        """Закончить голосовую сессию"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Находим незавершенную сессию
            cursor.execute('''
                SELECT id, join_time FROM user_voice_sessions
                WHERE guild_id = ? AND user_id = ? AND channel_id = ? AND leave_time IS NULL
                ORDER BY join_time DESC LIMIT 1
            ''', (guild_id, user_id, channel_id))

            session = cursor.fetchone()
            if not session:
                conn.close()
                return False

            session_id, join_time = session

            # Обновляем сессию
            cursor.execute('''
                UPDATE user_voice_sessions
                SET leave_time = CURRENT_TIMESTAMP,
                    duration = (julianday(CURRENT_TIMESTAMP) - julianday(join_time)) * 86400
                WHERE id = ?
            ''', (session_id,))

            # Получаем длительность
            cursor.execute('SELECT duration FROM user_voice_sessions WHERE id = ?', (session_id,))
            duration = cursor.fetchone()[0]

            # Обновляем общую статистику
            cursor.execute('''
                INSERT INTO user_stats_total (guild_id, user_id, total_voice_time)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                total_voice_time = total_voice_time + ?
            ''', (guild_id, user_id, int(duration), int(duration)))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error ending voice session: {e}")
            return False

    def cleanup_old_data(self):
        """Удалить данные старше 30 дней"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Удаляем старые записи сообщений
            cursor.execute('''
                DELETE FROM user_messages_daily
                WHERE message_date < DATE('now', '-30 days')
            ''')

            # Удаляем старые голосовые сессии
            cursor.execute('''
                DELETE FROM user_voice_sessions
                WHERE join_time < DATETIME('now', '-30 days')
            ''')

            deleted_messages = cursor.rowcount
            conn.commit()
            conn.close()
            return deleted_messages
        except Exception as e:
            print(f"Error cleaning up old data: {e}")
            return 0

    def get_user_stats(self, guild_id: int, user_id: int, days: int = None) -> dict:
        """Получить статистику пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Общая статистика
        cursor.execute('''
            SELECT total_messages, total_voice_time FROM user_stats_total
            WHERE guild_id = ? AND user_id = ?
        ''', (guild_id, user_id))
        total_stats = cursor.fetchone()

        if not total_stats:
            conn.close()
            return None

        total_messages, total_voice_time = total_stats

        # Сообщения за период
        if days:
            cursor.execute('''
                SELECT SUM(message_count) FROM user_messages_daily
                WHERE guild_id = ? AND user_id = ?
                AND message_date >= DATE('now', '-' || ? || ' days')
            ''', (guild_id, user_id, days))
            period_messages = cursor.fetchone()[0] or 0
        else:
            period_messages = total_messages

        # Время в голосовых каналах за период
        if days:
            cursor.execute('''
                SELECT channel_id, SUM(duration) as total_duration
                FROM user_voice_sessions
                WHERE guild_id = ? AND user_id = ?
                AND join_time >= DATETIME('now', '-' || ? || ' days')
                AND duration IS NOT NULL
                GROUP BY channel_id
                ORDER BY total_duration DESC
            ''', (guild_id, user_id, days))
        else:
            cursor.execute('''
                SELECT channel_id, SUM(duration) as total_duration
                FROM user_voice_sessions
                WHERE guild_id = ? AND user_id = ?
                AND duration IS NOT NULL
                GROUP BY channel_id
                ORDER BY total_duration DESC
            ''', (guild_id, user_id))

        voice_stats = cursor.fetchall()
        conn.close()

        return {
            'total_messages': total_messages,
            'total_voice_time': total_voice_time or 0,
            'period_messages': period_messages,
            'voice_by_channel': voice_stats
        }

    def get_all_users_stats(self, guild_id: int, days: int = None) -> list:
        """Получить статистику всех пользователей сервера"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Получаем всех пользователей с общей статистикой
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
            # Сообщения за период
            if days:
                cursor.execute('''
                    SELECT SUM(message_count) FROM user_messages_daily
                    WHERE guild_id = ? AND user_id = ?
                    AND message_date >= DATE('now', '-' || ? || ' days')
                ''', (guild_id, user_id, days))
                period_messages = cursor.fetchone()[0] or 0
            else:
                period_messages = total_messages

            # Время в голосовых за период
            if days:
                cursor.execute('''
                    SELECT SUM(duration) FROM user_voice_sessions
                    WHERE guild_id = ? AND user_id = ?
                    AND join_time >= DATETIME('now', '-' || ? || ' days')
                    AND duration IS NOT NULL
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
