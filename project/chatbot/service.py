from __future__ import annotations

import json
import logging
import threading
import uuid
from typing import Any, Callable, Dict, List, Tuple

from .async_dispatch import AsyncLLMDispatcher
from .cards import (
    build_home_card,
    build_issue_edit_form_card,
    build_issue_form_card,
    build_issue_history_card,
    build_issue_list_card,
    build_query_form_card,
    build_query_list_card,
    build_query_result_card,
    build_quick_links_card,
    build_quicklink_card,
    build_watchroom_form_card,
)
from .formatters import format_for_knox_text
from .issue_store import IssueStore
from .memory import ConversationMemory
from .knox import AESCipher, KnoxMessenger
from .router import parse_action_payload
from .watchroom_store import WatchroomStore

logger = logging.getLogger("hybrid-assistant.chatbot")


DEFAULT_QUICK_LINK_ALIASES: List[Tuple[List[str], str, str]] = [
    (["GSCM"], "🧭 GSCM", "https://dsgscm.sec.samsung.net/"),
    (["NSCM", "O9"], "📦 NSCM", "https://nextscm.sec.samsung.net/Kibo2#/P-Mix%20Item/DRAM/P-Mix%20Item%20(DRAM)"),
    (["컨플", "컨플루언스", "CONF", "CONFLUENCE"], "📚 컨플루언스", "https://confluence.samsungds.net/"),
    (["파워", "파워BI", "PB", "POWERBI", "POWER BI", "BI"], "📊 Power BI", "http://10.227.100.251/Reports/browse"),
    (["DSASSISTANT", "GPT"], "🤖 DS Assistant", "https://assistant.samsungds.net/#/main"),
    (["GITHUB", "GIT", "깃허브", "깃헙"], "🧑‍💻 GitHub", "https://github.samsungds.net/SCM-Group-MEM/SCM_DO"),
]


