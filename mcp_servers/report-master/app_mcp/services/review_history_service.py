# app_mcp/services/review_history_service.py

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional, TypedDict, List

from app_mcp.core.config import ensure_artifacts_dir


# ─────────────────────────────────────────────
# 타입 정의
# ─────────────────────────────────────────────

ActionType = Literal["approve", "revise", "reject"]
SourceType = Literal["slack", "web", "api", "system"]


class ReviewHistoryEntry(TypedDict, total=False):
    period: str              # "2025-10" 같은 형식
    action: ActionType       # "approve" | "revise" | "reject"
    comment: Optional[str]
    revision_no: int
    source: SourceType
    actor: Optional[str]     # 나중에 Slack user id / 이름
    created_at: str          # ISO8601 문자열 (UTC)


# ─────────────────────────────────────────────
# 파일 경로 설정
# ─────────────────────────────────────────────

def _get_history_file() -> Path:
    artifacts_dir = ensure_artifacts_dir()
    return artifacts_dir / "review_history.json"


# ─────────────────────────────────────────────
# 내부 유틸
# ─────────────────────────────────────────────

def _load_all() -> List[ReviewHistoryEntry]:
    """JSON 파일에서 전체 이력을 읽어온다. 없으면 빈 리스트."""
    history_file = _get_history_file()
    if not history_file.exists():
        return []

    try:
        with history_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # 형식이 잘못되어 있어도 최소한 리스트만 보장
        if isinstance(data, list):
            return data  # type: ignore[return-value]
        return []
    except Exception:
        # 파싱 에러 등 발생 시 안전하게 빈 리스트 반환
        return []


def _save_all(entries: List[ReviewHistoryEntry]) -> None:
    """전체 이력을 JSON 파일에 저장."""
    history_file = _get_history_file()
    history_file.parent.mkdir(parents=True, exist_ok=True)
    with history_file.open("w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# 외부에서 쓸 함수들
# ─────────────────────────────────────────────

def log_decision(
    *,
    period: str,
    action: ActionType,
    comment: Optional[str] = None,
    revision_no: int = 0,
    source: SourceType = "api",
    actor: Optional[str] = None,
) -> ReviewHistoryEntry:
    """
    승인/재생성/반려 한 건을 이력에 추가한다.
    """
    entries = _load_all()

    entry: ReviewHistoryEntry = {
        "period": period,
        "action": action,
        "comment": comment,
        "revision_no": int(revision_no),
        "source": source,
        "actor": actor,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    entries.append(entry)
    _save_all(entries)
    return entry


def get_all_history() -> List[ReviewHistoryEntry]:
    """
    전체 리뷰 이력을 반환한다.
    """
    return _load_all()


def get_history_by_period(period: str) -> List[ReviewHistoryEntry]:
    """
    특정 period(예: '2025-10')에 대한 이력만 필터링해서 반환한다.
    """
    entries = _load_all()
    return [e for e in entries if e.get("period") == period]


def get_latest_decision(period: str) -> Optional[ReviewHistoryEntry]:
    """
    특정 period에 대한 마지막 결정 1건을 반환한다.
    없으면 None.
    """
    history = get_history_by_period(period)
    if not history:
        return None
    return history[-1]
