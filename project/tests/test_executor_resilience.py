from project.executor import Executor
from project.planner import Plan, Step
from project.query_registry.registry import QueryRegistry


def test_executor_continue_on_error_keeps_pipeline_alive():
    reg = QueryRegistry()
    reg.load_from_dir("project/query_registry/queries")
    ex = Executor(reg)

    plan = Plan(
        intent="hybrid",
        steps=[
            Step(id="s1", tool="rag.search", args={"query": "이번주 이슈"}),
            Step(id="s2", tool="db.query", args={"query_id": "not_exists", "params": {}}),
            Step(id="s3", tool="answer.compose", args={"question": "이번주 이슈", "rag_from": "s1", "data_from": ["s2"]}),
        ],
    )

    out = ex.run(plan, "이번주 이슈", continue_on_error=True)

    assert "s1" in out["ctx"]
    assert "s2" in out["ctx"]
    assert "error" in out["ctx"]["s2"]
    assert "s3" in out["ctx"]
    assert any(log["status"] == "error" and log["step_id"] == "s2" for log in out["step_logs"])
