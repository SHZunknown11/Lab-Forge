import sqlite3
import json
import datetime
from pathlib import Path
from typing import List, Dict, Any

class RequestLogger:
    def __init__(self, db_path: str = "logs.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    request_data TEXT
                )
            """)
            conn.commit()

    def log_request(self, user_id: str, endpoint: str, status: str, error_message: str = None, request_data: dict = None):
        if not user_id:
            return
            
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        req_data_str = json.dumps(request_data) if request_data else None

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Insert the new log
            cursor.execute("""
                INSERT INTO requests (user_id, timestamp, endpoint, status, error_message, request_data)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, timestamp, endpoint, status, error_message, req_data_str))
            
            # Enforce 50 logs per user
            # Delete any rows for this user that are not in the latest 50
            cursor.execute("""
                DELETE FROM requests
                WHERE id IN (
                    SELECT id FROM requests
                    WHERE user_id = ?
                    ORDER BY timestamp DESC
                    LIMIT -1 OFFSET 50
                )
            """, (user_id,))
            conn.commit()

    def get_logs(self, user_id: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, endpoint, status, error_message, request_data
                FROM requests
                WHERE user_id = ?
                ORDER BY timestamp DESC
            """, (user_id,))
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                item = dict(row)
                if item["request_data"]:
                    try:
                        item["request_data"] = json.loads(item["request_data"])
                    except:
                        pass
                result.append(item)
            return result
