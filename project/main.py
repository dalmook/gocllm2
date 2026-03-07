from __future__ import annotations

import logging
import uuid
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .settings import settings
from .llm_client import LLMClient
from .planner import Planner, Plan, Step
from .executor import Executor, PlanExecutionError
from .synthesizer import Synthesizer
from .query_registry.registry import QueryRegistry


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("hybrid-assistant")

app = FastAPI(title=settings.app_name)

registry = QueryRegistry()
registry.load_from_dir(settings.query_dir)
llm = LLMClient()
planner = Planner(llm)
executor = Executor(registry)
synthesizer = Synthesizer(llm)


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"ok": True, "queries": len(registry.list_for_planner())}


@app.post("/ask")
def ask(req: AskRequest) -> Dict[str, Any]:
    request_id = str(uuid.uuid4())
    question = req.question.strip()

    try:
        plan = planner.make_plan(question, registry.list_for_planner())
    except Exception as e:
        logger.exception("request_id=%s planner_failed", request_id)
        raise HTTPException(status_code=400, detail=f"Planner error: {e}")

    # guardrail: ensure last step has answer.compose
    if not plan.steps or plan.steps[-1].tool != "answer.compose":
        plan.steps.append(Step(id=f"s{len(plan.steps)+1}", tool="answer.compose", args={"question": question, "data_from": []}))

    try:
        ran = executor.run(plan, question)
    except PlanExecutionError as e:
        logger.warning("request_id=%s executor_failed=%s", request_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        # required param miss, type validation fail etc.
        logger.warning("request_id=%s validation_failed=%s", request_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("request_id=%s executor_unknown_failed", request_id)
        raise HTTPException(status_code=500, detail=f"Executor error: {e}")

    compose_step = plan.steps[-1]
    answer = synthesizer.compose(question, ran["ctx"], compose_step.args)

    # evidence packing
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
