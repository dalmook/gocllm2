from __future__ import annotations

import json
import logging
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

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

RAG_NUM_RESULT_DOC = int(os.getenv("RAG_NUM_RESULT_DOC", "3"))
RAG_CONTEXT_DOCS = int(os.getenv("RAG_CONTEXT_DOCS", "2"))
RAG_TEMPORAL_NUM_RESULT_DOC = int(os.getenv("RAG_TEMPORAL_NUM_RESULT_DOC", "20"))
RAG_REWRITE_QUERY_COUNT = max(1, int(os.getenv("RAG_REWRITE_QUERY_COUNT", "1")))
MAX_RAG_QUERIES = max(1, int(os.getenv("MAX_RAG_QUERIES", "1")))
RAG_INCLUDE_ORIGINAL_QUERY = os.getenv("RAG_INCLUDE_ORIGINAL_QUERY", "true").lower() == "true"

RAG_SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.35"))
RAG_MIN_COMBINED_SCORE = float(os.getenv("RAG_MIN_COMBINED_SCORE", str(RAG_SIMILARITY_THRESHOLD)))
RAG_MIN_KEYWORD_HITS = int(os.getenv("RAG_MIN_KEYWORD_HITS", "1"))
RAG_RECENCY_WEIGHT = float(os.getenv("RAG_RECENCY_WEIGHT", "0.28"))
RAG_RECENCY_HALF_LIFE_DAYS = float(os.getenv("RAG_RECENCY_HALF_LIFE_DAYS", "30"))
RAG_MIN_RECENCY_SCORE = float(os.getenv("RAG_MIN_RECENCY_SCORE", "0.15"))

GLOSSARY_RAG_ENABLE = os.getenv("GLOSSARY_RAG_ENABLE", "true").lower() == "true"
MAIL_INDEX_NAME = os.getenv("MAIL_INDEX_NAME", "rp-gocinfo_mail_jsonl")
GLOSSARY_INDEX_NAME = os.getenv("GLOSSARY_INDEX_NAME", "glossary_m3_100chunk50")
GLOSSARY_TOPK_MATCH = int(os.getenv("GLOSSARY_TOPK_MATCH", "3"))
GLOSSARY_THRESHOLD = float(os.getenv("GLOSSARY_THRESHOLD", "0.35"))

BUSINESS_SPLIT_KEYWORDS = ["주간", "이슈", "정리", "요약", "현황", "리스크", "대응", "이번주", "저번주", "지난주"]
MAIL_STRONG_INTENT_KEYWORDS = ["이슈", "정리", "요약", "현황", "주간", "이번주", "저번주", "지난주", "최신", "최근", "업데이트"]
GLOSSARY_INTENT_KEYWORDS = ["뭐야", "뜻", "의미", "정의", "약자", "약어", "용어", "무슨 뜻"]
RECENT_PRIORITY_KEYWORDS = ["최신", "최근", "요즘", "근래", "업데이트", "이번주", "금주", "최근이슈", "최신이슈", "주요이슈", "이슈정리"]
ISSUE_SUMMARY_KEYWORDS = ["이슈", "정리", "요약", "현황", "동향", "업데이트", "주요"]

DATE_FIELD_CANDIDATES = [
    "created_time",
    "last_modified_time",
    "updated_time",
    "modified_time",
    "updated_at",
    "updated_date",
    "last_updated",
    "last_modified",
    "modified_at",
    "modified_date",
    "created_at",
    "created_date",
    "register_date",
    "reg_date",
    "date",
    "datetime",
    "timestamp",
    "mail_date",
    "page_updated_at",
    "page_created_at",
]


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


