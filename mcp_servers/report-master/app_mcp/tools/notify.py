#tools/notify.py
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from app_mcp.utils.http import slack_notify, slack_notify_report
from app_mcp.core.config import get_settings

router = APIRouter(prefix="/notify", tags=["notify"])

class NotifyItem(BaseModel):
    title: str = Field(..., description="메시지 제목")
    text: str = Field(..., description="본문 (마크다운 OK)")
    conclusion: Optional[str] = Field(default=None, description="상태 표시: compliant|conditional|non-compliant")
    links: Optional[Dict[str, str]] = Field(default=None, description="버튼 링크들 {라벨: URL}")

@router.post("/")
async def post_to_slack(item: NotifyItem):
    s = get_settings()
    # 결론이 있으면 예쁜 카드, 없으면 단순 텍스트
    if item.conclusion and item.links:
        # 카드 스타일 (버튼 2개까지 권장)
        labels = list(item.links.keys())
        urls   = list(item.links.values())
        html_url = urls[0] if urls else s.public_base_url
        json_url = urls[1] if len(urls) > 1 else s.public_base_url

        await slack_notify_report(
            conclusion=item.conclusion,
            rid=item.title,
            period="ad-hoc",
            html_url=html_url,
            json_url=json_url
        )
        # 본문도 한번 더 내려주고 싶으면:
        await slack_notify(f"{item.title}\n{item.text}")
    else:
        await slack_notify(f"*{item.title}*\n{item.text}")

    return {"ok": True}
