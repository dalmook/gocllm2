from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MemoryConfig:
    enabled: bool
    only_single: bool
    max_turns: int
    max_chars_per_message: int
    summarize_assistant: bool
    enable_state: bool
    db_path: str


class ConversationMemory:
    def __init__(self, cfg: MemoryConfig):
        self.cfg = cfg

    def _db_path(self) -> str:
        if self.cfg.db_path:
            return self.cfg.db_path
        return os.path.join(os.getcwd(), "gocllm_memory.db")

    def init_db(self) -> None:
        if not (self.cfg.enabled or self.cfg.enable_state):
            return
        with sqlite3.connect(self._db_path()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    room_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_memory_scope_id_id ON chat_memory(scope_id, id)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_context_state (
                    scope_id TEXT PRIMARY KEY,
                    topic TEXT,
                    time_label TEXT,
                    last_query TEXT,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                )
                """
            )
            conn.commit()

    def _enabled_for_chat(self, chat_type: str) -> bool:
        if not self.cfg.enabled:
            return False
        if self.cfg.only_single and (chat_type or "").upper() != "SINGLE":
            return False
        return True

    def _trim_content(self, role: str, content: str) -> str:
        text = re.sub(r"\s+", " ", (content or "")).strip()
        if role == "assistant" and self.cfg.summarize_assistant:
            text = text[: self.cfg.max_chars_per_message * 2]
        if len(text) <= self.cfg.max_chars_per_message:
            return text
        return text[: self.cfg.max_chars_per_message] + " ..."

    def save_message(self, *, scope_id: str, room_id: str, user_id: str, role: str, content: str, chat_type: str) -> None:
        if not self._enabled_for_chat(chat_type):
            return
        if role not in ("user", "assistant"):
            return
        trimmed = self._trim_content(role, content)
        if not trimmed:
            return
        with sqlite3.connect(self._db_path()) as conn:
            conn.execute(
                "INSERT INTO chat_memory(scope_id, room_id, user_id, role, content) VALUES (?, ?, ?, ?, ?)",
                (str(scope_id), str(room_id), str(user_id or ""), role, trimmed),
            )
            conn.execute(
                """
                DELETE FROM chat_memory
                WHERE scope_id = ? AND id NOT IN (
                    SELECT id FROM chat_memory WHERE scope_id = ? ORDER BY id DESC LIMIT ?
                )
                """,
                (str(scope_id), str(scope_id), self.cfg.max_turns),
            )
            conn.commit()

    def load_messages(self, *, scope_id: str, chat_type: str) -> List[Dict[str, str]]:
        if not self._enabled_for_chat(chat_type):
            return []
        with sqlite3.connect(self._db_path()) as conn:
            rows = conn.execute(
                "SELECT role, content FROM chat_memory WHERE scope_id = ? ORDER BY id DESC LIMIT ?",
                (str(scope_id), self.cfg.max_turns),
            ).fetchall()
        rows = list(reversed(rows))
        return [{"role": r[0], "content": r[1]} for r in rows]

    def clear(self, scope_id: str) -> None:
        if not self.cfg.enabled:
            return
        with sqlite3.connect(self._db_path()) as conn:
            conn.execute("DELETE FROM chat_memory WHERE scope_id = ?", (str(scope_id),))
            conn.commit()

    def load_state(self, scope_id: str) -> Dict[str, str]:
        if not self.cfg.enable_state:
            return {}
        with sqlite3.connect(self._db_path()) as conn:
            row = conn.execute(
                "SELECT topic, time_label, last_query FROM chat_context_state WHERE scope_id = ?",
                (str(scope_id),),
            ).fetchone()
        if not row:
            return {}
        return {
            "topic": (row[0] or "").strip(),
            "time_label": (row[1] or "").strip(),
            "last_query": (row[2] or "").strip(),
        }

    def save_state(self, scope_id: str, *, topic: str = "", time_label: str = "", last_query: str = "") -> None:
        if not self.cfg.enable_state:
            return
        with sqlite3.connect(self._db_path()) as conn:
            conn.execute(
                """
                INSERT INTO chat_context_state(scope_id, topic, time_label, last_query, updated_at)
                VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
                ON CONFLICT(scope_id) DO UPDATE SET
                    topic=excluded.topic,
                    time_label=excluded.time_label,
                    last_query=excluded.last_query,
                    updated_at=datetime('now', 'localtime')
                """,
                (str(scope_id), (topic or "").strip(), (time_label or "").strip(), (last_query or "").strip()),
            )
            conn.commit()

    def is_context_dependent_question(self, question: str) -> bool:
        q = (question or "").strip().lower()
        if not q:
            return False
        patterns = ["그거", "아까", "이전", "방금", "담당자는", "왜", "언제", "뭐야", "그게", "그건", "그 내용"]
        return any(p in q for p in patterns) or len(q) <= 8

    def _extract_topic(self, question: str) -> str:
        q = re.sub(r"\s+", " ", (question or "")).strip()
        if not q:
            return ""
        stop = {"이슈", "정리", "요약", "현황", "최근", "최신", "이번주", "지난주", "저번주", "사항", "알려줘", "해줘", "뭐야", "그거"}
        toks = [t for t in q.split() if len(t) >= 2 and t not in stop]
        if not toks:
            return ""
        for t in toks:
            if re.fullmatch(r"[A-Z0-9_\-]{2,20}", t):
                return t
        return toks[0]

    def _extract_time_label(self, question: str) -> str:
        q = re.sub(r"\s+", "", question or "")
        if any(k in q for k in ("이번주", "금주")):
            return "이번주"
        if any(k in q for k in ("지난주", "저번주", "전주")):
            return "지난주"
        if any(k in q for k in ("최근", "최신", "요즘", "근래")):
            return "최근"
        return ""

    def build_effective_question(self, *, scope_id: str, question: str) -> Tuple[str, Dict[str, str]]:
        state = self.load_state(scope_id)
        q = (question or "").strip()
        topic_now = self._extract_topic(q)
        time_now = self._extract_time_label(q)
        use_state = self.is_context_dependent_question(q) or any(x in q for x in ("그거", "저기", "그중", "방금", "아까"))
        topic_eff = topic_now or (state.get("topic", "") if use_state else "")
        time_eff = time_now or (state.get("time_label", "") if use_state else "")

        prefix_parts = []
        if topic_eff and not topic_now:
            prefix_parts.append(f"주제={topic_eff}")
        if time_eff and not time_now:
            prefix_parts.append(f"기간={time_eff}")
        effective = q if not prefix_parts else f"[{', '.join(prefix_parts)}] {q}"
        return effective, {"topic": topic_eff, "time_label": time_eff}

    def build_memory_text(self, memory_messages: List[Dict[str, str]]) -> str:
        if not memory_messages:
            return ""
        lines: List[str] = []
        total_chars = 0
        hard_limit = self.cfg.max_turns * self.cfg.max_chars_per_message
        for m in memory_messages:
            role = "사용자" if m.get("role") == "user" else "어시스턴트"
            line = f"- {role}: {(m.get('content') or '').strip()}"
            if total_chars + len(line) > hard_limit:
                break
            lines.append(line)
            total_chars += len(line)
        return "\n".join(lines)
