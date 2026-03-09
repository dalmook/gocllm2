from __future__ import annotations

import threading

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
        lib_dir = (settings.oracle_client_lib_dir or "").strip() or r"C:\instantclient"
        kwargs["lib_dir"] = lib_dir
        if (settings.oracle_client_config_dir or "").strip():
            kwargs["config_dir"] = settings.oracle_client_config_dir.strip()

        try:
            import oracledb
            oracledb.init_oracle_client(**kwargs)
        except Exception as e:
            raise RuntimeError(
                f"Oracle thick mode init failed. lib_dir={kwargs.get('lib_dir', '')} error={e}"
            ) from e

        _initialized = True
