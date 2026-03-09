from __future__ import annotations

from typing import Any, Dict, List

from .llm_client import LLMClient


class Synthesizer:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    @staticmethod
    def _truncate_text(text: str, limit: int = 900) -> str:
        s = (text or "").strip()
        if len(s) <= limit:
            return s
        return s[:limit] + " ..."

    @staticmethod
    def _pick_snippet(doc: Dict[str, Any]) -> str:
        source = doc.get("_source") if isinstance(doc.get("_source"), dict) else {}
        for key in (
            "snippet",
            "content",
            "summary",
            "text",
            "body",
            "description",
            "merge_title_content",
            "chunk_text",
            "page_content",
            "mail_body",
            "body_text",
            "document_text",
        ):
            value = doc.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            s_value = source.get(key)
            if isinstance(s_value, str) and s_value.strip():
                return s_value.strip()
        return ""

    def _format_rag_context(self, rag_data: List[Dict[str, Any]], max_docs: int = 4) -> str:
        if not rag_data:
            return ""
        parts: List[str] = []
        for i, doc in enumerate(rag_data[:max(1, max_docs)], 1):
            meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
            title = str(doc.get("title") or "제목 없음").strip()
            link = str(doc.get("link") or "").strip()
            score = meta.get("score", 0)
            index = str(meta.get("index") or "").strip()
            snippet = self._truncate_text(self._pick_snippet(doc), 900)
            parts.append(
                f"[문서 {i}]\n"
                f"제목: {title}\n"
                f"인덱스: {index}\n"
                f"점수: {score}\n"
                f"내용: {snippet}\n"
                f"출처: {link}"
            )
        return "\n\n".join(parts)

    def compose(self, question: str, ctx: Dict[str, Any], compose_args: Dict[str, Any]) -> str:
        rag_from = compose_args.get("rag_from")
        data_from = compose_args.get("data_from", [])

        rag_data: List[Dict[str, Any]] = ctx.get(rag_from, []) if rag_from else []
        data_parts = [ctx.get(sid) for sid in data_from]
        rag_context = self._format_rag_context(rag_data, max_docs=4)

        if not self.llm.enabled:
            chunks = []
            if rag_data:
                chunks.append(f"RAG {len(rag_data)}건 참고")
            if data_parts:
                chunks.append(f"DB/계산 결과 {len(data_parts)}건")
            return f"질문: {question}\n" + " | ".join(chunks)

        system_prompt = (
            "당신은 짧고 명확하게 답변하는 비서입니다. "
            "제공된 근거만 사용하고 SQL을 만들거나 추측하지 마세요. "
            "근거가 충분하면 핵심 사실을 구체적으로 요약하고, 근거가 부족하면 부족한 항목을 한 줄로 명시하세요."
        )
        user_prompt = (
            f"질문: {question}\n\n"
            f"RAG 근거:\n{rag_context}\n\n"
            f"DB/계산 결과: {data_parts}\n\n"
            "요구사항: 1) 핵심답 2~4문장 2) 마지막 줄에 근거 요약(문서번호 포함)"
        )
        return self.llm.invoke_text(system_prompt, user_prompt)
