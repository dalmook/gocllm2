from __future__ import annotations

import json
import re
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
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                temperature=0.0,
                max_tokens=800,
                default_headers=headers,
            )

    def _strip_json_wrappers(self, txt: str) -> str:
        s = (txt or "").strip()
        if s.startswith("```"):
            s = re.sub(r"^```(?:json)?\\s*", "", s, flags=re.IGNORECASE)
            s = re.sub(r"\\s*```$", "", s)
        return s.strip()

    def invoke_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        if not self._client:
            raise RuntimeError("LLM client is not configured")

        last_err: Exception | None = None
        for _ in range(2):
            try:
                resp = self._client.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ])
                txt = self._strip_json_wrappers((resp.content or ""))
                return json.loads(txt)
            except Exception as e:
                last_err = e
                continue

        raise ValueError(f"invalid LLM JSON response: {last_err}")

    def invoke_text(self, system_prompt: str, user_prompt: str) -> str:
        if not self._client:
            raise RuntimeError("LLM client is not configured")
        resp = self._client.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        return (resp.content or "").strip()
