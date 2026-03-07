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
    )

    out = svc.handle_message({"chatroomId": 1, "chatType": "SINGLE", "chatMsg": "안녕", "senderKnoxId": "u"})
    assert out["ok"] is True
    assert len(dispatcher.jobs) == 1
