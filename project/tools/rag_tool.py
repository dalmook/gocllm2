from __future__ import annotations

import re
from typing import Any, Dict, List


class RagTool:
    """Wrap existing RAG. Replace stubs with real integrations."""

    def search(self, query: str, top_k: int = 5, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        # TODO: bind to existing mail/doc RAG function
        return [
            {
                "title": "RAG stub result",
                "link": "",
                "snippet": f"query={query}",
                "meta": {"top_k": top_k, "filters": filters or {}},
            }
        ]

    def extract_entities(self, docs: List[Dict[str, Any]], schema: List[str]) -> Dict[str, Any]:
        text = "\n".join(str(d.get("snippet", "")) for d in docs)
        out: Dict[str, Any] = {}

        if "version" in schema:
            m = re.search(r"\b([A-Za-z]{1,10}[0-9_-]{0,10})\s*버전\b", text, re.IGNORECASE)
            if m:
                out["version"] = m.group(1).upper()

        if "yearmonth" in schema:
            m = re.search(r"\b(20\d{2})(0[1-9]|1[0-2])\b", text)
            if m:
                out["yearmonth"] = f"{m.group(1)}{m.group(2)}"

        if "keywords" in schema:
            kws = []
            for kw in ("FLASH", "WC", "HBM"):
                if kw.lower() in text.lower():
                    kws.append(kw)
            out["keywords"] = kws

        return out
