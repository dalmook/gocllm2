from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


def resolve_quick_link(key: str, aliases: List[Tuple[List[str], str, str]]) -> tuple[str | None, str | None]:
    k = (key or "").strip().upper()
    for names, title, url in aliases:
        if k in [x.upper() for x in names]:
            return title, url
    return None, None


def extract_group_llm_question(txt: str, mention_text: str, prefixes: List[str]) -> str:
    text = (txt or "").strip()
    if not text:
        return ""

    mention = (mention_text or "").strip()
    if mention and text.startswith(mention):
        return text[len(mention):].strip(" :")

    for prefix in prefixes:
        pfx = (prefix or "").strip()
        if not pfx:
            continue
        if text.startswith(pfx):
            return text[len(pfx):].strip(" :")
        if text.startswith(pfx + ",") or text.startswith(pfx + ":"):
            return text[len(pfx) + 1:].strip()

    return ""


def parse_action_payload(
    info: Dict[str, Any],
    *,
    llm_chat_default_mode: str,
    llm_group_mention_text: str,
    llm_group_prefixes: List[str],
    memory_reset_commands: List[str],
    quick_link_aliases: List[Tuple[List[str], str, str]],
) -> Tuple[str, Dict[str, Any]]:
    chat_msg = info.get("chatMsg", "") or ""
    raw = chat_msg
    if " -->" in chat_msg:
        raw = chat_msg.split(" -->", 1)[1].strip()

    if raw.strip().startswith("{"):
        try:
            payload = json.loads(raw)
            return payload.get("action", "HOME"), payload
        except Exception:
            pass

    txt = raw.strip()
    txt_u = txt.upper()
    chat_type = (info.get("chatType") or "").upper()

    if txt_u in ("INTRO", "HOME") or txt in ("홈", "/home"):
        return "INTRO", {}
    if txt in ("바로가기", "/바로가기", "링크", "/links", "links"):
        return "QUICK_LINKS", {}
    if txt.startswith("/warn"):
        return "WARN_RUN", {}
    if txt.startswith("/watchroom") or txt.startswith("/watch"):
        return "WATCHROOM_FORM", {}
    if txt.startswith("/issue"):
        if txt.strip() in ("/issue", "/issue form"):
            return "ISSUE_FORM", {}
        if txt.strip() in ("/issues", "/issue list"):
            return "ISSUE_LIST", {}

    if chat_type == "SINGLE":
        key = txt_u[1:] if txt_u.startswith("/") else txt_u
        title, url = resolve_quick_link(key, quick_link_aliases)
        if url:
            return "OPEN_URL", {"title": title, "url": url}

    if chat_type == "SINGLE":
        if txt.startswith("/ask "):
            return "LLM_CHAT", {"question": txt[5:].strip()}
        if txt.startswith("질문:"):
            return "LLM_CHAT", {"question": txt[3:].strip()}
        if txt in memory_reset_commands:
            return "LLM_CHAT", {"question": txt}
        if not txt.startswith("/"):
            return "LLM_CHAT", {"question": txt}
        return "NOOP", {}

    if chat_type == "GROUP":
        mode = (llm_chat_default_mode or "single").lower().strip()
        if mode == "all" and not txt.startswith("/"):
            return "LLM_CHAT", {"question": txt}
        if mode == "mention":
            q = extract_group_llm_question(txt, llm_group_mention_text, llm_group_prefixes)
            if q:
                return "LLM_CHAT", {"question": q}

    return "NOOP", {}
