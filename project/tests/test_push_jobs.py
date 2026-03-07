from project.chatbot.push_jobs import PushJobManager


class DummyWatchStore:
    def list_rooms(self):
        return [{"room_id": "101"}, {"room_id": "bad"}, {"room_id": "202"}]


class DummyIssueStore:
    def list_issues(self, *, scope_room_id, status="OPEN", limit=10):
        if scope_room_id == "101":
            return [{"issue_id": 1, "title": "t1", "owner": "o1"}]
        return []


def test_push_job_manager_issue_and_warn_once():
    sent = []

    mgr = PushJobManager(
        watchroom_store=DummyWatchStore(),
        issue_store=DummyIssueStore(),
        send_text_fn=lambda rid, msg: sent.append((rid, msg)),
        warn_message_fn=lambda: "warn-msg",
        issue_summary_hhmm="00:00",
        warn_hhmm="00:00",
    )

    mgr.run_issue_summary_once()
    mgr.run_warn_once()

    room_ids = [x[0] for x in sent]
    assert 101 in room_ids
    assert 202 in room_ids
    assert all(rid in (101, 202) for rid in room_ids)
    assert any("이슈 요약" in msg for _, msg in sent)
    assert any(msg == "warn-msg" for _, msg in sent)
