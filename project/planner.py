from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from .llm_client import LLMClient


class Step(BaseModel):
    id: str
    tool: Literal["rag.search", "rag.extract_entities", "db.query", "compute.diff", "answer.compose"]
    args: Dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    intent: Literal["data_only", "rag_only", "hybrid"]
    steps: List[Step]


_RAG_HINTS = ("이슈", "요약", "정리", "최근", "최신", "현황", "업데이트", "동향")
_DATA_HINTS = ("판매", "매출", "수량", "합계", "fab", "tg", "psi")


class Planner:
    def __init__(self, llm: LLMClient, *, tz: str = "Asia/Seoul"):
        self.llm = llm
        self.tz = tz

    def _now(self) -> datetime:
        return datetime.now(ZoneInfo(self.tz))

    def _to_yyyymm(self, year: int, month: int) -> str:
        return f"{year:04d}{month:02d}"

    def _extract_yearmonth(self, question: str) -> Optional[str]:
        q = (question or "").strip()
        now = self._now()

        m = re.search(r"\b(20\d{2})(0[1-9]|1[0-2])\b", q)
        if m:
            return f"{m.group(1)}{m.group(2)}"

        m = re.search(r"(20\d{2})\s*년\s*(1[0-2]|0?[1-9])\s*월", q)
        if m:
            return self._to_yyyymm(int(m.group(1)), int(m.group(2)))

        m = re.search(r"\b(1[0-2]|0?[1-9])\s*월", q)
        if m:
            return self._to_yyyymm(now.year, int(m.group(1)))

        if any(tok in q for tok in ("이번달", "이번 달", "금월")):
            return self._to_yyyymm(now.year, now.month)
        if any(tok in q for tok in ("지난달", "지난 달", "전월")):
            y, m = now.year, now.month - 1
            if m == 0:
                y -= 1
                m = 12
            return self._to_yyyymm(y, m)

        return None

    def _extract_version(self, question: str) -> Optional[str]:
        q = (question or "")

        # ex) "WC 버전", "버전 WC"
        m = re.search(r"\b([A-Za-z][A-Za-z0-9_-]{0,11})\s*버전\b", q, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        m = re.search(r"\b버전\s*([A-Za-z][A-Za-z0-9_-]{0,11})\b", q, re.IGNORECASE)
        if m:
            return m.group(1).upper()

        # short code fallback (avoids long words)
        for tok in re.findall(r"\b[A-Za-z]{1,6}[0-9]{0,3}\b", q):
            up = tok.upper()
            if up in {"WC", "HBM", "LPDDR", "DDR", "NAND"}:
                return up

        return None

    def _extract_params(self, question: str) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        yearmonth = self._extract_yearmonth(question)
        version = self._extract_version(question)
        if yearmonth:
            params["yearmonth"] = yearmonth
        if version:
            params["version"] = version
        return params

    def _classify_intent(self, question: str) -> Literal["data_only", "rag_only", "hybrid"]:
        q = (question or "")
        q_compact = re.sub(r"\s+", "", q)

        rag_score = sum(1 for h in _RAG_HINTS if h in q_compact)
        data_score = sum(1 for h in _DATA_HINTS if h in q_compact.lower())

        if rag_score > 0 and data_score > 0:
            return "hybrid"
        if rag_score > 0:
            return "rag_only"
        return "data_only"

    def _choose_query_id(self, question: str, query_catalog: List[Dict[str, str]]) -> Optional[str]:
        q = (question or "").lower()
        ids = {c.get("id", "") for c in query_catalog}

        if any(k in q for k in ("fab", "fab_tg", "tg")) and "psi_fab_tg" in ids:
            return "psi_fab_tg"
        if any(k in q for k in ("판매", "sales", "수량", "매출")) and "psi_sales_by_month" in ids:
            return "psi_sales_by_month"

        # deterministic fallback: first catalog item
        return query_catalog[0]["id"] if query_catalog else None

    def _normalize_params(self, question: str, params: Dict[str, Any]) -> Dict[str, Any]:
        params = dict(params or {})

        # planner deterministic extraction takes precedence for missing fields
        extracted = self._extract_params(question)
        for k, v in extracted.items():
            params.setdefault(k, v)

        # keep backward compatible 2월 형태
        ym = params.get("yearmonth")
        if isinstance(ym, str):
            m = re.fullmatch(r"\s*(\d{1,2})월\s*", ym)
            if m:
                params["yearmonth"] = self._to_yyyymm(self._now().year, int(m.group(1)))

        return params

    def _build_fallback_plan(self, question: str, query_catalog: List[Dict[str, str]]) -> Plan:
        intent = self._classify_intent(question)
        steps: List[Step] = []

        if intent in ("hybrid", "rag_only"):
            steps.append(Step(id="s1", tool="rag.search", args={"query": question, "top_k": 5}))

        if intent in ("hybrid", "data_only"):
            query_id = self._choose_query_id(question, query_catalog)
            if query_id:
                sid = f"s{len(steps)+1}"
                steps.append(Step(id=sid, tool="db.query", args={
                    "query_id": query_id,
                    "params": self._extract_params(question),
                }))

        data_from = [s.id for s in steps if s.tool == "db.query"]
        rag_steps = [s.id for s in steps if s.tool == "rag.search"]
        compose_args: Dict[str, Any] = {"question": question, "data_from": data_from}
        if rag_steps:
            compose_args["rag_from"] = rag_steps[-1]

        steps.append(Step(id=f"s{len(steps)+1}", tool="answer.compose", args=compose_args))
        return Plan(intent=intent, steps=steps)

    def make_plan(self, question: str, query_catalog: List[Dict[str, str]]) -> Plan:
        fallback = self._build_fallback_plan(question, query_catalog)

        # fallback heuristic when llm disabled
        if not self.llm.enabled:
            return fallback

        intent_hint = self._classify_intent(question)
        params_hint = self._extract_params(question)
        query_hint = self._choose_query_id(question, query_catalog)

        sys_prompt = (
            "You are a strict planning engine. Output JSON only.\n"
            "Never write SQL. Select query_id from catalog only.\n"
            "Use intent_hint/query_hint/params_hint unless the question clearly conflicts.\n"
            "Schema:\n"
            "{\"intent\":\"data_only|rag_only|hybrid\",\"steps\":[{\"id\":\"s1\",\"tool\":\"db.query|rag.search|rag.extract_entities|compute.diff|answer.compose\",\"args\":{}}]}\n"
            "Rules:\n"
            "- Every step must have id/tool/args.\n"
            "- db.query args must be {'query_id':..., 'params':{...}}\n"
            "- Include final answer.compose step.\n"
        )
        user_prompt = (
            f"question={question}\n"
            f"catalog={query_catalog}\n"
            f"intent_hint={intent_hint}\n"
            f"query_hint={query_hint}\n"
            f"params_hint={params_hint}\n"
            "Return only valid JSON."
        )

        try:
            data = self.llm.invoke_json(sys_prompt, user_prompt)
        except Exception:
            return fallback

        raw_steps = data.get("steps", []) if isinstance(data, dict) else []
        fixed_steps = []
        for i, step in enumerate(raw_steps, start=1):
            if not isinstance(step, dict):
                continue
            if "tool" not in step and "query_id" in step:
                step = {
                    "id": f"s{i}",
                    "tool": "db.query",
                    "args": {"query_id": step.get("query_id"), "params": step.get("params", {})},
                }
            step.setdefault("id", f"s{i}")
            step.setdefault("args", {})
            fixed_steps.append(step)

        # If model returns invalid/empty steps, use deterministic fallback.
        if not fixed_steps:
            return fallback

        for step in fixed_steps:
            if step.get("tool") == "db.query":
                args = step.get("args", {})
                if not args.get("query_id"):
                    args["query_id"] = query_hint
                args["params"] = self._normalize_params(question, args.get("params", {}))
                step["args"] = args

        data = {
            "intent": data.get("intent", intent_hint) if isinstance(data, dict) else intent_hint,
            "steps": fixed_steps,
        }

        try:
            return Plan.model_validate(data)
        except Exception:
            return fallback
