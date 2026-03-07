from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional


class IssueStore:
    def __init__(self, db_path: str = ""):
        self.db_path = db_path or os.path.join(os.getcwd(), "gocllm_issues.db")

    def init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS issues (
                    issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_room_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    title TEXT NOT NULL,
                    content TEXT,
                    url TEXT,
                    owner TEXT,
                    target_date TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    closed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS issue_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    issue_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT,
                    memo TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def create_issue(
        self,
        *,
        scope_room_id: str,
        title: str,
        content: str,
        url: str,
        owner: str,
        target_date: str,
        created_by: str,
    ) -> int:
        now = self._now()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO issues(scope_room_id, status, title, content, url, owner, target_date, created_by, created_at, updated_at)
                VALUES (?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(scope_room_id), title, content, url, owner, target_date, created_by, now, now),
            )
            issue_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO issue_events(issue_id, action, actor, memo, created_at) VALUES (?, 'CREATE', ?, ?, ?)",
                (issue_id, created_by, title, now),
            )
            conn.commit()
            return issue_id

    def list_issues(self, *, scope_room_id: str, status: str = "OPEN", limit: int = 50) -> List[Dict]:
        q = "SELECT issue_id, scope_room_id, status, title, content, url, owner, target_date, created_by, created_at, updated_at, closed_at FROM issues WHERE scope_room_id = ?"
        args: list = [str(scope_room_id)]
        if status and status != "ALL":
            q += " AND status = ?"
            args.append(status)
        q += " ORDER BY issue_id DESC LIMIT ?"
        args.append(int(limit))
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(q, args).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "issue_id": int(r[0]),
                    "scope_room_id": str(r[1]),
                    "status": str(r[2]),
                    "title": str(r[3] or ""),
                    "content": str(r[4] or ""),
                    "url": str(r[5] or ""),
                    "owner": str(r[6] or ""),
                    "target_date": str(r[7] or ""),
                    "created_by": str(r[8] or ""),
                    "created_at": str(r[9] or ""),
                    "updated_at": str(r[10] or ""),
                    "closed_at": str(r[11] or ""),
                }
            )
        return out

    def get_issue(self, issue_id: int) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            r = conn.execute(
                "SELECT issue_id, scope_room_id, status, title, content, url, owner, target_date, created_by, created_at, updated_at, closed_at FROM issues WHERE issue_id = ?",
                (int(issue_id),),
            ).fetchone()
        if not r:
            return None
        return {
            "issue_id": int(r[0]),
            "scope_room_id": str(r[1]),
            "status": str(r[2]),
            "title": str(r[3] or ""),
            "content": str(r[4] or ""),
            "url": str(r[5] or ""),
            "owner": str(r[6] or ""),
            "target_date": str(r[7] or ""),
            "created_by": str(r[8] or ""),
            "created_at": str(r[9] or ""),
            "updated_at": str(r[10] or ""),
            "closed_at": str(r[11] or ""),
        }

    def clear_issue(self, *, issue_id: int, actor: str) -> bool:
        now = self._now()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE issues SET status='CLOSED', closed_at=?, updated_at=? WHERE issue_id=? AND status='OPEN'",
                (now, now, int(issue_id)),
            )
            if cur.rowcount <= 0:
                return False
            conn.execute(
                "INSERT INTO issue_events(issue_id, action, actor, memo, created_at) VALUES (?, 'CLEAR', ?, '', ?)",
                (int(issue_id), actor, now),
            )
            conn.commit()
            return True

    def update_issue(self, *, issue_id: int, title: str, content: str, url: str, owner: str, target_date: str, actor: str) -> bool:
        now = self._now()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE issues
                SET title=?, content=?, url=?, owner=?, target_date=?, updated_at=?
                WHERE issue_id=?
                """,
                (title, content, url, owner, target_date, now, int(issue_id)),
            )
            if cur.rowcount <= 0:
                return False
            conn.execute(
                "INSERT INTO issue_events(issue_id, action, actor, memo, created_at) VALUES (?, 'EDIT', ?, ?, ?)",
                (int(issue_id), actor, title, now),
            )
            conn.commit()
            return True

    def list_events(self, *, issue_id: int, limit: int = 20) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT action, actor, memo, created_at FROM issue_events WHERE issue_id=? ORDER BY id DESC LIMIT ?",
                (int(issue_id), int(limit)),
            ).fetchall()
        return [
            {"action": str(r[0]), "actor": str(r[1] or ""), "memo": str(r[2] or ""), "created_at": str(r[3] or "")}
            for r in rows
        ]
