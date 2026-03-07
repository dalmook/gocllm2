from __future__ import annotations

import time
from typing import Any, Dict

from .planner import Plan
from .query_registry.registry import QueryRegistry
from .tools.rag_tool import RagTool
from .tools.db_tool import DBTool
from .tools.compute_tool import ComputeTool


_ALLOWED_TOOLS = {"rag.search", "rag.extract_entities", "db.query", "compute.diff", "answer.compose"}


class PlanExecutionError(Exception):
    pass


class Executor:
    def __init__(self, registry: QueryRegistry):
        self.registry = registry
        self.rag = RagTool()
        self.db = DBTool(registry)
        self.compute = ComputeTool()

    def run(self, plan: Plan, question: str) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {}
        step_logs = []

        for step in plan.steps:
            if step.tool not in _ALLOWED_TOOLS:
                raise PlanExecutionError(f"unsupported tool: {step.tool}")

            t0 = time.perf_counter()
            if step.tool == "rag.search":
                out = self.rag.search(
                    query=step.args.get("query", question),
                    top_k=int(step.args.get("top_k", 5)),
                    filters=step.args.get("filters", {}),
                )
            elif step.tool == "rag.extract_entities":
                from_step = step.args.get("from_step")
                if from_step not in ctx:
                    raise PlanExecutionError(f"missing from_step: {from_step}")
                out = self.rag.extract_entities(ctx[from_step], step.args.get("schema", ["version", "yearmonth", "keywords"]))
            elif step.tool == "db.query":
                qid = step.args.get("query_id", "")
                if not self.registry.get(qid):
                    raise PlanExecutionError(f"unknown query_id: {qid}")

                params = dict(step.args.get("params", {}))
                params_from = step.args.get("params_from")
                param_map = step.args.get("param_map", {})
                if params_from:
                    if params_from not in ctx:
                        raise PlanExecutionError(f"missing params_from step: {params_from}")
                    src = ctx[params_from] if isinstance(ctx[params_from], dict) else {}
                    for dst_k, src_k in param_map.items():
                        if dst_k not in params and src_k in src:
                            params[dst_k] = src[src_k]
                out = self.db.query(qid, params)
            elif step.tool == "compute.diff":
                from_step = step.args.get("from_step")
                if from_step not in ctx:
                    raise PlanExecutionError(f"missing from_step: {from_step}")
                data = ctx[from_step]
                cur = data.get("value") if isinstance(data, dict) else None
                baseline = step.args.get("baseline_value")
                out = self.compute.diff(cur, baseline)
            elif step.tool == "answer.compose":
                out = {"compose": step.args}
            else:
                raise PlanExecutionError(f"not implemented tool: {step.tool}")

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            ctx[step.id] = out
            step_logs.append({"step_id": step.id, "tool": step.tool, "elapsed_ms": round(elapsed_ms, 1)})

        return {"ctx": ctx, "step_logs": step_logs}
