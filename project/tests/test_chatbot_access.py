from project.chatbot.access import AllowlistService


class FakeAllowlist(AllowlistService):
    def __init__(self, *, first_set=None, fail=False):
        super().__init__()
        self.first_set = first_set or set()
        self.fail = fail

    def _fetch_allowed_users(self):
        if self.fail:
            raise RuntimeError("db down")
        return set(self.first_set)


def test_allowlist_stale_cache_fallback_on_db_error():
    svc = FakeAllowlist(first_set={"user.a"}, fail=False)
    assert svc.is_allowed("user.a") is True

    svc.fail = True
    assert svc.is_allowed("user.a") is True


def test_allowlist_normalizes_sender_formats():
    svc = FakeAllowlist(first_set={"sungmook.cho"}, fail=False)
    assert svc.is_allowed("sungmook.cho") is True
    assert svc.is_allowed("SUNGMOOK.CHO@samsung.com") is True
    assert svc.is_allowed("SEC\\sungmook.cho") is True
