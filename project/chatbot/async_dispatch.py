from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Dict

from .formatters import format_for_knox_text

logger = logging.getLogger("hybrid-assistant.chatbot.async")


class AsyncLLMDispatcher:
    def __init__(
        self,
        *,
        ask_fn: Callable[..., Dict[str, Any]],
        messenger: Any,
        memory_store: Any,
        workers: int,
        queue_max: int,
        max_concurrent: int,
        busy_message: str,
        queue_full_message: str,
        long_wait_delay_sec: float = 6.0,
        enable_recall: bool = False,
    ):
        self.ask_fn = ask_fn
        self.messenger = messenger
        self.memory_store = memory_store
        self.busy_message = busy_message
        self.queue_full_message = queue_full_message
        self.long_wait_delay_sec = max(1.0, float(long_wait_delay_sec))
        self.enable_recall = bool(enable_recall)

        self._queue: "queue.Queue[dict]" = queue.Queue(maxsize=max(1, queue_max))
        self._sem = threading.Semaphore(max(1, max_concurrent))
        self._inflight_lock = threading.Lock()
        self._inflight: Dict[str, bool] = {}
        self._state_lock = threading.Lock()
        self._state: Dict[str, str] = {}
        self._workers = max(1, workers)
        self._started = False
        self._start_lock = threading.Lock()
        self._notice_lock = threading.Lock()
        self._notices: Dict[str, list[tuple[int, int]]] = {}

    def start_workers(self) -> None:
        if self._started:
            return
        with self._start_lock:
            if self._started:
                return
            for i in range(self._workers):
                threading.Thread(
                    target=self._worker_loop,
                    args=(f"llm-worker-{i + 1}",),
                    daemon=True,
                    name=f"llm-worker-{i + 1}",
                ).start()
            self._started = True

    def _user_key(self, task: Dict[str, Any]) -> str:
        return (
            (task.get("sender_knox") or "").strip()
            or (task.get("sender_name") or "").strip()
            or str(task.get("chatroom_id"))
        )

    def enqueue(self, task: Dict[str, Any]) -> bool:
        try:
            self._queue.put_nowait(task)
            req_id = str(task.get("request_id") or "")
            if req_id:
                with self._state_lock:
                    self._state[req_id] = "queued"
            self._schedule_long_wait_notice(task)
            return True
        except queue.Full:
            return False

    def _extract_msgid_senttime(self, resp: dict) -> tuple[int | None, int | None]:
        if not isinstance(resp, dict):
            return None, None
        pme = resp.get("processedMessageEntries")
        if isinstance(pme, list) and pme:
            x = pme[0] or {}
            mid = x.get("msgId")
            st = x.get("sentTime")
            if mid is not None and st is not None:
                return int(mid), int(st)
        for k in ("chatReplyResultList", "chatReplyResults", "resultList", "data", "results"):
            v = resp.get(k)
            if isinstance(v, list) and v:
                x = v[0] or {}
                mid = x.get("msgId") or x.get("messageId") or x.get("msgID")
                st = x.get("sentTime") or x.get("sendTime") or x.get("sent_time")
                if mid is not None and st is not None:
                    return int(mid), int(st)
        mid = resp.get("msgId") or resp.get("messageId") or resp.get("msgID")
        st = resp.get("sentTime") or resp.get("sendTime") or resp.get("sent_time")
        if mid is not None and st is not None:
            return int(mid), int(st)
        return None, None

    def register_notice(self, req_id: str, resp: Any) -> None:
        if not self.enable_recall or not req_id:
            return
        try:
            mid, st = self._extract_msgid_senttime(resp if isinstance(resp, dict) else {})
            if mid is None or st is None:
                return
            with self._notice_lock:
                self._notices.setdefault(req_id, []).append((int(mid), int(st)))
        except Exception:
            return

    def _recall_notices(self, chatroom_id: int, req_id: str) -> None:
        if not self.enable_recall or not req_id:
            return
        with self._notice_lock:
            notices = self._notices.pop(req_id, [])
        for mid, st in notices:
            try:
                self.messenger.recall_message(chatroom_id, int(mid), int(st))
            except Exception:
                pass

    def _schedule_long_wait_notice(self, task: Dict[str, Any]) -> None:
        req_id = str(task.get("request_id") or "")
        chatroom_id = task.get("chatroom_id")
        if not req_id or not chatroom_id:
            return

        def _notify_if_still_running() -> None:
            try:
                time.sleep(self.long_wait_delay_sec)
                with self._state_lock:
                    state = self._state.get(req_id)
                if state in ("queued", "running"):
                    resp = self.messenger.send_text(int(chatroom_id), "⏳ 아직 분석 중입니다. 문서 확인 후 정리해서 보내드리겠습니다.")
                    self.register_notice(req_id, resp)
            except Exception as e:
                logger.warning("long wait notice failed req_id=%s err=%s", req_id, e)

        threading.Thread(target=_notify_if_still_running, daemon=True).start()

    def _worker_loop(self, worker_name: str) -> None:
        while True:
            task = self._queue.get()
            req_id = str(task.get("request_id") or "")
            user_key = self._user_key(task)
            chatroom_id = int(task.get("chatroom_id"))

            with self._inflight_lock:
                if self._inflight.get(user_key):
                    try:
                        self.messenger.send_text(chatroom_id, self.busy_message)
                    except Exception:
                        pass
                    if req_id:
                        with self._state_lock:
                            self._state[req_id] = "done"
                    self._queue.task_done()
                    continue
                self._inflight[user_key] = True

            if req_id:
                with self._state_lock:
                    self._state[req_id] = "running"

            try:
                with self._sem:
                    result = self.ask_fn(task.get("effective_question", ""), memory_text=task.get("memory_text", ""))

                answer = str(result.get("answer") or "답변을 생성하지 못했습니다.")
                self.memory_store.save_message(
                    scope_id=str(task.get("scope_id")),
                    room_id=str(chatroom_id),
                    user_id="assistant",
                    role="assistant",
                    content=answer,
                    chat_type=str(task.get("chat_type") or ""),
                )
                st = task.get("state") or {}
                self.memory_store.save_state(
                    scope_id=str(task.get("scope_id")),
                    topic=st.get("topic", ""),
                    time_label=st.get("time_label", ""),
                    last_query=str(task.get("effective_question") or ""),
                )
                self.messenger.send_text(chatroom_id, f"🤖 {format_for_knox_text(answer)}")
            except Exception as e:
                logger.exception("[%s][%s] async ask failed", worker_name, req_id)
                try:
                    self.messenger.send_text(chatroom_id, f"LLM 요청 처리 오류: {e}")
                except Exception:
                    pass
                if req_id:
                    with self._state_lock:
                        self._state[req_id] = "failed"
            finally:
                if req_id:
                    with self._state_lock:
                        if self._state.get(req_id) != "failed":
                            self._state[req_id] = "done"
                    self._recall_notices(chatroom_id, req_id)
                with self._inflight_lock:
                    self._inflight[user_key] = False
                self._queue.task_done()
