from __future__ import annotations

import threading
import time
from typing import Set

import oracledb

from ..oracle_client import ensure_oracle_client_mode
from ..settings import settings


class AllowlistService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: Set[str] = set()
        self._expire_at: float = 0.0

    def _dsn(self) -> str:
        if settings.oracle_dsn:
            return settings.oracle_dsn
        return oracledb.makedsn(
            settings.oracle_host,
            settings.oracle_port,
            service_name=settings.oracle_service,
        )

    def _fetch_allowed_users(self) -> Set[str]:
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
                    sid = str(row[0] or "").strip().lower()
                    if sid:
                        out.add(sid)
        return out

    def is_allowed(self, sender_knox: str) -> bool:
        sid = (sender_knox or "").strip().lower()
        if not sid:
            return False

        now_ts = time.time()
        with self._lock:
            if now_ts < self._expire_at:
                return sid in self._cache

        try:
            allowed = self._fetch_allowed_users()
        except Exception:
            # DB 장애 시 fail-closed 유지
            allowed = set()

        with self._lock:
            self._cache = allowed
            self._expire_at = now_ts + max(0, int(settings.llm_allowed_users_cache_ttl_sec))
            return sid in self._cache
