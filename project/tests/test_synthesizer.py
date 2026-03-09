from project.synthesizer import Synthesizer


class DummyLLM:
    def __init__(self, responses=None, *, enabled=True, raises=False):
        self.enabled = enabled
        self._responses = list(responses or [])
        self._raises = raises
        self.calls = []

    def invoke_text(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append({"system": system_prompt, "user": user_prompt})
        if self._raises:
            raise RuntimeError("llm failed")
        if self._responses:
            return self._responses.pop(0)
        return "기본 응답"


def _rag_docs():
    return [
        {
            "title": "VH 주간 이슈 리포트",
            "_doc_date": "2026-03-08 09:00",
            "content": "VH 관련 장애 대응 현황과 이번주 조치 계획이 정리되어 있습니다.",
            "url": "https://go/doc-vh",
        },
        {
            "title": "VF Edge DC 상향결정 공지",
            "_doc_date": "2026-03-07 18:00",
            "content": "VF Edge DC 상향결정 배경 및 영향 범위, 일정이 포함되어 있습니다.",
            "url": "https://go/doc-vf",
        },
    ]


def test_compose_replaces_clarification_with_doc_summary_when_docs_exist():
    llm = DummyLLM(responses=["vh가 무엇을 의미하는지 명확히 알려주세요."])
    s = Synthesizer(llm)
    answer = s.compose(
        "vh 이번주 이슈 있어?",
        {"s1": _rag_docs()},
        {"rag_from": "s1", "data_from": []},
    )
    assert "📂 문서 기반 답변" in answer
    assert "VH 관련 장애 대응" in answer
    assert "무엇을 의미" not in answer


def test_compose_returns_doc_summary_for_matched_vf_edge_query():
    llm = DummyLLM(
        responses=[
            "📌 한줄 요약\n- VF Edge DC 상향결정 관련 변경점이 정리되었습니다.\n\n📂 문서 기반 답변\n- 핵심 내용 정리"
        ]
    )
    s = Synthesizer(llm)
    answer = s.compose(
        "VF Edge DC 상향결정 관련 내용 있어?",
        {"s1": _rag_docs()},
        {"rag_from": "s1", "data_from": []},
    )
    assert "📂 문서 기반 답변" in answer
    assert "📂 근거 문서" in answer
    assert "VF Edge DC 상향결정 공지" in answer


def test_compose_blocks_english_clarification_for_acronym_query():
    llm = DummyLLM(responses=["Could you clarify what VH means and provide more context?"])
    s = Synthesizer(llm)
    answer = s.compose(
        "VH 상태 알려줘",
        {"s1": _rag_docs()},
        {"rag_from": "s1", "data_from": []},
    )
    assert "📂 문서 기반 답변" in answer
    assert "clarify" not in answer.lower()
    assert "한줄 요약" in answer


def test_compose_allows_general_answer_only_when_no_docs():
    llm = DummyLLM(responses=["문서가 없어 일반 답변으로 안내합니다."])
    s = Synthesizer(llm)
    answer = s.compose(
        "관련 자료 있어?",
        {},
        {"data_from": []},
    )
    assert answer == "문서가 없어 일반 답변으로 안내합니다."
    assert len(llm.calls) == 1
    assert "문서 기반 답변 미적용" in llm.calls[0]["user"]

