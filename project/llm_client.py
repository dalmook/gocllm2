from __future__ import annotations

import json
import uuid
from typing import Any, Dict

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from .settings import settings


class LLMClient:
    def __init__(self) -> None:
        self.enabled = bool(settings.llm_base_url and settings.llm_model)
        self._client = None
        if self.enabled:
            headers = {
                "x-dep-ticket": settings.llm_api_key,
                "Send-System-Name": settings.llm_send_system_name,
                "User-Id": "hybrid-assistant",
                "User-Type": settings.llm_user_type,
                "Prompt-Msg-Id": str(uuid.uuid4()),
                "Completion-Msg-Id": str(uuid.uuid4()),
            }
            self._client = ChatOpenAI(
                base_url=settings.llm_base_url,
                model=settings.llm_model,
                temperature=0.0,
                max_tokens=800,
                default_headers=headers,
            )

    def invoke_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        if not self._client:
            raise RuntimeError("LLM client is not configured")
        resp = self._client.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        txt = (resp.content or "").strip()
        return json.loads(txt)

    def invoke_text(self, system_prompt: str, user_prompt: str) -> str:
        if not self._client:
            raise RuntimeError("LLM client is not configured")
        resp = self._client.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        return (resp.content or "").strip()
