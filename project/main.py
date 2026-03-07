from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .chatbot.access import AllowlistService
from .chatbot.async_dispatch import AsyncLLMDispatcher
from .chatbot.issue_store import IssueStore
from .chatbot.memory import ConversationMemory, MemoryConfig
from .chatbot.push_jobs import PushJobManager
from .chatbot.service import ChatbotService
from .chatbot.watchroom_store import WatchroomStore
from .chatbot.knox import KnoxMessenger
from .settings import settings
from .llm_client import LLMClient
from .planner import Planner, Step
from .executor import Executor, PlanExecutionError
from .synthesizer import Synthesizer
from .query_registry.registry import QueryRegistry


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("hybrid-assistant")

app = FastAPI(title=settings.app_name)

registry = QueryRegistry()
registry.load_from_dir(settings.query_dir)
llm = LLMClient()
planner = Planner(llm, tz=settings.timezone)
executor = Executor(registry)
synthesizer = Synthesizer(llm)
chatbot_service: Optional[ChatbotService] = None
allowlist_service = AllowlistService()
async_dispatcher: Optional[AsyncLLMDispatcher] = None
push_job_manager: Optional[PushJobManager] = None
issue_store = IssueStore(db_path=settings.issue_db_path)
watchroom_store = WatchroomStore(db_path=settings.watchroom_db_path)
memory_store = ConversationMemory(
    MemoryConfig(
        enabled=settings.enable_conversation_memory,
        only_single=settings.memory_only_single,
        max_turns=max(1, settings.memory_max_turns),
        max_chars_per_message=max(50, settings.memory_max_chars_per_message),
        summarize_assistant=settings.memory_summarize_assistant,
        enable_state=settings.enable_conversation_state,
        db_path=settings.memory_db_path,
    )
)


