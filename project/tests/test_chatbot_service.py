from project.chatbot.service import ChatbotService


class DummyMessenger:
    def __init__(self):
        self.sent = []
        self.key = ""

    def send_text(self, chatroom_id, text):
        self.sent.append(("text", chatroom_id, text))
        return {"ok": True}

    def send_adaptive_card(self, chatroom_id, card):
        self.sent.append(("card", chatroom_id, card))
        return {"ok": True}

    def resolve_user_ids_from_loginids(self, login_ids):
        if not login_ids:
            return []
        return ["1001", "1002"]

    def room_create(self, receivers_userid, *, chat_type=1, chatroom_title=""):
        return 7777

    def recall_message(self, chatroom_id, msg_id, sent_time):
        self.sent.append(("recall", chatroom_id, f"{msg_id}:{sent_time}"))
        return {"ok": True}


class DummyMemory:
    def __init__(self):
        self.messages = []
        self.cleared = []

    def clear(self, scope_id):
        self.cleared.append(scope_id)

    def save_message(self, **kwargs):
        self.messages.append(kwargs)

    def load_messages(self, **kwargs):
        return [{"role": "user", "content": "이전 질문"}]

    def build_memory_text(self, memory_messages):
        return "이전 질문"

    def build_effective_question(self, **kwargs):
        return kwargs["question"], {"topic": "", "time_label": ""}

    def save_state(self, **kwargs):
        return None


class DummyDispatcher:
    def __init__(self, enqueue_ok=True):
        self.queue_full_message = "요청이 많아 잠시 후 다시 시도해주세요."
        self.jobs = []
        self.enqueue_ok = enqueue_ok

    def enqueue(self, job):
        self.jobs.append(job)
        return self.enqueue_ok

    def register_notice(self, req_id, resp):
        return None


class DummyIssueStore:
    def __init__(self):
        self.issues = []
        self.next_id = 1

    def list_issues(self, **kwargs):
        return list(self.issues)

    def create_issue(self, **kwargs):
        iid = self.next_id
        self.next_id += 1
        self.issues.insert(0, {"issue_id": iid, "title": kwargs.get("title", ""), "owner": kwargs.get("owner", "")})
        return iid

    def clear_issue(self, **kwargs):
        return True

    def get_issue(self, issue_id):
        return {"issue_id": issue_id, "title": "t", "content": "", "owner": "", "target_date": "", "url": ""}

    def update_issue(self, **kwargs):
        return True

    def list_events(self, **kwargs):
        return [{"action": "CREATE", "actor": "u", "memo": "m", "created_at": "2026-01-01"}]


class DummyWatchroomStore:
    def __init__(self):
        self.items = []

    def add_watch_room(self, **kwargs):
        self.items.append(kwargs)


class DummyQueryDef:
    description = "월 매출 조회"
    params = {"yearmonth": {"type": "yyyymm", "required": True, "aliases": ["년월"]}}


def _service(*, only_single_chat=True, allowed=True):
    memory = DummyMemory()
    return ChatbotService(
        messenger=DummyMessenger(),
        ask_fn=lambda q, memory_text="": {"answer": f"ans:{q}|mem:{memory_text}", "intent": "data_only", "request_id": "r1"},
        llm_chat_default_mode="single",
        llm_group_mention_text="@공급망 챗봇",
        llm_group_prefixes=["봇", "챗봇"],
        memory_reset_commands=["/reset"],
        only_single_chat=only_single_chat,
        is_allowed_user_fn=(lambda _s: allowed),
        memory_store=memory,
        issue_store=DummyIssueStore(),
        watchroom_store=DummyWatchroomStore(),
        term_admin_room_ids=[12345],
        warn_runner=lambda: "⚠️ 워닝 결과: 1건",
        route_ui_to_dm_for_group=True,
        query_catalog_provider=lambda: [{"id": "sales_monthly", "description": "월 매출"}],
        query_meta_provider=lambda qid: DummyQueryDef() if qid == "sales_monthly" else None,
        query_runner=lambda qid, params: {"mode": "scalar", "value": 123, "query_id": qid, "params": params},
    )


def test_service_blocks_group_when_single_only():
    svc = _service(only_single_chat=True, allowed=True)
    out = svc.handle_message({"chatroomId": 1, "chatType": "GROUP", "chatMsg": "@공급망 챗봇 안녕", "senderKnoxId": "u"})
    assert out["ok"] is True
    assert svc.messenger.sent == []


def test_service_blocks_unauthorized_user():
    svc = _service(only_single_chat=True, allowed=False)
    out = svc.handle_message({"chatroomId": 1, "chatType": "SINGLE", "chatMsg": "안녕", "senderKnoxId": "u"})
    assert out["ok"] is True
    assert len(svc.messenger.sent) == 1
    assert "권한" in svc.messenger.sent[0][2]


