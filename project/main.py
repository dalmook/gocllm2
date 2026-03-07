from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from .chatbot.access import AllowlistService
from .chatbot.service import ChatbotService
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


def _ask_core(question: str) -> Dict[str, Any]:
    request_id = str(uuid.uuid4())
    question = question.strip()

    try:
        plan = planner.make_plan(question, registry.list_for_planner())
    except Exception as e:
        logger.exception("request_id=%s planner_failed", request_id)
        if llm.enabled:
            answer = llm.invoke_text(
                "당신은 짧고 명확하게 답변하는 비서입니다.",
                f"질문: {question}\n가능한 범위에서 답변하세요.",
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
                f"질문: {question}\nDB 조회가 실패해도 가능한 범위에서 답변하세요.",
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


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"ok": True, "queries": len(registry.list_for_planner())}


@app.post("/ask")
def ask(req: AskRequest) -> Dict[str, Any]:
    return _ask_core(req.question)


@app.on_event("startup")
def startup_chatbot() -> None:
    global chatbot_service
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
        chatbot_service = ChatbotService(
            messenger=bot,
            ask_fn=_ask_core,
            llm_chat_default_mode=settings.llm_chat_default_mode,
            llm_group_mention_text=settings.llm_group_mention_text,
            llm_group_prefixes=[x.strip() for x in settings.llm_group_prefixes_csv.split(",") if x.strip()],
            memory_reset_commands=[x.strip() for x in settings.memory_reset_commands_csv.split(",") if x.strip()],
            only_single_chat=settings.llm_only_single_chat,
            is_allowed_user_fn=allowlist_service.is_allowed,
        )
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
