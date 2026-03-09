from __future__ import annotations

import logging
import threading
import time
from typing import Set

from ..oracle_client import ensure_oracle_client_mode
from ..settings import settings

logger = logging.getLogger("hybrid-assistant.chatbot.access")


class AllowlistService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: Set[str] = set()
        self._expire_at: float = 0.0

    def _dsn(self) -> str:
        import oracledb

        if settings.oracle_dsn:
            return settings.oracle_dsn
        return oracledb.makedsn(
            settings.oracle_host,
            settings.oracle_port,
            service_name=settings.oracle_service,
        )

    @staticmethod
    def _normalize_knox_id(value: str) -> str:
        sid = (value or "").strip().lower()
        if not sid:
            return ""
        if "\\" in sid:
            sid = sid.rsplit("\\", 1)[-1].strip()
        if "@" in sid:
            sid = sid.split("@", 1)[0].strip()
        return sid

    def _fetch_allowed_users(self) -> Set[str]:
        import oracledb

        sql = (settings.llm_allowed_users_sql or "").strip()
        if not sql:
            return set()

        out: Set[str] = set()
        ensure_oracle_client_mode()
        with oracledb.connect(
            user=settings.oracle_user,
            password=settings.oracle_password,
            dsn=self._dsn(),
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                for row in cur.fetchall():
                    if not row:
                        continue
                    sid = self._normalize_knox_id(str(row[0] or ""))
                    if sid:
                        out.add(sid)
        return out

    def is_allowed(self, sender_knox: str) -> bool:
        sid = self._normalize_knox_id(sender_knox)
        if not sid:
            return False

        now_ts = time.time()
        with self._lock:
            if now_ts < self._expire_at:
                return sid in self._cache

        try:
            allowed = self._fetch_allowed_users()
        except Exception as e:
            logger.exception("allowlist fetch failed: %s", e)
            # DB 장애 시 stale cache fallback
            with self._lock:
                if self._cache:
                    self._expire_at = now_ts + 60.0
                    return sid in self._cache
                # 캐시가 없는 상태에서 조회 실패 시 빈 목록을 장시간 캐시하지 않는다.
                self._expire_at = now_ts + 10.0
            return False

        with self._lock:
            self._cache = allowed
            self._expire_at = now_ts + max(0, int(settings.llm_allowed_users_cache_ttl_sec))
            ok = sid in self._cache
            logger.info("allowlist refreshed count=%d target=%s allowed=%s", len(self._cache), sid, ok)
            return ok
