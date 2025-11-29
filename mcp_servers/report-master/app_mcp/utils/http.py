import httpx
from typing import Any, Dict, Optional
from app_mcp.core.config import get_settings

async def get_json(url: str, headers: Optional[Dict[str, str]]=None, timeout: int=15) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, headers=headers or {})
        r.raise_for_status()
        return r.json()

async def post_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]]=None, timeout: int=15) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload, headers=headers or {})
        r.raise_for_status()
        return r.json()

async def slack_notify(text: str):
    settings = get_settings()
    if not settings.slack_webhook_url:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(settings.slack_webhook_url, json={"text": text})


# slack 알림 내용

from app_mcp.core.config import get_settings

async def slack_notify(text: str):
    s = get_settings()
    if not s.slack_webhook_url:
        return
    async with httpx.AsyncClient() as client:
        await client.post(s.slack_webhook_url, json={"text": text})

async def slack_notify_report(conclusion: str, rid: str, period: str, html_url: str, json_url: str):
    """
    상태별 이모지/색상 + 링크 포함 블록 메시지
    """
    s = get_settings()
    if not s.slack_webhook_url:
        return

    emoji = {"compliant":"✅", "conditional":"⚠️", "non-compliant":"🚨"}.get(conclusion, "ℹ️")
    color = {"compliant":"#2EB67D", "conditional":"#E3B23C", "non-compliant":"#E01E5A"}.get(conclusion, "#439FE0")

    payload = {
        "attachments": [{
            "color": color,
            "blocks": [
                {"type":"section","text":{"type":"mrkdwn","text":f"*{emoji} MCP 준수 보고서 생성 완료*"}},
                {"type":"context","elements":[{"type":"mrkdwn","text":f"*Report*: `{rid}`  |  *Period*: `{period}`  |  *결론*: *{conclusion}*"}]},
                {"type":"actions","elements":[
                    {"type":"button","text":{"type":"plain_text","text":"열기 (HTML)"},"url": html_url},
                    {"type":"button","text":{"type":"plain_text","text":"원본 (JSON)"},"url": json_url}
                ]}
            ]
        }]}
    

    async with httpx.AsyncClient() as client:
        await client.post(s.slack_webhook_url, json=payload)
