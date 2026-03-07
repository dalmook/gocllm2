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


def _service(*, only_single_chat=True, allowed=True):
    return ChatbotService(
        messenger=DummyMessenger(),
        ask_fn=lambda q: {"answer": f"ans:{q}", "intent": "data_only", "request_id": "r1"},
        llm_chat_default_mode="single",
        llm_group_mention_text="@공급망 챗봇",
        llm_group_prefixes=["봇", "챗봇"],
        memory_reset_commands=["/reset"],
        only_single_chat=only_single_chat,
        is_allowed_user_fn=(lambda _s: allowed),
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
