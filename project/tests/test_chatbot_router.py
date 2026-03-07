from project.chatbot.router import parse_action_payload


def _parse(info):
    return parse_action_payload(
        info,
        llm_chat_default_mode="mention",
        llm_group_mention_text="@공급망 챗봇",
        llm_group_prefixes=["봇", "챗봇"],
        memory_reset_commands=["/reset"],
        quick_link_aliases=[(["GSCM"], "GSCM", "https://dsgscm.sec.samsung.net/")],
    )


def test_single_plain_text_routes_llm_chat():
    action, payload = _parse({"chatMsg": "2월 WC 버전 판매", "chatType": "SINGLE"})
    assert action == "LLM_CHAT"
    assert payload["question"] == "2월 WC 버전 판매"


def test_group_mention_routes_llm_chat():
    action, payload = _parse({"chatMsg": "@공급망 챗봇 이번주 이슈 요약", "chatType": "GROUP"})
    assert action == "LLM_CHAT"
    assert payload["question"] == "이번주 이슈 요약"


def test_group_ask_command_is_ignored():
    action, payload = _parse({"chatMsg": "/ask 이번주 이슈 요약", "chatType": "GROUP"})
    assert action == "NOOP"
    assert payload == {}


def test_single_shortcut_open_url():
    action, payload = _parse({"chatMsg": "/gscm", "chatType": "SINGLE"})
    assert action == "OPEN_URL"
    assert payload["url"].startswith("https://")


def test_issue_command_routes_issue_form():
    action, payload = _parse({"chatMsg": "/issue", "chatType": "SINGLE"})
    assert action == "ISSUE_FORM"
    assert payload == {}


def test_warn_command_routes_warn_run():
    action, payload = _parse({"chatMsg": "/warn", "chatType": "SINGLE"})
    assert action == "WARN_RUN"
    assert payload == {}


def test_watchroom_command_routes_form():
    action, payload = _parse({"chatMsg": "/watchroom", "chatType": "SINGLE"})
    assert action == "WATCHROOM_FORM"
    assert payload == {}


def test_query_command_routes_list():
    action, payload = _parse({"chatMsg": "/query", "chatType": "SINGLE"})
    assert action == "QUERY_LIST"
    assert payload == {}


def test_query_command_routes_form_by_id():
    action, payload = _parse({"chatMsg": "/query sales_monthly", "chatType": "SINGLE"})
    assert action == "QUERY_FORM"
    assert payload["query_id"] == "sales_monthly"