def _sanitize_query(query: str) -> str:
    cleaned = re.sub(r"[\x00-\x1F\x7F]", " ", query or "")
    cleaned = re.sub(r"[^\w\sㄱ-ㅎ가-힣]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _parse_permission_groups(raw: str) -> List[str]:
    groups = [x.strip() for x in (raw or "").split(",") if x.strip()]
    return groups or ["rag-public"]


def normalize_query_for_search(question: str) -> str:
    q = (question or "").strip()
    if not q:
        return ""
    q = re.sub(r"([A-Za-z0-9])([가-힣])", r"\1 \2", q)
    q = re.sub(r"([가-힣])([A-Za-z0-9])", r"\1 \2", q)
    for kw in sorted(BUSINESS_SPLIT_KEYWORDS, key=len, reverse=True):
        q = re.sub(rf"\s*{re.escape(kw)}\s*", f" {kw} ", q)
    return re.sub(r"\s+", " ", q).strip()


def _normalize_text_for_match(s: str) -> str:
    s = (s or "").lower().strip()
    for ch in [" ", "\n", "\t", ",", ".", ":", ";", "/", "\\", "(", ")", "[", "]", "{", "}", "-", "_", "?", "!"]:
        s = s.replace(ch, " ")
    return " ".join(s.split())


def _extract_query_keywords(question: str) -> List[str]:
    q = _normalize_text_for_match(normalize_query_for_search(question))
    toks = [t for t in q.split() if len(t) >= 2]
    stopwords = {"오늘", "어때", "뭐야", "알려줘", "조회", "관련", "대한", "해줘", "설명", "the", "is", "are", "what", "when", "how", "why", "please"}
    return [t for t in toks if t not in stopwords]


def has_strong_mail_intent(question: str) -> bool:
    q_compact = re.sub(r"\s+", "", question or "")
    return any(kw in q_compact for kw in MAIL_STRONG_INTENT_KEYWORDS)


def is_issue_summary_intent(question: str) -> bool:
    q_compact = re.sub(r"\s+", "", question or "")
    hits = sum(1 for kw in ISSUE_SUMMARY_KEYWORDS if kw in q_compact)
    return hits >= 2 or ("이슈" in q_compact and any(k in q_compact for k in ("정리", "요약", "현황")))


def should_prioritize_recent_docs(question: str) -> bool:
    q_norm = _normalize_text_for_match(question)
    if not q_norm:
        return False
    compact = q_norm.replace(" ", "")
    return any(k in compact for k in RECENT_PRIORITY_KEYWORDS)


def is_glossary_doc(doc: Dict[str, Any]) -> bool:
    return doc.get("_index", "") == GLOSSARY_INDEX_NAME


def is_glossary_intent(question: str) -> bool:
    q = (question or "").strip()
    if not q:
        return False
    if has_strong_mail_intent(q):
        return False
    q_norm = _normalize_text_for_match(q)
    if any(kw in q_norm for kw in GLOSSARY_INTENT_KEYWORDS):
        return True
    if re.search(r"\b[A-Z]{2,8}\b", q):
        return True
    return False


def is_force_glossary_query(question: str) -> bool:
    q_norm = _normalize_text_for_match(question)
    if not q_norm:
        return False
    compact = q_norm.replace(" ", "")
    return any(p in compact for p in ["용어검색", "용어알려", "용어설명", "용어뜻", "약어검색", "약어설명"])


def is_rag_result_relevant(question: str, top_docs: List[Dict[str, Any]]) -> bool:
    if not top_docs:
        return False
    top1 = top_docs[0]
    top_score = float(top1.get("_combined_score") or 0.0)

    title = str(top1.get("title") or "")
    content = str(top1.get("content") or top1.get("merge_title_content") or "")
    haystack = _normalize_text_for_match(title + " " + content)

    keywords = _extract_query_keywords(question)
    keyword_hits = sum(1 for kw in keywords if kw in haystack)

    noisy_title = title.strip().upper().startswith(("FW:", "RE:"))
    effective_threshold = max(RAG_SIMILARITY_THRESHOLD, RAG_MIN_COMBINED_SCORE)
    if top_score < effective_threshold:
        return False
    if keyword_hits < RAG_MIN_KEYWORD_HITS and noisy_title:
        return False
    if keywords and keyword_hits == 0:
        return False
    return True


def is_glossary_result_relevant(question: str, docs: List[Dict[str, Any]], *, topk: int = 3, min_score: float = 0.35) -> bool:
    if not docs:
        return False
    gdocs = [d for d in docs if is_glossary_doc(d)]
    if not gdocs:
        return False

    target_docs = gdocs[:max(1, topk)]
    keywords = _extract_query_keywords(question)
    abbreviations = re.findall(r"\b[A-Z]{2,8}\b", question or "")

    for doc in target_docs:
        combined_score = float(doc.get("_combined_score") or 0.0)
        if combined_score < min_score:
            continue
        title = str(doc.get("title") or "")
        content = str(doc.get("content") or doc.get("merge_title_content") or "")
        haystack = _normalize_text_for_match(title + " " + content)
        if any(abbr.lower() in haystack for abbr in abbreviations):
            return True
        if any(kw in haystack for kw in keywords):
            return True
    return False


def _parse_doc_datetime_value(v: Any) -> Optional[datetime]:
    if v in (None, "", 0):
        return None
    if isinstance(v, (int, float)):
        try:
            ts = float(v)
            if ts > 1_000_000_000_000:
                ts = ts / 1000.0
            if ts > 0:
                return datetime.fromtimestamp(ts, tz=ZoneInfo("Asia/Seoul"))
        except Exception:
            pass
    s = str(v).strip()
    if not s:
        return None
    s_norm = s.replace("Z", "+00:00").replace("/", "-").replace(".", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d"):
        try:
            dt = datetime.strptime(s_norm, fmt)
            return dt.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        except Exception:
            pass
    try:
        dt = datetime.fromisoformat(s_norm)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        return dt
    except Exception:
        return None


def _extract_doc_datetime(doc: Dict[str, Any]) -> Optional[datetime]:
    if not isinstance(doc, dict):
        return None
    for key in DATE_FIELD_CANDIDATES:
        if key in doc:
            dt = _parse_doc_datetime_value(doc.get(key))
            if dt:
                return dt
    meta = doc.get("metadata")
    if isinstance(meta, dict):
        for key in DATE_FIELD_CANDIDATES:
            if key in meta:
                dt = _parse_doc_datetime_value(meta.get(key))
                if dt:
                    return dt
    for k, v in doc.items():
        lk = str(k).lower()
        if any(token in lk for token in ("date", "time", "updated", "modified", "created", "ts")):
            dt = _parse_doc_datetime_value(v)
            if dt:
                return dt
    return None


def _get_week_range(base_dt: datetime, week_offset: int = 0) -> Tuple[datetime, datetime]:
    tz = ZoneInfo("Asia/Seoul")
    if base_dt.tzinfo is None:
        base_dt = base_dt.replace(tzinfo=tz)
    base_dt = base_dt.astimezone(tz)
    monday = (base_dt - timedelta(days=base_dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start = monday + timedelta(days=7 * week_offset)
    end = start + timedelta(days=7)
    return start, end


def _get_month_range(year: int, month: int) -> Optional[Tuple[datetime, datetime]]:
    if month < 1 or month > 12:
        return None
    tz = ZoneInfo("Asia/Seoul")
    start = datetime(year, month, 1, tzinfo=tz)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=tz)
    else:
        end = datetime(year, month + 1, 1, tzinfo=tz)
    return start, end


def _extract_time_range_from_question(question: str) -> Optional[Dict[str, Any]]:
    q_raw = (question or "").strip()
    if not q_raw:
        return None
    q_compact = q_raw.replace(" ", "")
    now = datetime.now(ZoneInfo("Asia/Seoul"))

    def _mk(label: str, start: datetime, end: datetime) -> Dict[str, Any]:
        if start.tzinfo is None:
            start = start.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        return {"label": f"{label}({start.strftime('%Y-%m-%d')}~{end.strftime('%Y-%m-%d')})", "start": start, "end": end}

    m = re.search(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})\s*[~\-]\s*(\d{4})[-./](\d{1,2})[-./](\d{1,2})", q_raw)
    if m:
        y1, mo1, d1, y2, mo2, d2 = map(int, m.groups())
        start = datetime(y1, mo1, d1, 0, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        end = datetime(y2, mo2, d2, 23, 59, 59, tzinfo=ZoneInfo("Asia/Seoul"))
        if start <= end:
            return _mk("지정기간", start, end)

    m = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월", q_raw)
    if m:
        month_range = _get_month_range(int(m.group(1)), int(m.group(2)))
        if month_range:
            return _mk(f"{int(m.group(1))}년 {int(m.group(2))}월", month_range[0], month_range[1])

    m = re.search(r"작년\s*(\d{1,2})\s*월", q_raw)
    if m:
        month_range = _get_month_range(now.year - 1, int(m.group(1)))
        if month_range:
            return _mk(f"작년 {int(m.group(1))}월", month_range[0], month_range[1])

    m = re.search(r"(올해|금년|당해)\s*(\d{1,2})\s*월", q_raw)
    if m:
        month_range = _get_month_range(now.year, int(m.group(2)))
        if month_range:
            return _mk(f"올해 {int(m.group(2))}월", month_range[0], month_range[1])

    if any(token in q_compact for token in ("이번주", "금주", "이번주간")):
        start, end = _get_week_range(now, week_offset=0)
        return _mk("이번주", start, end)
    if any(token in q_compact for token in ("저번주", "지난주", "전주", "지난주간")):
        start, end = _get_week_range(now, week_offset=-1)
        return _mk("저번주", start, end)

    if any(token in q_compact for token in ("이번달", "금월")):
        month_range = _get_month_range(now.year, now.month)
        if month_range:
            return _mk("이번달", month_range[0], month_range[1])
    if any(token in q_compact for token in ("저번달", "지난달", "전월")):
        year = now.year
        month = now.month - 1
        if month == 0:
            year -= 1
            month = 12
        month_range = _get_month_range(year, month)
        if month_range:
            return _mk("저번달", month_range[0], month_range[1])

    recent_tokens = ("최근", "요즘", "근래", "최근에", "최신", "최신순", "최신이슈", "최근이슈")
    if any(tok in q_compact for tok in recent_tokens):
        m = re.search(r"(최근|요즘|근래|최근에)\s*(\d{1,3})?\s*(일|주|주일|개월|달)?", q_raw)
        n = None
        unit = None
        if m:
            if m.group(2):
                try:
                    n = int(m.group(2))
                except Exception:
                    n = None
            unit = (m.group(3) or "").strip()
        if n is None:
            n = 7
        if not unit:
            unit = "일"
        unit = unit.replace("주일", "주").replace("달", "개월")

        if unit == "일":
            delta = timedelta(days=n)
            label = f"최근 {n}일"
        elif unit == "주":
            delta = timedelta(days=7 * n)
            label = f"최근 {n}주"
        else:
            delta = timedelta(days=30 * n)
            label = f"최근 {n}개월"

        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
        start = (end - delta).replace(hour=0, minute=0, second=0, microsecond=0)
        return _mk(label, start, end)

    return None


def _filter_docs_by_datetime_range(documents: List[Dict[str, Any]], start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for doc in documents:
        dt = _extract_doc_datetime(doc)
        if not dt:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        dt = dt.astimezone(ZoneInfo("Asia/Seoul"))
        if start_dt <= dt < end_dt:
            filtered.append(doc)
    return filtered


def rerank_rag_documents(documents: List[Dict[str, Any]], prefer_recent: bool = False) -> List[Dict[str, Any]]:
    if not documents:
        return []
    merged: Dict[str, Dict[str, Any]] = {}
    for doc in documents:
        key = str(doc.get("doc_id") or doc.get("id") or doc.get("confluence_mail_page_url") or doc.get("url") or f"{doc.get('title','')}|{doc.get('_index','')}")
        raw_score = float(doc.get("_score") or 0.0)
        if key not in merged:
            item = dict(doc)
            item["_query_hits"] = 1
            item["_vector_score"] = raw_score
            merged[key] = item
        else:
            merged[key]["_query_hits"] += 1
            if raw_score > float(merged[key].get("_vector_score") or 0.0):
                keep_hits = merged[key]["_query_hits"]
                item = dict(doc)
                item["_query_hits"] = keep_hits
                item["_vector_score"] = raw_score
                merged[key] = item

    docs = list(merged.values())
    max_vec = max([float(d.get("_vector_score") or 0.0) for d in docs] or [1.0])
    now = datetime.now(ZoneInfo("Asia/Seoul"))

    for d in docs:
        vec = float(d.get("_vector_score") or 0.0)
        vec_norm = vec / max_vec if max_vec > 0 else 0.0
        dt = _extract_doc_datetime(d)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("Asia/Seoul"))
            dt_local = dt.astimezone(ZoneInfo("Asia/Seoul"))
            age_days = max((now - dt_local).total_seconds() / 86400.0, 0.0)
            recency_score = max(RAG_MIN_RECENCY_SCORE, math.exp(-math.log(2) * age_days / max(RAG_RECENCY_HALF_LIFE_DAYS, 1.0)))
            d["_doc_date"] = dt_local.strftime("%Y-%m-%d %H:%M")
            d["_doc_ts"] = dt_local.timestamp()
        else:
            recency_score = RAG_MIN_RECENCY_SCORE
            d["_doc_date"] = "날짜 정보 없음"
            d["_doc_ts"] = 0.0

        query_hit_bonus = min(max(int(d.get("_query_hits") or 1) - 1, 0), 3) * 0.03
        combined_score = ((1 - RAG_RECENCY_WEIGHT) * vec_norm) + (RAG_RECENCY_WEIGHT * recency_score) + query_hit_bonus
        d["_vector_norm"] = round(vec_norm, 4)
        d["_recency_score"] = round(recency_score, 4)
        d["_combined_score"] = round(combined_score, 4)

    if prefer_recent:
        docs.sort(key=lambda x: (float(x.get("_doc_ts", 0.0)), float(x.get("_combined_score", 0.0)), float(x.get("_vector_score", 0.0))), reverse=True)
    else:
        docs.sort(key=lambda x: (float(x.get("_combined_score", 0.0)), float(x.get("_vector_score", 0.0))), reverse=True)
    return docs


def _pick_best_link(doc: Dict[str, Any]) -> str:
    for key in ("confluence_mail_page_url", "url", "source_url", "doc_url", "link"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _pick_best_snippet(doc: Dict[str, Any]) -> str:
    for key in (
        "content",
        "merge_title_content",
        "summary",
        "snippet",
        "text",
        "body",
        "description",
        "chunk_text",
        "page_content",
        "mail_body",
        "body_text",
        "document_text",
    ):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    source = doc.get("_source")
    if isinstance(source, dict):
        for key in (
            "content",
            "merge_title_content",
            "summary",
            "snippet",
            "text",
            "body",
            "description",
            "chunk_text",
            "page_content",
            "mail_body",
            "body_text",
            "document_text",
        ):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return _pick_fallback_snippet(doc)


def _collect_text_fragments(obj: Any, out: List[str], *, depth: int = 0) -> None:
    if depth > 3 or len(out) >= 12:
        return
    if isinstance(obj, str):
        s = re.sub(r"\s+", " ", obj).strip()
        if len(s) >= 20 and not s.startswith(("http://", "https://")):
            out.append(s)
        return
    if isinstance(obj, dict):
        for _, v in obj.items():
            _collect_text_fragments(v, out, depth=depth + 1)
        return
    if isinstance(obj, list):
        for item in obj[:20]:
            _collect_text_fragments(item, out, depth=depth + 1)


def _pick_fallback_snippet(doc: Dict[str, Any]) -> str:
    frags: List[str] = []
    _collect_text_fragments(doc, frags)
    dedup: List[str] = []
    seen = set()
    for f in frags:
        key = f[:120]
        if key in seen:
            continue
        seen.add(key)
        dedup.append(f)
    if not dedup:
        return ""
    return "\n".join(dedup[:3])[:3500]


def _enrich_doc_for_output(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(doc)
    if not out.get("title"):
        out["title"] = str(out.get("doc_id") or out.get("id") or "제목 없음")
    out["link"] = _pick_best_link(out)
    out["snippet"] = _pick_best_snippet(out)
    if not out.get("content") and out.get("snippet"):
        out["content"] = out["snippet"]
    out["meta"] = {
        "index": out.get("_index", ""),
        "score": out.get("_score", 0.0),
        "combined_score": out.get("_combined_score", 0.0),
        "doc_date": out.get("_doc_date", ""),
    }
    out["_source"] = {k: v for k, v in out.items() if not str(k).startswith("_")}
    return out


def generate_deterministic_query_variants(question: str) -> List[str]:
    base = normalize_query_for_search(question)
    if not base:
        return []
    variants: List[str] = []
    q = re.sub(r"\s+", " ", base).strip()
    if "주요" in q and "이슈" in q and "정리" in q and "파트" not in q:
        parts = q.split()
        if parts:
            lead = parts[0]
            if re.fullmatch(r"[A-Za-z0-9]{2,10}", lead):
                variants.append(f"{lead} 파트 " + " ".join(parts[1:]))
    return [v for v in variants if v and v != base]


def build_search_queries(question: str) -> List[str]:
    normalized = normalize_query_for_search(question)
    sanitized_original = _sanitize_query(normalized)
    if not sanitized_original:
        return []

    queries: List[str] = []
    if RAG_INCLUDE_ORIGINAL_QUERY:
        queries.append(sanitized_original)

    deterministic = generate_deterministic_query_variants(question)
    for item in deterministic:
        sq = _sanitize_query(item)
        if sq and sq not in queries:
            queries.append(sq)

    if not queries:
        queries = [sanitized_original]
    return queries[:MAX_RAG_QUERIES]


def _search_single_query(query: str, *, indexes: Optional[List[str]], top_k: int, mode: Optional[str], filter: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    target_indexes = indexes or [x.strip() for x in RAG_INDEXES.split(",") if x.strip()]
    sanitized_query = _sanitize_query(query)
    if not sanitized_query:
        return []

    num_result_doc = min(max(1, int(top_k)), RAG_API_MAX_NUM_RESULT_DOC)
    rag_client = RagClient(api_key=RAG_API_KEY, dep_ticket=RAG_DEP_TICKET, base_url=RAG_BASE_URL)
    all_results: List[Dict[str, Any]] = []

    for index in target_indexes:
        try:
            result = rag_client.retrieve(
                index_name=index,
                query_text=sanitized_query,
                mode=mode or RAG_RETRIEVE_MODE,
                num_result_doc=num_result_doc,
                permission_groups=_parse_permission_groups(RAG_PERMISSION_GROUPS),
                filter=filter,
                bm25_boost=RAG_BM25_BOOST,
                knn_boost=RAG_KNN_BOOST,
            )
            hits = (result.get("hits") or {}).get("hits", []) if isinstance(result, dict) else []
            for hit in hits:
                source = hit.get("_source") if isinstance(hit, dict) else None
                if not isinstance(source, dict):
                    continue
                doc = dict(source)
                doc["_index"] = index
                doc["_score"] = float(hit.get("_score", 0.0))
                all_results.append(doc)
        except Exception as e:
            logger.warning("RAG retrieve failed index=%s err=%s", index, e)
            continue

    return all_results


def retrieve_rag_documents_parallel(queries: List[str], *, top_k: int, indexes: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    query_list = [q.strip() for q in queries if q and q.strip()]
    if not query_list:
        return []

    all_documents: List[Dict[str, Any]] = []
    max_workers = min(len(query_list), MAX_RAG_QUERIES, 2)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_search_single_query, query, indexes=indexes, top_k=top_k, mode=RAG_RETRIEVE_MODE, filter=None): query
            for query in query_list
        }
        for future in as_completed(future_map):
            query = future_map[future]
            try:
                docs = future.result()
                logger.info("[RAG] parallel query done query=%s docs=%s", query, len(docs))
                all_documents.extend(docs)
            except Exception as e:
                logger.warning("[RAG] parallel query failed query=%s err=%s", query, e)
    return all_documents


class RagTool:
    """RAG wrapper used by executor."""

    def search(self, query: str, top_k: int = 5, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        _ = filters
        effective_question = (query or "").strip()
        if not effective_question:
            return []

        normalized_query = normalize_query_for_search(effective_question)
        glossary_intent = is_glossary_intent(effective_question)
        force_glossary = is_force_glossary_query(effective_question)

        search_queries = build_search_queries(effective_question)
        if not search_queries:
            return []

        time_range = _extract_time_range_from_question(effective_question)
        issue_summary_intent = is_issue_summary_intent(effective_question)
        strong_mail_intent = has_strong_mail_intent(effective_question)
        prefer_recent_docs = bool(time_range) or should_prioritize_recent_docs(effective_question) or issue_summary_intent

        retrieve_top_k = max(int(top_k or RAG_NUM_RESULT_DOC), RAG_NUM_RESULT_DOC)
        if time_range:
            retrieve_top_k = max(retrieve_top_k, RAG_TEMPORAL_NUM_RESULT_DOC)
        elif issue_summary_intent:
            retrieve_top_k = max(retrieve_top_k, RAG_API_MAX_NUM_RESULT_DOC)

        target_indexes = None
        if strong_mail_intent or issue_summary_intent:
            target_indexes = [MAIL_INDEX_NAME]

        all_rag_documents = retrieve_rag_documents_parallel(search_queries, top_k=retrieve_top_k, indexes=target_indexes)
        all_mail_docs = [d for d in all_rag_documents if d.get("_index") == MAIL_INDEX_NAME]
        all_glossary_docs = [d for d in all_rag_documents if d.get("_index") == GLOSSARY_INDEX_NAME]

        if time_range and all_mail_docs:
            ranged_mail_docs = _filter_docs_by_datetime_range(all_mail_docs, time_range["start"], time_range["end"])
            if ranged_mail_docs:
                all_mail_docs = ranged_mail_docs
            else:
                expanded_start = time_range["start"] - timedelta(days=14)
                expanded_mail_docs = _filter_docs_by_datetime_range(all_mail_docs, expanded_start, time_range["end"])
                all_mail_docs = expanded_mail_docs if expanded_mail_docs else []

        reranked_mail_docs = rerank_rag_documents(all_mail_docs, prefer_recent=prefer_recent_docs)[:RAG_NUM_RESULT_DOC]
        reranked_glossary_docs = rerank_rag_documents(all_glossary_docs, prefer_recent=prefer_recent_docs)[:RAG_NUM_RESULT_DOC]
        mail_docs = reranked_mail_docs[:RAG_CONTEXT_DOCS]
        glossary_docs = reranked_glossary_docs[: max(RAG_CONTEXT_DOCS, GLOSSARY_TOPK_MATCH)]

        selected_docs: List[Dict[str, Any]] = []

        if GLOSSARY_RAG_ENABLE and force_glossary and glossary_docs:
            glossary_match = is_glossary_result_relevant(effective_question, glossary_docs, topk=GLOSSARY_TOPK_MATCH, min_score=GLOSSARY_THRESHOLD)
            if glossary_match:
                selected_docs = glossary_docs[:RAG_CONTEXT_DOCS]
            elif mail_docs and is_rag_result_relevant(effective_question, mail_docs):
                selected_docs = mail_docs
        elif mail_docs and is_rag_result_relevant(effective_question, mail_docs):
            selected_docs = mail_docs
        elif GLOSSARY_RAG_ENABLE and glossary_intent and glossary_docs:
            glossary_match = is_glossary_result_relevant(effective_question, glossary_docs, topk=GLOSSARY_TOPK_MATCH, min_score=GLOSSARY_THRESHOLD)
            if glossary_match:
                selected_docs = glossary_docs[:RAG_CONTEXT_DOCS]
        else:
            combined_docs = rerank_rag_documents(all_rag_documents, prefer_recent=prefer_recent_docs)[:RAG_NUM_RESULT_DOC]
            top_docs = combined_docs[:RAG_CONTEXT_DOCS]
            top_score = float(top_docs[0].get("_combined_score") or 0.0) if top_docs else 0.0
            skip_rag = top_score < RAG_SIMILARITY_THRESHOLD
            rag_relevant = (not skip_rag) and is_rag_result_relevant(effective_question, top_docs)
            if rag_relevant:
                selected_docs = top_docs

        out = [_enrich_doc_for_output(d) for d in selected_docs]
        if out:
            debug_docs = []
            for d in out[:3]:
                snippet_len = len(str(d.get("snippet") or ""))
                debug_docs.append(
                    {
                        "title": str(d.get("title") or "")[:80],
                        "doc_date": str(d.get("_doc_date") or d.get("meta", {}).get("doc_date") or ""),
                        "score": d.get("_combined_score", d.get("meta", {}).get("combined_score")),
                        "snippet_len": snippet_len,
                    }
                )
            logger.info("RAG selected docs preview=%s", debug_docs)
        logger.info(
            "RAG search done query=%s normalized=%s indexes=%s candidates=%s results=%s",
            effective_question,
            normalized_query,
            target_indexes or [x.strip() for x in RAG_INDEXES.split(",") if x.strip()],
            len(all_rag_documents),
            len(out),
        )
        return out

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
