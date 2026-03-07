from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Hybrid RAG+DB Assistant")
    app_env: str = os.getenv("APP_ENV", "dev")
    timezone: str = os.getenv("APP_TIMEZONE", "Asia/Seoul")

    # planner llm
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://apigw.samsungds.net:8000/model-23/1/gausso4-instruct/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "credential:TICKET-96f7bce0-efab-4516-8e62-5501b07ab43c:ST0000107488-PROD:CTXLCkSDRGWtI5HdVHkPAQgol2o-RyQiq2I1vCHHOgGw:-1:Q1RYTENrU0RSR1d0STVIZFZIa1BBUWdvbDJvLVJ5UWlxMkkxdkNISE9nR3c=:signature=eRa1UcfmWGfKTDBt-Xnz2wFhW0OvMX0WESZUpoNVgCA5uNVgpgax59LZ3osPOp8whnZwQay8s5TUvxJGtmsCD9iK-HpcsyUOcE5P58W0Weyg-YQ3KRTWFiA==")
    llm_model: str = os.getenv("LLM_MODEL", "GaussO4-instruct")
    llm_send_system_name: str = os.getenv("LLM_SEND_SYSTEM_NAME", "GOC_MAIL_RAG_PIPELINE")
    llm_user_type: str = os.getenv("LLM_USER_TYPE", "AD_ID")

    # oracle
    oracle_host: str = os.getenv("ORACLE_HOST", "gmgsdd09-vip.sec.samsung.net")
    oracle_port: int = int(os.getenv("ORACLE_PORT", "2541"))
    oracle_service: str = os.getenv("ORACLE_SERVICE", "MEMSCM")
    oracle_user: str = os.getenv("ORACLE_USER", "memscm")
    oracle_password: str = os.getenv("ORACLE_PW", os.getenv("ORACLE_PASSWORD", "mem01scm"))
    oracle_dsn: str = os.getenv("ORACLE_DSN", "")

    query_dir: str = os.getenv("QUERY_DIR", "project/query_registry/queries")


settings = Settings()