def test_service_answers_for_allowed_single_user():
    svc = _service(only_single_chat=True, allowed=True)
    out = svc.handle_message({"chatroomId": 1, "chatType": "SINGLE", "chatMsg": "안녕", "senderKnoxId": "u"})
    assert out["ok"] is True
    assert len(svc.messenger.sent) >= 2
    assert svc.messenger.sent[0][0] == "text"


def test_service_reset_command_clears_memory():
    svc = _service(only_single_chat=True, allowed=True)
    out = svc.handle_message({"chatroomId": 99, "chatType": "SINGLE", "chatMsg": "/reset", "senderKnoxId": "u"})
    assert out["ok"] is True
    assert "99" in svc.memory_store.cleared


def test_service_uses_async_dispatcher_when_provided():
    memory = DummyMemory()
    dispatcher = DummyDispatcher(enqueue_ok=True)
    svc = ChatbotService(
        messenger=DummyMessenger(),
        ask_fn=lambda q, memory_text="": {"answer": f"ans:{q}|mem:{memory_text}", "intent": "data_only", "request_id": "r1"},
        llm_chat_default_mode="single",
        llm_group_mention_text="@공급망 챗봇",
        llm_group_prefixes=["봇", "챗봇"],
        memory_reset_commands=["/reset"],
        only_single_chat=True,
        is_allowed_user_fn=(lambda _s: True),
        memory_store=memory,
        async_dispatcher=dispatcher,
        issue_store=DummyIssueStore(),
    )

    out = svc.handle_message({"chatroomId": 1, "chatType": "SINGLE", "chatMsg": "안녕", "senderKnoxId": "u"})
    assert out["ok"] is True
    assert len(dispatcher.jobs) == 1


def test_service_issue_form_and_create():
    svc = _service(only_single_chat=True, allowed=True)
    out1 = svc.handle_message({"chatroomId": 1, "chatType": "SINGLE", "chatMsg": "/issue", "senderKnoxId": "u"})
    assert out1["ok"] is True
    assert svc.messenger.sent[-1][0] == "card"

    payload_msg = '{"action":"ISSUE_CREATE","title":"테스트 이슈","content":"c","owner":"u","room_id":"1"}'
    out2 = svc.handle_message({"chatroomId": 1, "chatType": "SINGLE", "chatMsg": payload_msg, "senderKnoxId": "u", "senderName": "u"})
    assert out2["ok"] is True
    assert any(x[0] == "text" and "등록 완료" in x[2] for x in svc.messenger.sent)


def test_service_warn_run():
    svc = _service(only_single_chat=True, allowed=True)
    out = svc.handle_message({"chatroomId": 1, "chatType": "SINGLE", "chatMsg": "/warn", "senderKnoxId": "u"})
    assert out["ok"] is True
    assert any(x[0] == "text" and "워닝 결과" in x[2] for x in svc.messenger.sent)


def test_service_watchroom_create():
    svc = _service(only_single_chat=True, allowed=True)
    msg = '{"action":"WATCHROOM_CREATE","room_title":"공지","members":"u1,u2","note":"n"}'
    out = svc.handle_message({"chatroomId": 1, "chatType": "SINGLE", "chatMsg": msg, "senderKnoxId": "u", "senderName": "u"})
    assert out["ok"] is True
    assert any(x[0] == "text" and "공지방 생성" in x[2] for x in svc.messenger.sent)


def test_group_issue_form_routes_to_dm_room():
    svc = _service(only_single_chat=True, allowed=True)
    out = svc.handle_message({"chatroomId": 555, "chatType": "GROUP", "chatMsg": "/issue", "senderKnoxId": "u1", "senderName": "u1"})
    assert out["ok"] is True
    # UI card should be sent to DM room id created by DummyMessenger.room_create
    assert any(x[0] == "card" and x[1] == 7777 for x in svc.messenger.sent)


def test_service_query_list_and_form():
    svc = _service(only_single_chat=True, allowed=True)
    out1 = svc.handle_message({"chatroomId": 1, "chatType": "SINGLE", "chatMsg": "/query", "senderKnoxId": "u"})
    assert out1["ok"] is True
    assert any(x[0] == "card" for x in svc.messenger.sent)

    out2 = svc.handle_message({"chatroomId": 1, "chatType": "SINGLE", "chatMsg": "/query sales_monthly", "senderKnoxId": "u"})
    assert out2["ok"] is True
    assert any(x[0] == "card" and "Query 실행: sales_monthly" in str(x[2]) for x in svc.messenger.sent)


def test_service_query_run_scalar_result():
    svc = _service(only_single_chat=True, allowed=True)
    msg = '{"action":"QUERY_RUN","query_id":"sales_monthly","yearmonth":"202602"}'
    out = svc.handle_message({"chatroomId": 1, "chatType": "SINGLE", "chatMsg": msg, "senderKnoxId": "u"})
    assert out["ok"] is True
    assert any(x[0] == "card" and "결과: 123" in str(x[2]) for x in svc.messenger.sent)
