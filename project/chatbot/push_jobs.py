from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List


class PushJobManager:
    def __init__(
        self,
        *,
        watchroom_store: Any,
        issue_store: Any,
        send_text_fn: Callable[[int, str], None],
        warn_message_fn: Callable[[], str],
        issue_summary_hhmm: str = "08:00",
        warn_hhmm: str = "08:35",
    ):
        self.watchroom_store = watchroom_store
        self.issue_store = issue_store
        self.send_text_fn = send_text_fn
        self.warn_message_fn = warn_message_fn
        self.issue_summary_hhmm = issue_summary_hhmm
        self.warn_hhmm = warn_hhmm

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_run: Dict[str, str] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="push-job-manager")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _today_key(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = datetime.now().strftime("%H:%M")
            today = self._today_key()

            if now == self.issue_summary_hhmm and self._last_run.get("issue") != today:
                self.run_issue_summary_once()
                self._last_run["issue"] = today

            if now == self.warn_hhmm and self._last_run.get("warn") != today:
                self.run_warn_once()
                self._last_run["warn"] = today

            time.sleep(20)

    def _list_room_ids(self) -> List[int]:
        rooms = self.watchroom_store.list_rooms()
        out: List[int] = []
        for r in rooms:
            rid = str(r.get("room_id", "")).strip()
            if rid.isdigit():
                out.append(int(rid))
        return out

    def run_issue_summary_once(self) -> None:
        for room_id in self._list_room_ids():
            issues = self.issue_store.list_issues(scope_room_id=str(room_id), status="OPEN", limit=10)
            if not issues:
                msg = "📌 [이슈 요약] 현재 OPEN 이슈가 없습니다."
            else:
                lines = [f"📌 [이슈 요약] OPEN {len(issues)}건"]
                for it in issues[:5]:
                    lines.append(f"- #{it.get('issue_id')} {it.get('title')} (담당:{it.get('owner') or '-'})")
                msg = "\n".join(lines)
            self.send_text_fn(room_id, msg)

    def run_warn_once(self) -> None:
        msg = self.warn_message_fn()
        for room_id in self._list_room_ids():
            self.send_text_fn(room_id, msg)
