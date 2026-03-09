from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from .llm_client import LLMClient


class Synthesizer:
    def __init__(self, llm: "LLMClient"):
        self.llm = llm

    @staticmethod
    def _truncate_text(text: str, limit: int = 2200) -> str:
        s = (text or "").strip()
        if len(s) <= limit:
            return s
        return s[:limit] + " ..."

    @staticmethod
    def _pick_content(doc: Dict[str, Any]) -> str:
        source = doc.get("_source") if isinstance(doc.get("_source"), dict) else {}
        for key in (
            "content",
            "merge_title_content",
            "summary",
            "snippet",
            "text",
            "body",
            "description",
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
        return Synthesizer._pick_fallback_content(doc)

    @staticmethod
    def _collect_text_fragments(obj: Any, out: List[str], *, depth: int = 0) -> None:
        if depth > 3 or len(out) >= 12:
            return
        if isinstance(obj, str):
            s = re.sub(r"\s+", " ", obj).strip()
            if len(s) >= 20 and not s.startswith(("http://", "https://")):
                out.append(s)
            return
        if isinstance(obj, dict):
            for _, v in obj.items():
                Synthesizer._collect_text_fragments(v, out, depth=depth + 1)
            return
        if isinstance(obj, list):
            for item in obj[:20]:
                Synthesizer._collect_text_fragments(item, out, depth=depth + 1)

    @staticmethod
    def _pick_fallback_content(doc: Dict[str, Any]) -> str:
        frags: List[str] = []
        Synthesizer._collect_text_fragments(doc, frags)
        dedup: List[str] = []
        seen = set()
        for f in frags:
            key = f[:120]
            if key in seen:
                continue
            seen.add(key)
            dedup.append(f)
        if not dedup:
            return ""
        return "\n".join(dedup[:3])[:3500]

    @staticmethod
    def _pick_link(doc: Dict[str, Any]) -> str:
        source = doc.get("_source") if isinstance(doc.get("_source"), dict) else {}
        for key in ("confluence_mail_page_url", "url", "source_url", "doc_url", "link"):
            value = doc.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            s_value = source.get(key)
            if isinstance(s_value, str) and s_value.strip():
                return s_value.strip()
        return ""

    def _format_rag_context(self, rag_data: List[Dict[str, Any]], max_docs: int = 3) -> str:
        if not rag_data:
            return ""
        parts: List[str] = []
        for i, doc in enumerate(rag_data[:max(1, max_docs)], 1):
            meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
            title = str(doc.get("title") or doc.get("doc_id") or "제목 없음").strip()
            index = str(doc.get("_index") or meta.get("index") or "").strip()
            doc_date = str(doc.get("_doc_date") or meta.get("doc_date") or "날짜 정보 없음").strip()
            score = doc.get("_combined_score")
            if score is None:
                score = meta.get("combined_score", doc.get("_score", meta.get("score", 0)))
            content = self._truncate_text(self._pick_content(doc), 2200)
            link = self._pick_link(doc)
            parts.append(
                f"[문서 {i}]\n"
                f"제목: {title}\n"
                f"문서일시: {doc_date}\n"
                f"종합점수: {score}\n"
                f"인덱스: {index}\n"
                f"내용: {content}\n"
                f"출처: {link}"
            )
        return "\n\n".join(parts)

    def _append_source_lines(self, answer: str, rag_data: List[Dict[str, Any]], max_docs: int = 3) -> str:
        if "📂 근거 문서" in answer:
            return answer
        lines: List[str] = []
        for doc in rag_data[:max(1, max_docs)]:
            title = str(doc.get("title") or "제목 없음")
            meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
            doc_date = str(doc.get("_doc_date") or meta.get("doc_date") or "날짜 정보 없음")
            url = self._pick_link(doc)
            line = f"- {title} | {doc_date}"
            if url:
                line += f"\n  🔗 GO LINK: {url}"
            lines.append(line)
        if not lines:
            return answer
        return answer + "\n\n📂 근거 문서\n" + "\n".join(lines)

    @staticmethod
    def _looks_like_clarification_request(answer: str) -> bool:
        t = (answer or "").strip().lower()
        patterns = [
            "무슨 뜻",
            "무엇인지",
            "무엇을 의미",
            "약어",
            "무엇을 의미",
            "구체적으로 알려",
            "추가 정보를",
            "추가 정보",
            "더 자세한 정보",
            "명확히 해",
            "설명해주실",
            "의미하는 바",
            "질문하신",
            "확인해 주",
            "확인 부탁",
            "정확히 어떤",
            "어떤 의미",
            "어떤 것을",
            "what does",
            "what is",
            "what does it mean",
            "could you provide more context",
            "need more context",
            "please clarify",
            "could you clarify",
        ]
        return any(p in t for p in patterns)

    def _compose_doc_only_fallback(self, question: str, rag_data: List[Dict[str, Any]], max_docs: int = 3) -> str:
        lines: List[str] = ["📌 한줄 요약", "- 검색 문서 기준으로 이번 이슈를 요약했습니다.", "", "📂 문서 기반 답변"]
        for doc in rag_data[:max(1, max_docs)]:
            meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
            title = str(doc.get("title") or "제목 없음").strip()
            doc_date = str(doc.get("_doc_date") or meta.get("doc_date") or "날짜 정보 없음").strip()
            content = self._pick_content(doc)
            brief = self._truncate_text(content, 220).replace("\n", " ")
            if not brief:
                brief = title
            lines.append(f"- ({doc_date}) {brief}")
        lines.extend(["", "💡 AI 의견", "- 문서 기반 요약이며, 세부 영향도는 추가 확인이 필요합니다."])
        out = "\n".join(lines)
        return self._append_source_lines(out, rag_data, max_docs=max_docs)

    def compose(self, question: str, ctx: Dict[str, Any], compose_args: Dict[str, Any]) -> str:
        rag_from = compose_args.get("rag_from")
        data_from = compose_args.get("data_from", [])

        rag_data: List[Dict[str, Any]] = ctx.get(rag_from, []) if rag_from else []
        data_parts = [ctx.get(sid) for sid in data_from]

        if not self.llm.enabled:
            # 기존 체감 동작 보존: 문서가 있으면 되묻기 없이 문서 요약을 바로 반환한다.
            if rag_data:
                return self._compose_doc_only_fallback(question, rag_data, max_docs=3)
            chunks = []
            if data_parts:
                chunks.append(f"DB/계산 결과 {len(data_parts)}건")
            return f"질문: {question}\n" + " | ".join(chunks)

        if rag_data:
            rag_context = self._format_rag_context(rag_data, max_docs=3)
            system_prompt = (
                "당신은 GOC 업무 지원 챗봇입니다.\n\n"
                "최우선 규칙\n"
                "1) 아래 [검색 문서]에 있는 내용만을 근거로 '📂 문서 기반 답변'을 작성하세요. (추측/일반상식/외부지식 금지)\n"
                "2) 문서에 없는 내용은 반드시 '문서에 해당 정보가 없습니다.'라고 명시하세요.\n"
                "3) 질문에 기간(이번주/저번주/지난주/오늘/어제/최근N일)이 포함되면, 답변 첫 줄 또는 요약에 적용한 기간을 반드시 명시하세요.\n"
                "4) 질문에 기간 지정이 없으면, 검색 문서 중 가장 최신 문서일시를 기준으로 답변하고 기준 문서일시를 명시하세요.\n"
                "5) 문서 간 내용이 다르면 가장 최신 문서를 우선하고, '문서 간 상충'이라고 표시하세요.\n"
                "6) 답변의 항목/불릿은 가능한 한 문서일시 최신순(내림차순)으로 배치하세요.\n"
                "7) '💡 AI 의견'은 참고용 보충설명만 가능하며, 문서 사실처럼 단정하지 마세요.\n"
                "8) 사용자에게 되묻거나 추가 설명을 요구하지 마세요. 문서가 있는 한 문서 내용으로 바로 답하세요.\n"
            )
            user_prompt = (
                f"질문: {question}\n\n"
                f"[검색 문서]\n{rag_context}\n\n"
                f"DB/계산 결과: {data_parts}\n\n"
                "출력 형식(아래 순서/제목 유지)\n"
                "📌 한줄 요약\n"
                "- (기간/기준일시 포함 1문장)\n\n"
                "📂 문서 기반 답변\n"
                "- 핵심 사실 2~5개\n"
                "- 문서에 없는 부분은 '문서에 해당 정보가 없습니다.'\n\n"
                "💡 AI 의견\n"
                "- 참고용 해석 1~3개\n\n"
                "📂 근거 문서\n"
                "- 문서명 | 문서일시 | 근거한줄 | 링크 (최대 3개)"
            )
            # 코드 레벨 가드: 문서가 한 건이라도 있으면 clarification 응답을 허용하지 않고 문서 요약으로 치환한다.
            try:
                answer = self.llm.invoke_text(system_prompt, user_prompt).strip()
            except Exception:
                return self._compose_doc_only_fallback(question, rag_data, max_docs=3)
            if not answer or self._looks_like_clarification_request(answer):
                return self._compose_doc_only_fallback(question, rag_data, max_docs=3)
            return self._append_source_lines(answer, rag_data, max_docs=3)

        fallback_system_prompt = (
            "당신은 GOC 업무 지원 챗봇입니다. "
            "이번 질문은 문서 검색 결과가 없거나 관련성이 낮아 일반 LLM 답변으로 안내합니다. "
            "과도한 추측은 피하고, 불확실한 내용은 단정하지 마세요."
        )
        fallback_user_prompt = (
            "📋 문서 기반 답변 미적용\n"
            "- 관련 문서를 찾지 못했거나 질문과의 관련성이 낮았습니다.\n"
            "- 아래는 일반 LLM 답변입니다.\n\n"
            f"질문: {question}\n"
            f"DB/계산 결과: {data_parts}"
        )
        return self.llm.invoke_text(fallback_system_prompt, fallback_user_prompt).strip()
