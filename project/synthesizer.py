from __future__ import annotations

from typing import Any, Dict, List

from .llm_client import LLMClient


class Synthesizer:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def compose(self, question: str, ctx: Dict[str, Any], compose_args: Dict[str, Any]) -> str:
        rag_from = compose_args.get("rag_from")
        data_from = compose_args.get("data_from", [])

        rag_data: List[Dict[str, Any]] = ctx.get(rag_from, []) if rag_from else []
        data_parts = [ctx.get(sid) for sid in data_from]

        if not self.llm.enabled:
            chunks = []
            if rag_data:
                chunks.append(f"RAG {len(rag_data)}건 참고")
            if data_parts:
                chunks.append(f"DB/계산 결과 {len(data_parts)}건")
            return f"질문: {question}\n" + " | ".join(chunks)

        system_prompt = (
            "당신은 짧고 명확하게 답변하는 비서입니다. "
            "제공된 근거만 사용하고 SQL을 만들거나 추측하지 마세요."
        )
        user_prompt = (
            f"질문: {question}\n\n"
            f"RAG 근거: {rag_data}\n\n"
            f"DB/계산 결과: {data_parts}\n\n"
            "요구사항: 1) 핵심답 2~4문장 2) 마지막 줄에 근거 요약"
        )
        return self.llm.invoke_text(system_prompt, user_prompt)
