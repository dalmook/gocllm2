from __future__ import annotations

import threading

import oracledb

from .settings import settings

_init_lock = threading.Lock()
_initialized = False


def ensure_oracle_client_mode() -> None:
    """Initialize Oracle thick mode once if configured."""
    global _initialized
    if _initialized:
        return

    if not settings.oracle_force_thick_mode:
        _initialized = True
        return

    with _init_lock:
        if _initialized:
            return

        kwargs = {}
        if (settings.oracle_client_lib_dir or "").strip():
            kwargs["lib_dir"] = settings.oracle_client_lib_dir.strip()
        if (settings.oracle_client_config_dir or "").strip():
            kwargs["config_dir"] = settings.oracle_client_config_dir.strip()

        try:
            oracledb.init_oracle_client(**kwargs)
        except Exception as e:
            raise RuntimeError(
                f"Oracle thick mode init failed. lib_dir={kwargs.get('lib_dir', '')} error={e}"
            ) from e

        _initialized = True
