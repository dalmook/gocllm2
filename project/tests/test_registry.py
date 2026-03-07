from project.query_registry.registry import QueryRegistry


def test_registry_load_and_list():
    reg = QueryRegistry()
    reg.load_from_dir("project/query_registry/queries")
    rows = reg.list_for_planner()
    ids = {r["id"] for r in rows}
    assert "psi_sales_by_month" in ids
    assert "psi_fab_tg" in ids


def test_registry_param_resolution_yyyymm():
    reg = QueryRegistry()
    reg.load_from_dir("project/query_registry/queries")
    p = reg.resolve_params("psi_sales_by_month", {"version": "WC", "yearmonth": "202603"})
    assert p["version"] == "WC"
    assert p["yearmonth"] == "202603"
