from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Dict, List


class WatchroomStore:
    def __init__(self, db_path: str = ""):
        self.db_path = db_path or os.path.join(os.getcwd(), "gocllm_watchrooms.db")

    def init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watch_rooms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id TEXT NOT NULL UNIQUE,
                    chatroom_title TEXT,
                    note TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def add_watch_room(self, *, room_id: str, created_by: str, note: str, chatroom_title: str) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO watch_rooms(room_id, chatroom_title, note, created_by, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(room_id) DO UPDATE SET
                    chatroom_title=excluded.chatroom_title,
                    note=excluded.note,
                    created_by=excluded.created_by
                """,
                (str(room_id), chatroom_title, note, created_by, now),
            )
            conn.commit()

    def list_rooms(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT room_id, chatroom_title, note, created_by, created_at FROM watch_rooms ORDER BY id DESC").fetchall()
        return [
            {
                "room_id": str(r[0]),
                "chatroom_title": str(r[1] or ""),
                "note": str(r[2] or ""),
                "created_by": str(r[3] or ""),
                "created_at": str(r[4] or ""),
            }
            for r in rows
        ]
