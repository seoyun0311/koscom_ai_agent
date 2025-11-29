# app_mcp/tools/slack.py
import hmac, hashlib, time
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
import httpx
import os
import logging
import requests

from app_mcp.core.config import get_settings
from app_mcp.tools.server import generate_report    # 기존 생성 함수 재사용
from app_mcp.core.risk_rules import RiskLevel

router = APIRouter(prefix="/slack", tags=["slack"])

logger = logging.getLogger(__name__)

# 실시간 경보용 Webhook (없으면 MCP용 / 기본 Webhook 순서로 fallback)
SLACK_WEBHOOK_URL_ALERT = (
    os.getenv("SLACK_WEBHOOK_URL_ALERT")
    or os.getenv("SLACK_WEBHOOK_URL_MCP")
    or os.getenv("SLACK_WEBHOOK_URL")
)


def verify_slack_signature(signing_secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    # Slack: v0=<hash>
    base = f"v0:{timestamp}:{body.decode()}".encode()
    computed = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


@router.post("/command")
async def slack_command(request: Request, background_tasks: BackgroundTasks):
    """
    Slash Command 설정:
      - Command: /mcp
      - Request URL: {PUBLIC_BASE_URL}/slack/command
      - Shortcuts: 텍스트: "report 2025-11" 형태
      - 권한: commands, chat:write (앱 설정에서 추가)
    """
    s = get_settings()
    form = await request.form()
    text: str = (form.get("text") or "").strip()
    response_url: Optional[str] = form.get("response_url")

    # 서명 검증 (필수)
    sig = request.headers.get("X-Slack-Signature", "")
    ts = request.headers.get("X-Slack-Request-Timestamp", "0")
    if abs(time.time() - int(ts)) > 60 * 5:
        raise HTTPException(status_code=400, detail="timestamp too far")
    if not verify_slack_signature(s.slack_signing_secret, ts, await request.body(), sig):
        raise HTTPException(status_code=403, detail="invalid signature")

    # 파싱: "report 2025-11" 또는 "report" (이달)
    if text.startswith("report"):
        parts = text.split()
        period = parts[1] if len(parts) > 1 else time.strftime("%Y-%m")  # 기본: 이번 달

        # 3초 제한 때문에 백그라운드로 생성
        def do_generate():
            # 내부 HTTP 호출 대신, 직접 함수 재사용하려면 FastAPI DI가 필요 → 간단히 REST 호출:
            import asyncio

            async def call():
                async with httpx.AsyncClient() as client:
                    await client.post(f"{s.public_base_url}/reports/generate", params={"period": period})
                    if response_url:
                        await client.post(
                            response_url,
                            json={
                                "text": f"🛠 MCP 보고서 생성 요청을 접수했습니다. period={period}"
                            },
                        )

            asyncio.run(call())

        background_tasks.add_task(do_generate)

        # 즉시 응답(에페메럴)
        return {"response_type": "ephemeral", "text": f"🚀 보고서 생성 시작: period={period}"}

    return {"response_type": "ephemeral", "text": "사용법: `/mcp report 2025-11`"}


# ─────────────────────────────────────────────
# 실시간 리스크 알림 (OK / WARN / CRIT)
# ─────────────────────────────────────────────


def _level_emoji(level: str) -> str:
    mapping = {
        "OK": "🟢",
        "WARN": "🟡",
        "CRIT": "🔴",
    }
    return mapping.get(level, "⚪")


def _level_title(level: str) -> str:
    if level == RiskLevel.CRIT.value:
        return "심각: 즉시 조치 필요"
    if level == RiskLevel.WARN.value:
        return "경고: 모니터링 및 주의 필요"
    return "정상: 시스템 안정"


def send_risk_alert(data: Dict[str, Any]):
    """
    실시간 리스크 알림을 Slack으로 전송 (OK / WARN / CRIT 기준)

    Args:
        data: {
            "risk_level": "OK" | "WARN" | "CRIT",
            "metrics": {
                "tvl": float,
                "reserve_ratio": float,
                "peg_deviation": float,
                "liquidity_score": float
            }
        }
    """
    if not SLACK_WEBHOOK_URL_ALERT:
        logger.warning(
            "[Slack-ALERT] SLACK_WEBHOOK_URL_ALERT / SLACK_WEBHOOK_URL_MCP / SLACK_WEBHOOK_URL not set"
        )
        return

    risk_level: str = data.get("risk_level", "OK")
    metrics: Dict[str, Any] = data.get("metrics", {}) or {}

    tvl = metrics.get("tvl")
    reserve_ratio = metrics.get("reserve_ratio")
    peg_dev = metrics.get("peg_deviation")
    liq_score = metrics.get("liquidity_score")

    emoji = _level_emoji(risk_level)
    title = _level_title(risk_level)

    # 숫자 포맷은 타입 체크 후에만 적용 (에러 방지)
    tvl_line = (
        f"- TVL(유통량): {tvl:,.0f} KRW"
        if isinstance(tvl, (int, float))
        else "- TVL(유통량): (값 없음)"
    )
    cov_line = (
        f"- 담보 비율: {reserve_ratio:.4f}x"
        if isinstance(reserve_ratio, (int, float))
        else "- 담보 비율: (값 없음)"
    )
    peg_line = (
        f"- 페그 이탈: {peg_dev:+.4%}"
        if isinstance(peg_dev, (int, float))
        else "- 페그 이탈: (값 없음)"
    )
    liq_line = (
        f"- 유동성 점수: {liq_score:.3f}"
        if isinstance(liq_score, (int, float))
        else "- 유동성 점수: (값 없음)"
    )

    summary_lines = [
        f"*리스크 레벨*: {emoji} *{risk_level}*",
        f"*설명*: {title}",
        "",
        "*핵심 지표*",
        tvl_line,
        cov_line,
        peg_line,
        liq_line,
    ]
    summary_text = "\n".join(summary_lines)

    if risk_level == RiskLevel.CRIT.value:
        footer_text = "🔴 *즉시 조치 필요*: 담보/페그/유동성 지표를 우선적으로 점검하고, PoR 및 은행별 익스포저를 확인하세요."
    elif risk_level == RiskLevel.WARN.value:
        footer_text = "🟡 *경고*: 추세가 악화되는지 모니터링하고, 필요시 담보 비율/유동성 비율을 보수적으로 조정하세요."
    else:
        footer_text = "🟢 현재는 정상 범위입니다. 추세 모니터링을 지속하세요."

    payload = {
        "text": f"{emoji} K-WON 실시간 리스크 알림: {risk_level}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} K-WON 실시간 리스크 알림 ({risk_level})",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": summary_text,
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": footer_text,
                    }
                ],
            },
        ],
    }

    try:
        resp = requests.post(SLACK_WEBHOOK_URL_ALERT, json=payload, timeout=5)
        if resp.status_code // 100 == 2:
            logger.info("[Slack-ALERT] ✅ Alert sent to Slack (%s)", risk_level)
        else:
            logger.error(
                "[Slack-ALERT] ❌ Failed: %s %s", resp.status_code, resp.text
            )
    except Exception as e:
        logger.error(f"[Slack-ALERT] ❌ Exception: {e}")
