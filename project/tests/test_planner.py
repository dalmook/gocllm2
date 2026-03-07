from project.planner import Planner


class DummyLLM:
    enabled = False


def _catalog():
    return [
        {"id": "psi_sales_by_month", "description": "특정 월/버전 판매량 합계"},
        {"id": "psi_fab_tg", "description": "특정 월/버전 FAB_TG 합계"},
    ]


def test_planner_extracts_month_and_version_for_sales():
    p = Planner(DummyLLM(), tz="Asia/Seoul")
    plan = p.make_plan("2월 WC 버전 판매 몇개야", _catalog())

    db_steps = [s for s in plan.steps if s.tool == "db.query"]
    assert len(db_steps) == 1
    assert db_steps[0].args["query_id"] == "psi_sales_by_month"
    assert db_steps[0].args["params"]["version"] == "WC"
    assert db_steps[0].args["params"]["yearmonth"].endswith("02")


def test_planner_extracts_fab_query_id():
    p = Planner(DummyLLM(), tz="Asia/Seoul")
    plan = p.make_plan("지난달 fab tg 알려줘", _catalog())

    db_steps = [s for s in plan.steps if s.tool == "db.query"]
    assert len(db_steps) == 1
    assert db_steps[0].args["query_id"] == "psi_fab_tg"
    assert "yearmonth" in db_steps[0].args["params"]


def test_planner_rag_only_for_issue_summary():
    p = Planner(DummyLLM(), tz="Asia/Seoul")
    plan = p.make_plan("이번주 이슈 요약해줘", _catalog())

    assert plan.intent in ("rag_only", "hybrid")
    assert any(s.tool == "rag.search" for s in plan.steps)
    assert plan.steps[-1].tool == "answer.compose"
