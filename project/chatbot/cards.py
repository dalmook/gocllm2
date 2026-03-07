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


def build_issue_form_card(*, room_id: str, sender_hint: str = "") -> Dict:
    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "weight": "Bolder", "size": "Medium", "text": "Issue 등록"},
            {"type": "Input.Text", "id": "title", "placeholder": "제목", "isRequired": True, "errorMessage": "제목 필수"},
            {"type": "Input.Text", "id": "content", "placeholder": "내용", "isMultiline": True},
            {"type": "Input.Text", "id": "owner", "placeholder": f"담당자 (예: {sender_hint})"},
            {"type": "Input.Text", "id": "target_date", "placeholder": "목표일 (YYYY-MM-DD)"},
            {"type": "Input.Text", "id": "url", "placeholder": "참고 URL"},
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "등록",
                "data": {"action": "ISSUE_CREATE", "room_id": str(room_id)},
            }
        ],
    }


def build_issue_list_card(issues: List[Dict], *, room_id: str) -> Dict:
    body: List[Dict] = [
        {"type": "TextBlock", "weight": "Bolder", "size": "Medium", "text": "Issue 목록(OPEN)"},
    ]
    if not issues:
        body.append({"type": "TextBlock", "text": "현재 OPEN 이슈가 없습니다.", "wrap": True})
    else:
        for it in issues[:12]:
            iid = int(it.get("issue_id", 0))
            title = str(it.get("title", ""))
            owner = str(it.get("owner", ""))
            body.append({"type": "TextBlock", "wrap": True, "text": f"#{iid} {title} (담당:{owner or '-'})"})
    actions: List[Dict] = [
        {"type": "Action.Submit", "title": "새 이슈", "data": {"action": "ISSUE_FORM", "room_id": str(room_id)}},
        {"type": "Action.Submit", "title": "새로고침", "data": {"action": "ISSUE_LIST", "room_id": str(room_id)}},
    ]
    if issues:
        for it in issues[:5]:
            iid = int(it.get("issue_id", 0))
            actions.append({"type": "Action.Submit", "title": f"Clear #{iid}", "data": {"action": "ISSUE_CLEAR", "issue_id": iid, "room_id": str(room_id)}})
    return {"type": "AdaptiveCard", "version": "1.4", "body": body, "actions": actions[:10]}


def build_issue_edit_form_card(issue: Dict, *, room_id: str) -> Dict:
    iid = int(issue.get("issue_id", 0))
    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "weight": "Bolder", "size": "Medium", "text": f"Issue 수정 #{iid}"},
            {"type": "Input.Text", "id": "title", "value": str(issue.get("title", "")), "isRequired": True, "errorMessage": "제목 필수"},
            {"type": "Input.Text", "id": "content", "value": str(issue.get("content", "")), "isMultiline": True},
            {"type": "Input.Text", "id": "owner", "value": str(issue.get("owner", ""))},
            {"type": "Input.Text", "id": "target_date", "value": str(issue.get("target_date", ""))},
            {"type": "Input.Text", "id": "url", "value": str(issue.get("url", ""))},
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "저장",
                "data": {"action": "ISSUE_EDIT_SAVE", "issue_id": iid, "room_id": str(room_id)},
            },
            {
                "type": "Action.Submit",
                "title": "이력",
                "data": {"action": "ISSUE_HISTORY", "issue_id": iid, "room_id": str(room_id)},
            },
        ],
    }


def build_issue_history_card(events: List[Dict], *, issue_id: int, room_id: str) -> Dict:
    body: List[Dict] = [
        {"type": "TextBlock", "weight": "Bolder", "size": "Medium", "text": f"Issue 이력 #{int(issue_id)}"},
    ]
    if not events:
        body.append({"type": "TextBlock", "text": "이력이 없습니다.", "wrap": True})
    else:
        for e in events[:15]:
            body.append(
                {
                    "type": "TextBlock",
                    "wrap": True,
                    "text": f"[{e.get('created_at','')}] {e.get('action','')} / {e.get('actor','')} / {e.get('memo','')}",
                }
            )
    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
        "actions": [
            {"type": "Action.Submit", "title": "목록", "data": {"action": "ISSUE_LIST", "room_id": str(room_id)}},
            {"type": "Action.Submit", "title": "수정", "data": {"action": "ISSUE_EDIT_FORM", "issue_id": int(issue_id), "room_id": str(room_id)}},
        ],
    }


def build_watchroom_form_card() -> Dict:
    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "weight": "Bolder", "size": "Medium", "text": "공지방 생성"},
            {"type": "Input.Text", "id": "room_title", "placeholder": "방 제목"},
            {"type": "Input.Text", "id": "members", "placeholder": "참여자 SSO (콤마 구분)", "isRequired": True, "errorMessage": "참여자 필수"},
            {"type": "Input.Text", "id": "note", "placeholder": "메모"},
        ],
        "actions": [
            {"type": "Action.Submit", "title": "생성", "data": {"action": "WATCHROOM_CREATE"}}
        ],
    }
