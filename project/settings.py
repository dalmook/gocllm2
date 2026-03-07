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
    oracle_force_thick_mode: bool = os.getenv("ORACLE_FORCE_THICK_MODE", "true").lower() == "true"
    oracle_client_lib_dir: str = os.getenv("ORACLE_CLIENT_LIB_DIR", r"C:\instantclient")
    oracle_client_config_dir: str = os.getenv("ORACLE_CLIENT_CONFIG_DIR", "")

    # query catalog
    query_dir: str = os.getenv("QUERY_DIR", "project/query_registry/queries")

    # knox chatbot
    knox_host: str = os.getenv("KNOX_HOST", "https://openapi.samsung.net")
    knox_system_id: str = os.getenv("KNOX_SYSTEM_ID", "")
    knox_token: str = os.getenv("KNOX_TOKEN", "")
    knox_verify_ssl: bool = os.getenv("VERIFY_SSL", "false").lower() == "true"
    llm_chat_default_mode: str = os.getenv("LLM_CHAT_DEFAULT_MODE", "single")
    llm_group_mention_text: str = os.getenv("LLM_GROUP_MENTION_TEXT", "@공급망 챗봇")
    llm_group_prefixes_csv: str = os.getenv("LLM_GROUP_PREFIXES", "봇,챗봇")
    memory_reset_commands_csv: str = os.getenv("MEMORY_RESET_COMMANDS", "/reset,기억초기화,대화초기화")
    enable_conversation_memory: bool = os.getenv("ENABLE_CONVERSATION_MEMORY", "true").lower() == "true"
    memory_only_single: bool = os.getenv("MEMORY_ONLY_SINGLE", "true").lower() == "true"
    memory_max_turns: int = int(os.getenv("MEMORY_MAX_TURNS", "4"))
    memory_max_chars_per_message: int = int(os.getenv("MEMORY_MAX_CHARS_PER_MESSAGE", "300"))
    memory_summarize_assistant: bool = os.getenv("MEMORY_SUMMARIZE_ASSISTANT", "true").lower() == "true"
    enable_conversation_state: bool = os.getenv("ENABLE_CONVERSATION_STATE", "true").lower() == "true"
    memory_db_path: str = os.getenv("MEMORY_DB_PATH", "")
    issue_db_path: str = os.getenv("ISSUE_DB_PATH", "")
    llm_only_single_chat: bool = os.getenv("LLM_ONLY_SINGLE_CHAT", "true").lower() == "true"
    llm_allowed_users_sql: str = os.getenv(
        "LLM_ALLOWED_USERS_SQL",
        "SELECT SSO_ID FROM SCM_WP.T_T_FOR_MASTER A WHERE 1=1 AND a.sso_id in ('hy73.park','cheon.kim','suy.kim','kyungchan.seong','jh3.park','junsoo.jung','jjlive.kim','jc2573.lee','hs1979.kim','sunok78.han','sungmook.cho','hsung.chae','sj82.han','w2635.lee','sung.w.jung') AND A.DEPT_NAME LIKE '%메모리%' and a.POSITION_CODE is not null AND A.SSO_ID NOT IN ('SCM.RPA','SCM 봇','메모리STO2','메모리 STO','dalbong.chatbot01', 'dalbongbot01', 'dalbong.bot01', 'command.center', 'thatcoolguy')",
    )
    llm_allowed_users_cache_ttl_sec: int = int(os.getenv("LLM_ALLOWED_USERS_CACHE_TTL_SEC", "1800"))
    llm_workers: int = int(os.getenv("LLM_WORKERS", "4"))
    llm_job_queue_max: int = int(os.getenv("LLM_JOB_QUEUE_MAX", "200"))
    llm_max_concurrent: int = int(os.getenv("LLM_MAX_CONCURRENT", "4"))
    llm_busy_message: str = os.getenv("LLM_BUSY_MESSAGE", "지금 답변 생성 중입니다. 완료 후 다시 질문해주세요.")
    llm_queue_full_message: str = os.getenv("LLM_QUEUE_FULL_MESSAGE", "요청이 많아 잠시 후 다시 시도해주세요.")
    llm_long_wait_delay_sec: float = float(os.getenv("LLM_LONG_WAIT_DELAY_SEC", "6.0"))
    enable_recall: bool = os.getenv("ENABLE_RECALL", "false").lower() == "true"


settings = Settings()
