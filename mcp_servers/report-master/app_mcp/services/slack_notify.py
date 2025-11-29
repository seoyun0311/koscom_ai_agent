# app_mcp/services/slack_notify.py
import os
import httpx
from app_mcp.core.config import get_settings

settings = get_settings()

# 예: settings.slack_webhook_url 또는 환경변수에서 가져오기
SLACK_WEBHOOK_URL = settings.slack_webhook_url


async def send_slack_message(text: str):
    if not SLACK_WEBHOOK_URL:
        # 설정 안 되어 있으면 그냥 로그 느낌으로만 지나가기
        print("[Slack] SLACK_WEBHOOK_URL not set, skip:", text)
        return

    async with httpx.AsyncClient() as client:
        resp = await client.post(SLACK_WEBHOOK_URL, json={"text": text})
        resp.raise_for_status()
