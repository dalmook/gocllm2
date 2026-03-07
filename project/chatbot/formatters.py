from __future__ import annotations

import re


def format_for_knox_text(text: str) -> str:
    t = (text or "").replace("\r\n", "\n")
    t = re.sub(r"(?m)^###\\s*", "📌 ", t)
    t = re.sub(r"(?m)^##\\s*", "📍 ", t)
    t = re.sub(r"(?m)^#\\s*", "📍 ", t)
    t = t.replace("**", "").replace("__", "").replace("`", "")
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t
