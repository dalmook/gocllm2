from __future__ import annotations

from typing import Dict, List, Tuple


def build_home_card() -> Dict:
    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "size": "Large", "weight": "Bolder", "text": "Hybrid Assistant"},
            {"type": "TextBlock", "wrap": True, "text": "질문을 바로 입력하거나 /ask 질문 형태로 입력하세요."},
            {"type": "TextBlock", "wrap": True, "text": "그룹방은 멘션/접두어 기반 호출을 지원합니다."},
        ],
    }


def build_quick_links_card(links: List[Tuple[List[str], str, str]]) -> Dict:
    facts = []
    for aliases, title, _url in links:
        facts.append({"title": "/" + aliases[0], "value": title})

    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "size": "Medium", "weight": "Bolder", "text": "Quick Links"},
            {"type": "FactSet", "facts": facts[:15]},
        ],
    }


def build_quicklink_card(title: str, url: str) -> Dict:
    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "size": "Medium", "weight": "Bolder", "text": title},
            {"type": "TextBlock", "wrap": True, "text": url},
        ],
        "actions": [
            {"type": "Action.OpenUrl", "title": "열기", "url": url},
        ],
    }
