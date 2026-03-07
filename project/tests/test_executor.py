from project.executor import Executor
from project.planner import Plan, Step
from project.query_registry.registry import QueryRegistry


def test_executor_rejects_unknown_tool():
    reg = QueryRegistry()
    reg.load_from_dir("project/query_registry/queries")
    ex = Executor(reg)
    plan = Plan(intent="rag_only", steps=[Step(id="s1", tool="rag.search", args={"query": "x"})])
    out = ex.run(plan, "x")
    assert "s1" in out["ctx"]


def test_executor_unknown_query_id_fails():
    reg = QueryRegistry()
    reg.load_from_dir("project/query_registry/queries")
    ex = Executor(reg)
    plan = Plan(intent="data_only", steps=[Step(id="s1", tool="db.query", args={"query_id": "not_exists", "params": {}})])
    try:
        ex.run(plan, "2월 WC 버전 판매")
        assert False, "should fail"
    except Exception as e:
        assert "unknown query_id" in str(e)
