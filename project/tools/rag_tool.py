from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

logger = logging.getLogger("hybrid-assistant.rag")

RAG_DEP_TICKET = os.getenv(
    "RAG_DEP_TICKET",
    "credential:TICKET-e09692e2-45e3-46e7-ab4d-e75c06ef2b47:ST0000106045-PROD:n591JsqkTh-51wynrJeZ3Qbk2a5Oo2TfGDc9P6pAkN9Q:-1:bjU5MUpzcWtUaC01MXd5bnJKZVozUWJrMmE1T28yVGZHRGM5UDZwQWtOOVE=:signature=x-Dh7diDnQqQAVyfObfHxQoqHxyH7zGC4irZ9vA0Wgfi9zNURR853sMEXG5QcMnYUHXCclma5dGSMwDWSOgGQBvesPSHRz3zvarPfkcFqovLv6OgNZw_X5A==",
)
RAG_API_KEY = os.getenv(
    "RAG_API_KEY",
    "rag-laeeKyA.KazNAgzjr-d1iK9rUClS2vdqKLZ4oOOcsOhhuR3tJaAYa3h73BE7SdjgLjxQsEtJCN6Oc7B1mJYq1Pu_ruTKmcmeujAVpmDxms44OdjGCeHGBTisaSFHdqyepsbEa3nw",
)
RAG_BASE_URL = os.getenv("RAG_BASE_URL", "http://apigw.samsungds.net:8000/ds_llm_rag/2/dsllmrag/elastic/v2")
RAG_INDEXES = os.getenv("RAG_INDEXES", "rp-gocinfo_mail_jsonl,glossary_m3_100chunk50")
RAG_PERMISSION_GROUPS = os.getenv("RAG_PERMISSION_GROUPS", "rag-public")
RAG_RETRIEVE_MODE = os.getenv("RAG_RETRIEVE_MODE", "hybrid").lower()
RAG_BM25_BOOST = float(os.getenv("RAG_BM25_BOOST", "0.025"))
RAG_KNN_BOOST = float(os.getenv("RAG_KNN_BOOST", "7.98"))
RAG_API_MAX_NUM_RESULT_DOC = int(os.getenv("RAG_API_MAX_NUM_RESULT_DOC", "100"))
RAG_TIMEOUT_SEC = int(os.getenv("RAG_TIMEOUT_SEC", "20"))


def _sanitize_query(query: str) -> str:
    cleaned = re.sub(r"[\x00-\x1F\x7F]", " ", query or "")
    cleaned = re.sub(r"[^\w\sㄱ-ㅎ가-힣]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _parse_permission_groups(raw: str) -> List[str]:
    groups = [x.strip() for x in (raw or "").split(",") if x.strip()]
    return groups or ["rag-public"]


def _pick_best_source(doc: Dict[str, Any]) -> str:
    for key in (
        "summary",
        "snippet",
        "content",
        "text",
        "body",
        "description",
        "merge_title_content",
        "chunk_text",
        "page_content",
        "mail_body",
        "body_text",
        "document_text",
    ):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _pick_best_title(doc: Dict[str, Any]) -> str:
    for key in ("title", "subject", "name", "doc_title", "file_name"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _pick_best_link(doc: Dict[str, Any]) -> str:
    for key in ("link", "url", "source_url", "doc_url"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


class RagClient:
    def __init__(self, api_key: str, dep_ticket: str, base_url: str, timeout: int = RAG_TIMEOUT_SEC):
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout
        self.sess = requests.Session()

        headers = {"Content-Type": "application/json"}
        if dep_ticket:
            headers["x-dep-ticket"] = dep_ticket
        if api_key:
            headers["api-key"] = api_key
        self.sess.headers.update(headers)

    def retrieve(
        self,
        index_name: str,
        query_text: str,
        *,
        mode: str = "hybrid",
        num_result_doc: int = 5,
        permission_groups: List[str] | None = None,
        filter: Dict[str, Any] | None = None,
        bm25_boost: float | None = None,
        knn_boost: float | None = None,
    ) -> Dict[str, Any]:
        endpoint_map = {
            "bm25": "/retrieve-bm25",
            "knn": "/retrieve-knn",
            "hybrid": "/retrieve-rrf",
            "weighted_hybrid": "/retrieve-weighted-hybrid",
        }
        selected_mode = mode if mode in endpoint_map else "hybrid"
        url = f"{self.base_url}{endpoint_map[selected_mode]}"

        payload: Dict[str, Any] = {
            "index_name": index_name,
            "permission_groups": permission_groups or ["rag-public"],
            "query_text": query_text,
            "num_result_doc": num_result_doc,
        }
        if filter:
            payload["filter"] = filter
        if selected_mode == "weighted_hybrid":
            if bm25_boost is not None:
                payload["bm25_boost"] = bm25_boost
            if knn_boost is not None:
                payload["knn_boost"] = knn_boost

        resp = self.sess.post(url, data=json.dumps(payload, ensure_ascii=False), timeout=self.timeout)
        if 200 <= resp.status_code < 300:
            return resp.json()
        raise RuntimeError(f"RAG API error: {resp.status_code} {resp.text}")


class RagTool:
    """RAG wrapper used by executor."""

    def search(self, query: str, top_k: int = 5, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        sanitized_query = _sanitize_query(query)
        if not sanitized_query:
            return []

        if not RAG_BASE_URL:
            return []

        num_result_doc = min(max(1, int(top_k or 5)), max(1, RAG_API_MAX_NUM_RESULT_DOC))
        indexes = [x.strip() for x in RAG_INDEXES.split(",") if x.strip()]
        permission_groups = _parse_permission_groups(RAG_PERMISSION_GROUPS)
        rag = RagClient(api_key=RAG_API_KEY, dep_ticket=RAG_DEP_TICKET, base_url=RAG_BASE_URL)

        all_results: List[Dict[str, Any]] = []
        errors: List[str] = []
        for index in indexes:
            try:
                response = rag.retrieve(
                    index_name=index,
                    query_text=sanitized_query,
                    mode=RAG_RETRIEVE_MODE,
                    num_result_doc=num_result_doc,
                    permission_groups=permission_groups,
                    filter=filters or None,
                    bm25_boost=RAG_BM25_BOOST,
                    knn_boost=RAG_KNN_BOOST,
                )
            except Exception as e:
                errors.append(f"{index}: {e}")
                logger.warning("RAG retrieve failed index=%s err=%s", index, e)
                continue

            hits = (response.get("hits") or {}).get("hits", []) if isinstance(response, dict) else []
            for hit in hits:
                source = hit.get("_source") if isinstance(hit, dict) else {}
                if not isinstance(source, dict):
                    continue
                all_results.append(
                    {
                        "title": _pick_best_title(source),
                        "link": _pick_best_link(source),
                        "snippet": _pick_best_source(source),
                        "meta": {
                            "index": index,
                            "score": hit.get("_score", 0.0),
                            "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        },
                        "_source": source,
                    }
                )

        all_results.sort(key=lambda x: float((x.get("meta") or {}).get("score", 0.0)), reverse=True)
        if not all_results and errors:
            raise RuntimeError(f"RAG retrieval failed for all indexes: {' | '.join(errors)}")
        logger.info(
            "RAG search done query=%s indexes=%s results=%s errors=%s",
            sanitized_query,
            indexes,
            len(all_results),
            len(errors),
        )
        return all_results[:num_result_doc]

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