def _ask_core(question: str, *, memory_text: str = "") -> Dict[str, Any]:
    request_id = str(uuid.uuid4())
    question = question.strip()

    try:
        plan = planner.make_plan(question, registry.list_for_planner())
    except Exception as e:
        logger.exception("request_id=%s planner_failed", request_id)
        if llm.enabled:
            answer = llm.invoke_text(
                "당신은 짧고 명확하게 답변하는 비서입니다.",
                f"최근 대화: {memory_text}\n질문: {question}\n가능한 범위에서 답변하세요.",
            )
            return {
                "request_id": request_id,
                "intent": "rag_only",
                "answer": answer,
                "plan": {"intent": "rag_only", "steps": []},
                "evidence": {"rag": [], "data": []},
                "logs": [{"step_id": "planner", "tool": "planner", "status": "error", "error": str(e)}],
            }
        raise HTTPException(status_code=400, detail=f"Planner error: {e}")

    if not plan.steps or plan.steps[-1].tool != "answer.compose":
        data_from = [s.id for s in plan.steps if s.tool == "db.query"]
        rag_steps = [s.id for s in plan.steps if s.tool == "rag.search"]
        compose_args: Dict[str, Any] = {"question": question, "data_from": data_from}
        if rag_steps:
            compose_args["rag_from"] = rag_steps[-1]
        plan.steps.append(Step(id=f"s{len(plan.steps)+1}", tool="answer.compose", args=compose_args))

    try:
        ran = executor.run(plan, question, continue_on_error=True)
    except PlanExecutionError as e:
        logger.warning("request_id=%s executor_failed=%s", request_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        logger.warning("request_id=%s validation_failed=%s", request_id, e)
        if llm.enabled:
            answer = llm.invoke_text(
                "당신은 짧고 명확하게 답변하는 비서입니다.",
                f"최근 대화: {memory_text}\n질문: {question}\nDB 조회가 실패해도 가능한 범위에서 답변하세요.",
            )
            return {
                "request_id": request_id,
                "intent": plan.intent,
                "answer": answer,
                "plan": plan.model_dump(),
                "evidence": {"rag": [], "data": []},
                "logs": [{"step_id": "executor", "tool": "executor", "status": "error", "error": str(e)}],
            }
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("request_id=%s executor_unknown_failed", request_id)
        raise HTTPException(status_code=500, detail=f"Executor error: {e}")

    compose_step = plan.steps[-1]
    answer = synthesizer.compose(question, ran["ctx"], compose_step.args)

    rag_evidence = []
    data_evidence = []
    for st in plan.steps:
        out = ran["ctx"].get(st.id)
        if st.tool == "rag.search":
            rag_evidence = out if isinstance(out, list) else []
        if st.tool == "db.query":
            data_evidence.append(out)

    logger.info(
        "request_id=%s intent=%s steps=%s",
        request_id,
        plan.intent,
        ran["step_logs"],
    )

    return {
        "request_id": request_id,
        "intent": plan.intent,
        "answer": answer,
        "plan": plan.model_dump(),
        "evidence": {
            "rag": rag_evidence,
            "data": data_evidence,
        },
        "logs": ran["step_logs"],
    }


def _run_warn_once_message() -> str:
    qid = (settings.warn_query_id or "").strip()
    if not qid:
        return "WARN_QUERY_ID 미설정입니다."
    if not registry.get(qid):
        return f"WARN_QUERY_ID를 찾을 수 없습니다: {qid}"
    try:
        out = executor.db.query(qid, {})
    except Exception as e:
        return f"워닝 조회 실패: {e}"
    rowcount = int(out.get("rowcount") or 0) if isinstance(out, dict) else 0
    if rowcount <= 0:
        return "워닝 조건: 현재 0건 ✅"
    return f"⚠️ 워닝 결과: {rowcount}건"


class AskRequest(BaseModel):
    question: str


def _require_dashboard_token(token: Optional[str]) -> None:
    if settings.dashboard_token and (token or "") != settings.dashboard_token:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/health")
def health():
    return {"ok": True, "queries": len(registry.list_for_planner())}


@app.post("/ask")
def ask(req: AskRequest) -> Dict[str, Any]:
    return _ask_core(req.question)


@app.get("/api/watchrooms")
def api_watchrooms(token: Optional[str] = None) -> Dict[str, Any]:
    _require_dashboard_token(token)
    return {"items": watchroom_store.list_rooms()}


@app.get("/api/dashboard/issues")
def api_dashboard_issues(
    token: Optional[str] = None,
    room_id: str = "",
    status: str = "OPEN",
    owner: str = "",
    q: str = "",
    page: int = 0,
    size: int = 50,
) -> Dict[str, Any]:
    _require_dashboard_token(token)

    def _dday(s: str) -> Optional[int]:
        t = (s or "").strip()
        if not t:
            return None
        try:
            return (datetime.strptime(t, "%Y-%m-%d").date() - datetime.now().date()).days
        except Exception:
            return None

    def _age_days(s: str) -> int:
        t = (s or "").strip()
        if not t:
            return 0
        try:
            d = datetime.strptime(t[:10], "%Y-%m-%d").date()
            return max(0, (datetime.now().date() - d).days)
        except Exception:
            return 0

    if room_id:
        items = issue_store.list_issues(scope_room_id=room_id, status=status, limit=max(1000, size * (page + 1)))
    else:
        items = []
        for r in watchroom_store.list_rooms():
            rid = str(r.get("room_id", ""))
            if not rid:
                continue
            items.extend(issue_store.list_issues(scope_room_id=rid, status=status, limit=1000))

    if owner:
        owner_l = owner.lower()
        items = [x for x in items if owner_l in str(x.get("owner", "")).lower()]
    if q:
        q_l = q.lower()
        items = [
            x
            for x in items
            if q_l in str(x.get("title", "")).lower() or q_l in str(x.get("content", "")).lower()
        ]

    for x in items:
        x["d_day"] = _dday(str(x.get("target_date") or ""))
        x["age_days"] = _age_days(str(x.get("created_at") or ""))

    if status == "OPEN":
        items.sort(key=lambda x: (999999 if x.get("d_day") is None else int(x.get("d_day")), -int(x.get("age_days") or 0), int(x.get("issue_id") or 0)))
    all_items = []
    if status != "OPEN":
        items.sort(key=lambda x: int(x.get("issue_id") or 0), reverse=True)
    total = len(items)
    start = max(0, int(page)) * max(1, int(size))
    end = start + max(1, int(size))
    all_items = items[start:end]
    return {"items": all_items, "total": total, "page": int(page), "size": int(size)}


@app.get("/api/dashboard/summary")
def api_dashboard_summary(token: Optional[str] = None) -> Dict[str, Any]:
    _require_dashboard_token(token)
    open_items = []
    for r in watchroom_store.list_rooms():
        rid = str(r.get("room_id", ""))
        if rid:
            open_items.extend(issue_store.list_issues(scope_room_id=rid, status="OPEN", limit=1000))

    overdue = 0
    due_7 = 0
    for it in open_items:
        t = str(it.get("target_date") or "")
        try:
            dday = (datetime.strptime(t, "%Y-%m-%d").date() - datetime.now().date()).days if t else None
        except Exception:
            dday = None
        if dday is not None:
            if dday < 0:
                overdue += 1
            if 0 <= dday <= 7:
                due_7 += 1
    return {
        "kpi": {
            "open_total": len(open_items),
            "overdue": overdue,
            "due_7": due_7,
            "watchrooms": len(watchroom_store.list_rooms()),
        }
    }


@app.post("/api/jobs/run_issue_summary")
def api_run_issue_summary(token: Optional[str] = None) -> Dict[str, Any]:
    _require_dashboard_token(token)
    if push_job_manager is None:
        return {"ok": False, "error": "push scheduler not started"}
    push_job_manager.run_issue_summary_once()
    return {"ok": True}


@app.post("/api/jobs/run_warn")
def api_run_warn(token: Optional[str] = None) -> Dict[str, Any]:
    _require_dashboard_token(token)
    if push_job_manager is None:
        return {"ok": False, "error": "push scheduler not started"}
    push_job_manager.run_warn_once()
    return {"ok": True}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(token: Optional[str] = None):
    if settings.dashboard_token and (token or "") != settings.dashboard_token:
        return HTMLResponse(
            "<html><body><h3>Dashboard Login</h3><p>?token=... 파라미터를 넣어주세요.</p></body></html>",
            status_code=401,
        )
    return HTMLResponse(
        f"""<html><head><title>{settings.dashboard_title}</title></head>
<body>
<h2>{settings.dashboard_title}</h2>
<p>API:</p>
<ul>
<li>/api/watchrooms?token=...</li>
<li>/api/dashboard/issues?token=...&room_id=...</li>
</ul>
</body></html>"""
    )


@app.on_event("startup")
def startup_chatbot() -> None:
    global chatbot_service, async_dispatcher, push_job_manager
    memory_store.init_db()
    issue_store.init_db()
    watchroom_store.init_db()
    if not (settings.knox_system_id and settings.knox_token):
        logger.info("knox chatbot disabled (missing KNOX_SYSTEM_ID/KNOX_TOKEN)")
        return

    try:
        bot = KnoxMessenger(
            host=settings.knox_host,
            system_id=settings.knox_system_id,
            token=settings.knox_token,
            verify_ssl=settings.knox_verify_ssl,
        )
        bot.device_regist()
        bot.get_keys()
        async_dispatcher = AsyncLLMDispatcher(
            ask_fn=_ask_core,
            messenger=bot,
            memory_store=memory_store,
            workers=max(1, settings.llm_workers),
            queue_max=max(1, settings.llm_job_queue_max),
            max_concurrent=max(1, settings.llm_max_concurrent),
            busy_message=settings.llm_busy_message,
            queue_full_message=settings.llm_queue_full_message,
            long_wait_delay_sec=settings.llm_long_wait_delay_sec,
            enable_recall=settings.enable_recall,
        )
        async_dispatcher.start_workers()
        chatbot_service = ChatbotService(
            messenger=bot,
            ask_fn=_ask_core,
            llm_chat_default_mode=settings.llm_chat_default_mode,
            llm_group_mention_text=settings.llm_group_mention_text,
            llm_group_prefixes=[x.strip() for x in settings.llm_group_prefixes_csv.split(",") if x.strip()],
            memory_reset_commands=[x.strip() for x in settings.memory_reset_commands_csv.split(",") if x.strip()],
            only_single_chat=settings.llm_only_single_chat,
            is_allowed_user_fn=allowlist_service.is_allowed,
            memory_store=memory_store,
            async_dispatcher=async_dispatcher,
            issue_store=issue_store,
            watchroom_store=watchroom_store,
            term_admin_room_ids=[int(x) for x in settings.term_admin_room_ids_csv.split(",") if x.strip().isdigit()],
            warn_runner=_run_warn_once_message,
            route_ui_to_dm_for_group=settings.route_ui_to_dm_for_group,
        )
        if settings.enable_push_scheduler:
            push_job_manager = PushJobManager(
                watchroom_store=watchroom_store,
                issue_store=issue_store,
                send_text_fn=lambda rid, msg: bot.send_text(int(rid), msg),
                warn_message_fn=_run_warn_once_message,
                issue_summary_hhmm=settings.issue_summary_push_hhmm,
                warn_hhmm=settings.warn_push_hhmm,
            )
            push_job_manager.start()
        logger.info("knox chatbot connected")
    except Exception as e:
        chatbot_service = None
        logger.exception("knox chatbot startup failed: %s", e)


@app.post("/message")
async def post_message(request: Request) -> Dict[str, Any]:
    if chatbot_service is None:
        return {"ok": False, "error": "KNOX chatbot not connected"}

    body = await request.body()
    try:
        info = chatbot_service.decrypt_request(body)
    except Exception:
        try:
            info = await request.json()
        except Exception as e:
            return {"ok": False, "error": f"invalid message payload: {e}"}

    return chatbot_service.handle_message(info)


@app.on_event("shutdown")
def shutdown_jobs() -> None:
    if push_job_manager is not None:
        push_job_manager.stop()
