from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field

from .llm_client import LLMClient


class Step(BaseModel):
    id: str
    tool: Literal["rag.search", "rag.extract_entities", "db.query", "compute.diff", "answer.compose"]
    args: Dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    intent: Literal["data_only", "rag_only", "hybrid"]
    steps: List[Step]


class Planner:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def _normalize_params(self, question: str, params: Dict[str, Any]) -> Dict[str, Any]:
        import re
        from datetime import datetime

        params = dict(params or {})

        # "2월" -> "202502"
        ym = params.get("yearmonth")
        if isinstance(ym, str):
            m = re.fullmatch(r"\s*(\d{1,2})월\s*", ym)
            if m:
                month = int(m.group(1))
                year = datetime.now().year
                params["yearmonth"] = f"{year}{month:02d}"

        # 질문 안에 월이 있고 params에 없으면 보정
        if not params.get("yearmonth"):
            m = re.search(r"(\d{1,2})월", question)
            if m:
                month = int(m.group(1))
                year = datetime.now().year
                params["yearmonth"] = f"{year}{month:02d}"

        return params

    def make_plan(self, question: str, query_catalog: List[Dict[str, str]]) -> Plan:
        # fallback heuristic if llm is not configured
        if not self.llm.enabled:
            if "이슈" in question:
                return Plan(intent="rag_only", steps=[
                    Step(id="s1", tool="rag.search", args={"query": question, "top_k": 5}),
                    Step(id="s2", tool="answer.compose", args={"question": question, "rag_from": "s1", "data_from": []}),
                ])
            return Plan(intent="data_only", steps=[
                Step(id="s1", tool="db.query", args={"query_id": "psi_sales_by_month", "params": {}}),
                Step(id="s2", tool="answer.compose", args={"question": question, "data_from": ["s1"]}),
            ])

        sys_prompt = (
            "You are a strict planning engine.\n"
            "Output JSON only.\n"
            "Never write SQL.\n"
            "Select query_id from catalog only.\n"
            "You must return this exact schema:\n"
            "{\n"
            '  "intent": "data_only" | "rag_only" | "hybrid",\n'
            '  "steps": [\n'
            "    {\n"
            '      "id": "s1",\n'
            '      "tool": "db.query" | "rag.search" | "rag.extract_entities" | "compute.diff" | "answer.compose",\n'
            '      "args": { ... }\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Rules:\n"
            "- Every step must have id, tool, args.\n"
            "- For DB queries, use tool='db.query' and args={'query_id': ..., 'params': {...}}.\n"
            "- For final answer, use tool='answer.compose'.\n"
            "- Do not return query_id at top level of step.\n"
            "- Do not omit required fields.\n"
        )

        user_prompt = (
            f"question={question}\n"
            f"catalog={query_catalog}\n"
            "Return only valid Plan JSON.\n"
            "Examples:\n"
            '{'
            '"intent":"data_only",'
            '"steps":['
            '{"id":"s1","tool":"db.query","args":{"query_id":"psi_sales_by_month","params":{"yearmonth":"202502","version":"WC"}}},'
            '{"id":"s2","tool":"answer.compose","args":{"question":"2월 WC 버전 판매 몇개야","data_from":["s1"]}}'
            ']'
            '}'
        )

        data = self.llm.invoke_json(sys_prompt, user_prompt)

        # LLM step 자동 보정
        steps = data.get("steps", [])
        fixed_steps = []
        for i, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue

            # query_id / params만 바로 준 경우 → db.query step으로 보정
            if "tool" not in step and "query_id" in step:
                step = {
                    "id": f"s{i}",
                    "tool": "db.query",
                    "args": {
                        "query_id": step["query_id"],
                        "params": step.get("params", {})
                    }
                }

            # id 없으면 자동 부여
            if "id" not in step:
                step["id"] = f"s{i}"

            # args 없으면 기본값
            if "args" not in step:
                step["args"] = {}

            fixed_steps.append(step)

        for step in fixed_steps:
            if step.get("tool") == "db.query":
                args = step.get("args", {})
                args["params"] = self._normalize_params(question, args.get("params", {}))
                step["args"] = args

        data["steps"] = fixed_steps
        return Plan.model_validate(data)
