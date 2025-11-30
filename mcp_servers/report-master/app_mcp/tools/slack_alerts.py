# app_mcp/tools/slack_alerts.py
from __future__ import annotations

import os
import logging
from typing import Dict, Any

import requests

from app_mcp.core.risk_rules import RiskLevel
from app_mcp.core.config import get_settings

logger = logging.getLogger(__name__)

# Settings 로딩 (.env 기반)
_settings = get_settings()

# ✅ Webhook URL 결정 로직
# 1순위: 환경변수 (컨테이너/배포 환경에서 override 용)
# 2순위: .env → Settings.slack_webhook_url
SLACK_WEBHOOK_URL_ALERT = (
    os.getenv("SLACK_WEBHOOK_URL_ALERT")
    or os.getenv("SLACK_WEBHOOK_URL_MCP")
    or os.getenv("SLACK_WEBHOOK_URL")
    or _settings.slack_webhook_url
)


def _level_emoji(level: str) -> str:
    if level == "CRIT":
        return "🔴"
    if level == "WARN":
        return "🟡"
    return "🟢"


def _level_title(level: str) -> str:
    if level == "CRIT":
        return "중대 리스크 (즉시 조치 필요)"
    if level == "WARN":
        return "경고 (주의 깊은 모니터링 필요)"
    return "정상 범위"


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
            "[Slack-ALERT] SLACK_WEBHOOK_URL_ALERT / SLACK_WEBHOOK_URL_MCP / SLACK_WEBHOOK_URL / Settings.slack_webhook_url not set"
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