class ChatbotService:
    def __init__(
        self,
        *,
        messenger: KnoxMessenger,
        ask_fn: Callable[..., Dict[str, Any]],
        llm_chat_default_mode: str,
        llm_group_mention_text: str,
        llm_group_prefixes: List[str],
        memory_reset_commands: List[str],
        only_single_chat: bool,
        is_allowed_user_fn: Callable[[str], bool],
        memory_store: ConversationMemory,
        async_dispatcher: AsyncLLMDispatcher | None = None,
        issue_store: IssueStore | None = None,
        watchroom_store: WatchroomStore | None = None,
        term_admin_room_ids: List[int] | None = None,
        warn_runner: Callable[[], str] | None = None,
        route_ui_to_dm_for_group: bool = True,
        query_catalog_provider: Callable[[], List[Dict[str, str]]] | None = None,
        query_meta_provider: Callable[[str], Any] | None = None,
        query_runner: Callable[[str, Dict[str, Any]], Dict[str, Any]] | None = None,
        quick_link_aliases: List[Tuple[List[str], str, str]] | None = None,
    ):
        self.messenger = messenger
        self.ask_fn = ask_fn
        self.llm_chat_default_mode = llm_chat_default_mode
        self.llm_group_mention_text = llm_group_mention_text
        self.llm_group_prefixes = llm_group_prefixes
        self.memory_reset_commands = memory_reset_commands
        self.only_single_chat = bool(only_single_chat)
        self.is_allowed_user_fn = is_allowed_user_fn
        self.memory_store = memory_store
        self.async_dispatcher = async_dispatcher
        self.issue_store = issue_store
        self.watchroom_store = watchroom_store
        self.term_admin_room_ids = term_admin_room_ids or []
        self.warn_runner = warn_runner
        self.route_ui_to_dm_for_group = bool(route_ui_to_dm_for_group)
        self.query_catalog_provider = query_catalog_provider
        self.query_meta_provider = query_meta_provider
        self.query_runner = query_runner
        self.quick_link_aliases = quick_link_aliases or DEFAULT_QUICK_LINK_ALIASES
        self._ui_room_lock = threading.Lock()
        self._ui_room_cache: Dict[str, int] = {}

    def _route_ui_room(self, *, chatroom_id: int, chat_type: str, sender_name: str, sender_knox: str) -> int:
        if not self.route_ui_to_dm_for_group:
            return int(chatroom_id)
        if (chat_type or "").upper() != "GROUP":
            return int(chatroom_id)

        cache_key = (sender_knox or sender_name or "").strip().lower()
        if not cache_key:
            return int(chatroom_id)
        with self._ui_room_lock:
            cached = self._ui_room_cache.get(cache_key)
        if cached:
            return int(cached)

        try:
            ids = self.messenger.resolve_user_ids_from_loginids([cache_key])
            if not ids:
                return int(chatroom_id)
            rid = int(self.messenger.room_create(ids, chat_type=1, chatroom_title=f"{sender_name or cache_key} 전용"))
            with self._ui_room_lock:
                self._ui_room_cache[cache_key] = rid
            return rid
        except Exception:
            return int(chatroom_id)

    def decrypt_request(self, body: bytes) -> Dict[str, Any]:
        if not self.messenger.key:
            raise RuntimeError("knox key is empty")
        dec = AESCipher(self.messenger.key).decrypt(body)
        return json.loads(dec)

    def handle_message(self, info: Dict[str, Any]) -> Dict[str, Any]:
        chatroom_id = int(info["chatroomId"])
        chat_type = (info.get("chatType") or "").upper()
        sender_knox = (info.get("senderKnoxId") or "").strip()
        sender_name = (info.get("senderName") or "").strip()
        action, payload = parse_action_payload(
            info,
            llm_chat_default_mode=self.llm_chat_default_mode,
            llm_group_mention_text=self.llm_group_mention_text,
            llm_group_prefixes=self.llm_group_prefixes,
            memory_reset_commands=self.memory_reset_commands,
            quick_link_aliases=self.quick_link_aliases,
        )

        if action == "NOOP":
            return {"ok": True}

        if action in ("INTRO", "HOME"):
            self.messenger.send_adaptive_card(chatroom_id, build_home_card())
            return {"ok": True}

        if action == "QUICK_LINKS":
            ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
            self.messenger.send_adaptive_card(ui_room, build_quick_links_card(self.quick_link_aliases))
            return {"ok": True}

        if action == "OPEN_URL":
            url = (payload.get("url") or "").strip()
            title = (payload.get("title") or "🔗 바로가기").strip()
            if not url:
                self.messenger.send_text(chatroom_id, "링크가 비어있어요.")
            else:
                self.messenger.send_adaptive_card(chatroom_id, build_quicklink_card(title, url))
            return {"ok": True}

        if action == "WARN_RUN":
            if self.warn_runner is None:
                self.messenger.send_text(chatroom_id, "워닝 기능이 아직 연결되지 않았습니다.")
            else:
                self.messenger.send_text(chatroom_id, self.warn_runner())
            return {"ok": True}

        if action == "QUERY_LIST":
            if self.query_catalog_provider is None:
                self.messenger.send_text(chatroom_id, "Query 기능이 비활성화되어 있습니다.")
                return {"ok": True}
            ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
            catalog = self.query_catalog_provider() or []
            self.messenger.send_adaptive_card(ui_room, build_query_list_card(catalog))
            return {"ok": True}

        if action == "QUERY_FORM":
            if self.query_meta_provider is None:
                self.messenger.send_text(chatroom_id, "Query 기능이 비활성화되어 있습니다.")
                return {"ok": True}
            qid = str(payload.get("query_id") or "").strip()
            if not qid:
                self.messenger.send_text(chatroom_id, "query_id가 없습니다. (/query [id])")
                return {"ok": True}
            qdef = self.query_meta_provider(qid)
            if not qdef:
                self.messenger.send_text(chatroom_id, f"알 수 없는 query_id: {qid}")
                return {"ok": True}
            ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
            self.messenger.send_adaptive_card(
                ui_room,
                build_query_form_card(query_id=qid, description=str(getattr(qdef, "description", "")), params=dict(getattr(qdef, "params", {}) or {})),
            )
            return {"ok": True}

        if action == "QUERY_RUN":
            if self.query_runner is None or self.query_meta_provider is None:
                self.messenger.send_text(chatroom_id, "Query 기능이 비활성화되어 있습니다.")
                return {"ok": True}
            qid = str(payload.get("query_id") or "").strip()
            if not qid:
                self.messenger.send_text(chatroom_id, "query_id가 없습니다.")
                return {"ok": True}
            qdef = self.query_meta_provider(qid)
            if not qdef:
                self.messenger.send_text(chatroom_id, f"알 수 없는 query_id: {qid}")
                return {"ok": True}
            params = {}
            for k in dict(getattr(qdef, "params", {}) or {}).keys():
                v = payload.get(k)
                if v not in (None, ""):
                    params[k] = v
            try:
                out = self.query_runner(qid, params)
            except Exception as e:
                self.messenger.send_text(chatroom_id, f"쿼리 실행 실패: {e}")
                ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
                self.messenger.send_adaptive_card(
                    ui_room,
                    build_query_form_card(query_id=qid, description=str(getattr(qdef, "description", "")), params=dict(getattr(qdef, "params", {}) or {})),
                )
                return {"ok": True}

            mode = str(out.get("mode") or "table")
            ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
            if mode == "scalar":
                self.messenger.send_adaptive_card(
                    ui_room,
                    build_query_result_card(title=f"{qid} 결과", rows=[], value=out.get("value"), mode="scalar"),
                )
            else:
                self.messenger.send_adaptive_card(
                    ui_room,
                    build_query_result_card(title=f"{qid} 결과", rows=list(out.get("rows") or []), mode="table"),
                )
            return {"ok": True}

        if action == "TERM_UNKNOWN_SUBMIT":
            ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
            sender = (sender_name or sender_knox or "").strip()
            findword = (payload.get("findword") or "").strip()
            memo = (payload.get("memo") or "").strip()
            msg = f"📩 [용어 반영 요청]\n- 단어: {findword}\n- 요청자: {sender}\n" + (f"- 메모: {memo}\n" if memo else "")
            if self.term_admin_room_ids:
                for rid in self.term_admin_room_ids:
                    self.messenger.send_text(int(rid), msg)
                self.messenger.send_text(ui_room, "접수 완료 ✅ (담당자에게 전달했습니다)")
            else:
                self.messenger.send_text(ui_room, "접수 완료 ✅ (TERM_ADMIN_ROOM_IDS 미설정이라 전달은 생략됨)")
            return {"ok": True}

        if action == "ISSUE_FORM":
            scope = str(payload.get("room_id") or chatroom_id)
            ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
            self.messenger.send_adaptive_card(ui_room, build_issue_form_card(room_id=scope, sender_hint=(sender_name or sender_knox or "")))
            return {"ok": True}

        if action == "ISSUE_LIST":
            if self.issue_store is None:
                self.messenger.send_text(chatroom_id, "Issue 기능이 비활성화되어 있습니다.")
                return {"ok": True}
            scope = str(payload.get("room_id") or chatroom_id)
            ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
            issues = self.issue_store.list_issues(scope_room_id=scope, status="OPEN", limit=30)
            self.messenger.send_adaptive_card(ui_room, build_issue_list_card(issues, room_id=scope))
            return {"ok": True}

        if action == "ISSUE_CREATE":
            if self.issue_store is None:
                self.messenger.send_text(chatroom_id, "Issue 기능이 비활성화되어 있습니다.")
                return {"ok": True}
            ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
            title = (payload.get("title") or "").strip()
            if not title:
                self.messenger.send_text(ui_room, "제목이 비어있습니다. 다시 입력해주세요.")
                self.messenger.send_adaptive_card(ui_room, build_issue_form_card(room_id=str(payload.get("room_id") or chatroom_id), sender_hint=(sender_name or sender_knox or "")))
                return {"ok": True}
            issue_id = self.issue_store.create_issue(
                scope_room_id=str(payload.get("room_id") or chatroom_id),
                title=title,
                content=(payload.get("content") or "").strip(),
                url=(payload.get("url") or "").strip(),
                owner=(payload.get("owner") or "").strip(),
                target_date=(payload.get("target_date") or "").strip(),
                created_by=(sender_name or sender_knox or ""),
            )
            self.messenger.send_text(ui_room, f"✅ 이슈 등록 완료: #{issue_id} {title}")
            issues = self.issue_store.list_issues(scope_room_id=str(payload.get("room_id") or chatroom_id), status="OPEN", limit=30)
            self.messenger.send_adaptive_card(ui_room, build_issue_list_card(issues, room_id=str(payload.get("room_id") or chatroom_id)))
            return {"ok": True}

        if action == "ISSUE_CLEAR":
            if self.issue_store is None:
                self.messenger.send_text(chatroom_id, "Issue 기능이 비활성화되어 있습니다.")
                return {"ok": True}
            ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
            issue_id = int(payload.get("issue_id") or 0)
            if issue_id <= 0:
                self.messenger.send_text(ui_room, "issue_id가 없습니다.")
                return {"ok": True}
            ok = self.issue_store.clear_issue(issue_id=issue_id, actor=(sender_name or sender_knox or ""))
            if ok:
                self.messenger.send_text(ui_room, f"✅ Clear 처리 완료: #{issue_id}")
            else:
                self.messenger.send_text(ui_room, f"해당 OPEN 이슈를 찾지 못했습니다: #{issue_id}")
            issues = self.issue_store.list_issues(scope_room_id=str(payload.get("room_id") or chatroom_id), status="OPEN", limit=30)
            self.messenger.send_adaptive_card(ui_room, build_issue_list_card(issues, room_id=str(payload.get("room_id") or chatroom_id)))
            return {"ok": True}

        if action == "ISSUE_EDIT_FORM":
            if self.issue_store is None:
                self.messenger.send_text(chatroom_id, "Issue 기능이 비활성화되어 있습니다.")
                return {"ok": True}
            ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
            issue_id = int(payload.get("issue_id") or 0)
            if issue_id <= 0:
                self.messenger.send_text(ui_room, "issue_id가 없습니다.")
                return {"ok": True}
            issue = self.issue_store.get_issue(issue_id)
            if not issue:
                self.messenger.send_text(ui_room, f"해당 이슈를 찾을 수 없습니다: #{issue_id}")
                return {"ok": True}
            self.messenger.send_adaptive_card(ui_room, build_issue_edit_form_card(issue, room_id=str(payload.get("room_id") or chatroom_id)))
            return {"ok": True}

        if action == "ISSUE_EDIT_SAVE":
            if self.issue_store is None:
                self.messenger.send_text(chatroom_id, "Issue 기능이 비활성화되어 있습니다.")
                return {"ok": True}
            ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
            issue_id = int(payload.get("issue_id") or 0)
            if issue_id <= 0:
                self.messenger.send_text(ui_room, "issue_id가 없습니다.")
                return {"ok": True}
            title = (payload.get("title") or "").strip()
            if not title:
                self.messenger.send_text(ui_room, "제목이 비어있습니다.")
                return {"ok": True}
            ok = self.issue_store.update_issue(
                issue_id=issue_id,
                title=title,
                content=(payload.get("content") or "").strip(),
                url=(payload.get("url") or "").strip(),
                owner=(payload.get("owner") or "").strip(),
                target_date=(payload.get("target_date") or "").strip(),
                actor=(sender_name or sender_knox or ""),
            )
            if ok:
                self.messenger.send_text(ui_room, f"✅ 수정 완료: #{issue_id} {title}")
            else:
                self.messenger.send_text(ui_room, f"수정 실패: #{issue_id}")
            issues = self.issue_store.list_issues(scope_room_id=str(payload.get("room_id") or chatroom_id), status="OPEN", limit=30)
            self.messenger.send_adaptive_card(ui_room, build_issue_list_card(issues, room_id=str(payload.get("room_id") or chatroom_id)))
            return {"ok": True}

        if action == "ISSUE_UPDATE":
            payload = dict(payload or {})
            payload["action"] = "ISSUE_EDIT_SAVE"
            return self.handle_message({**info, "chatMsg": json.dumps(payload, ensure_ascii=False)})

        if action == "ISSUE_HISTORY":
            if self.issue_store is None:
                self.messenger.send_text(chatroom_id, "Issue 기능이 비활성화되어 있습니다.")
                return {"ok": True}
            ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
            issue_id = int(payload.get("issue_id") or 0)
            if issue_id <= 0:
                self.messenger.send_text(ui_room, "issue_id가 없습니다.")
                return {"ok": True}
            events = self.issue_store.list_events(issue_id=issue_id, limit=20)
            self.messenger.send_adaptive_card(ui_room, build_issue_history_card(events, issue_id=issue_id, room_id=str(payload.get("room_id") or chatroom_id)))
            return {"ok": True}

        if action == "ISSUE_DELETE":
            if self.issue_store is None:
                self.messenger.send_text(chatroom_id, "Issue 기능이 비활성화되어 있습니다.")
                return {"ok": True}
            ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
            issue_id = int(payload.get("issue_id") or 0)
            if issue_id <= 0:
                self.messenger.send_text(ui_room, "issue_id가 없습니다.")
                return {"ok": True}
            ok = self.issue_store.delete_issue(issue_id=issue_id, actor=(sender_name or sender_knox or ""))
            if not ok:
                self.messenger.send_text(ui_room, f"해당 이슈를 찾을 수 없습니다: #{issue_id}")
            events = self.issue_store.list_events(issue_id=issue_id, limit=20)
            self.messenger.send_adaptive_card(ui_room, build_issue_history_card(events, issue_id=issue_id, room_id=str(payload.get("room_id") or chatroom_id)))
            return {"ok": True}

        if action == "WATCHROOM_FORM":
            ui_room = self._route_ui_room(chatroom_id=chatroom_id, chat_type=chat_type, sender_name=sender_name, sender_knox=sender_knox)
            self.messenger.send_adaptive_card(ui_room, build_watchroom_form_card())
            return {"ok": True}

        if action == "WATCHROOM_CREATE":
            room_title = (payload.get("room_title") or "").strip()
            members_raw = (payload.get("members") or "").strip()
            note = (payload.get("note") or "").strip()
            if not members_raw:
                self.messenger.send_text(chatroom_id, "참여자 SSO가 비어있습니다. 예: sungmook.cho,cc.choi")
                self.messenger.send_adaptive_card(chatroom_id, build_watchroom_form_card())
                return {"ok": True}
            members = [x.strip() for x in members_raw.replace("\n", ",").split(",") if x.strip()]
            user_ids = self.messenger.resolve_user_ids_from_loginids(members)
            if not user_ids:
                self.messenger.send_text(chatroom_id, "참여자 변환(userID)이 실패했습니다. SSO가 맞는지 확인해 주세요.")
                return {"ok": True}
            title_to_use = room_title or note or "공지방"
            new_room_id = self.messenger.room_create(user_ids, chat_type=1, chatroom_title=title_to_use)
            if self.watchroom_store is not None:
                self.watchroom_store.add_watch_room(
                    room_id=str(new_room_id),
                    created_by=(info.get("senderName") or sender_knox or ""),
                    note=note,
                    chatroom_title=title_to_use,
                )
            self.messenger.send_text(chatroom_id, f"✅ 공지방 생성 & 푸시대상 등록 완료\n- chatroomId: {new_room_id}\n- title: {title_to_use}\n- note: {note}")
            self.messenger.send_text(new_room_id, "📣 이 방은 봇이 생성한 공지/워닝/이슈 방입니다.")
            self.messenger.send_adaptive_card(new_room_id, build_home_card())
            return {"ok": True}

        if action == "LLM_CHAT":
            if self.only_single_chat and chat_type != "SINGLE":
                return {"ok": True}
            if not self.is_allowed_user_fn(sender_knox):
                self.messenger.send_text(chatroom_id, "권한이 없는 사용자입니다.")
                return {"ok": True}

            question = (payload.get("question") or "").strip()
            if not question:
                self.messenger.send_text(chatroom_id, "질문 내용이 비어있습니다. /ask 질문내용 또는 질문:내용 형식으로 입력해주세요.")
                return {"ok": True}
            if question in self.memory_reset_commands:
                self.memory_store.clear(str(chatroom_id))
                self.messenger.send_text(chatroom_id, "🧹 해당 1:1 대화 메모리를 초기화했습니다.")
                return {"ok": True}

            scope_id = str(chatroom_id)
            self.memory_store.save_message(
                scope_id=scope_id,
                room_id=str(chatroom_id),
                user_id=sender_knox,
                role="user",
                content=question,
                chat_type=chat_type,
            )
            memory_messages = self.memory_store.load_messages(scope_id=scope_id, chat_type=chat_type)
            memory_text = self.memory_store.build_memory_text(memory_messages)
            effective_question, state = self.memory_store.build_effective_question(scope_id=scope_id, question=question)

            if self.async_dispatcher is not None:
                req_id = str(uuid.uuid4())
                think_resp = self.messenger.send_text(chatroom_id, "🤔 검색 중입니다. 잠시만 기다려주세요...")
                self.async_dispatcher.register_notice(req_id, think_resp)
                job = {
                    "request_id": req_id,
                    "chatroom_id": chatroom_id,
                    "scope_id": scope_id,
                    "sender_knox": sender_knox,
                    "sender_name": info.get("senderName", "") or "",
                    "chat_type": chat_type,
                    "memory_text": memory_text,
                    "effective_question": effective_question,
                    "state": state,
                }
                if not self.async_dispatcher.enqueue(job):
                    self.messenger.send_text(chatroom_id, self.async_dispatcher.queue_full_message)
                return {"ok": True}

            try:
                self.messenger.send_text(chatroom_id, "🤔 검색 중입니다. 잠시만 기다려주세요...")
                result = self.ask_fn(effective_question, memory_text=memory_text)
                answer = str(result.get("answer") or "답변을 생성하지 못했습니다.")
                self.memory_store.save_message(
                    scope_id=scope_id,
                    room_id=str(chatroom_id),
                    user_id="assistant",
                    role="assistant",
                    content=answer,
                    chat_type=chat_type,
                )
                self.memory_store.save_state(
                    scope_id=scope_id,
                    topic=state.get("topic", ""),
                    time_label=state.get("time_label", ""),
                    last_query=effective_question,
                )
                self.messenger.send_text(chatroom_id, f"🤖 {format_for_knox_text(answer)}")
                return {"ok": True, "intent": result.get("intent"), "request_id": result.get("request_id")}
            except Exception as e:
                logger.exception("chatbot ask failed")
                self.messenger.send_text(chatroom_id, f"LLM 요청 처리 오류: {e}")
                return {"ok": False, "error": str(e)}

        self.messenger.send_adaptive_card(chatroom_id, build_home_card())
        return {"ok": True}
