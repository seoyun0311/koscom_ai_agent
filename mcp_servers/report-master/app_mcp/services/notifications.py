# app_mcp/services/notifications.py

import os
import uuid
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# -------------------------------------------------
# 유틸리티 함수
# -------------------------------------------------
def mask_email(email: str) -> str:
    """이메일 마스킹 (예: c**@example.com)"""
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    masked = local[0] + "**" if len(local) > 1 else local
    return f"{masked}@{domain}"


def grade_emoji(grade: str) -> str:
    """등급별 이모지 반환"""
    return {
        "A": "🟢",
        "B": "🟡",
        "C": "🟠",
        "D": "🔴",
    }.get(grade, "⚪")


# -------------------------------------------------
# 1) 월간 요약 Slack 전송 (링크 포함 버전)
# -------------------------------------------------
def send_slack_monthly_summary(
    *,
    period: str,
    summary: dict,
    report_path: str | None = None,
    webhook_url: str | None = None,
) -> dict:
    """
    월간 컴플라이언스 요약을 Slack으로 전송하는 함수

    반환 형식 예:
    {"success": True, "error": None}
    """
    url = (
        webhook_url
        or os.getenv("SLACK_WEBHOOK_URL_MCP")
        or os.getenv("SLACK_WEBHOOK_URL")
    )

    if not url:
        msg = "Slack webhook URL missing"
        logger.warning(f"[Slack-SUMMARY] {msg}")
        return {"success": False, "error": msg}

    # summary에서 필요한 정보 뽑기
    final_grade = summary.get("final_grade", "N/A")
    key_points = summary.get("key_points", [])

    # 세부 등급 (있으면 표시, 없어도 동작하게)
    collateral = summary.get("collateral_grade")
    peg = summary.get("peg_grade")
    liquidity = summary.get("liquidity_grade")
    por = summary.get("por_grade")

    detail_lines = []
    if collateral:
        detail_lines.append(f"{grade_emoji(collateral)} 담보율: {collateral}")
    if peg:
        detail_lines.append(f"{grade_emoji(peg)} 페그 안정성: {peg}")
    if liquidity:
        detail_lines.append(f"{grade_emoji(liquidity)} 유동성: {liquidity}")
    if por:
        detail_lines.append(f"{grade_emoji(por)} PoR 검증: {por}")

    detail_text = "\n".join(detail_lines) if detail_lines else "세부 등급 정보 없음"

    # key_points를 bullet로 표시
    key_points_text = ""
    if key_points:
        key_points_text = "\n\n*주요 포인트*\n" + "\n".join(
            f"• {kp}" for kp in key_points
        )

    summary_text = (
        f"*{period} 월간 K-WON 컴플라이언스 요약*\n\n"
        f"*최종 등급*: {grade_emoji(final_grade)} *{final_grade}*\n\n"
        f"*세부 평가*\n{detail_text}"
        f"{key_points_text}"
    )

    # 기본 블록 (헤더 + 요약)
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📊 {period} 월간 K-WON 컴플라이언스 요약",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": summary_text,
            },
        },
    ]

    # 🔗 report_path가 있으면 다운로드 링크 블록 추가
    if report_path and os.path.exists(report_path):
        report_filename = os.path.basename(report_path)
        BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
        download_url = f"{BASE_URL}/artifacts/{report_filename}"

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📄 *상세 보고서*\n<{download_url}|{report_filename} 다운로드>",
                },
            }
        )

    payload = {
        "text": f"{period} 월간 보고서 요약",
        "blocks": blocks,
    }

    try:
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code // 100 == 2:
            logger.info("[Slack-SUMMARY] ✓ Sent monthly summary for %s", period)
            return {"success": True, "error": None}
        err = f"Slack returned {resp.status_code}: {resp.text}"
        logger.error("[Slack-SUMMARY] ✗ %s", err)
        return {"success": False, "error": err}
    except Exception as e:
        logger.error("[Slack-SUMMARY] ✗ Exception: %s", e)
        return {"success": False, "error": str(e)}


# -------------------------------------------------
# 2) Human Review Slack Block Kit
# -------------------------------------------------
def send_slack_human_review_request(
    *,
    period: str,
    task_id: int,
    summary: dict,
    report_path: str,
    revision_count: int | None = None,
    webhook_url: str | None = None,
) -> dict:
    """Human Review용 Slack Block Kit 메시지 전송"""
    
    url = (
        webhook_url
        or os.getenv("SLACK_WEBHOOK_URL_MCP")
        or os.getenv("SLACK_WEBHOOK_URL")
    )

    if not url:
        msg = "Slack webhook URL missing"
        logger.warning(f"[Slack-HR] {msg}")
        return {"success": False, "error": msg}

    # 파일 존재 확인
    if report_path and os.path.exists(report_path):
        report_filename = os.path.basename(report_path)
        BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
        download_url = f"{BASE_URL}/artifacts/{report_filename}"
        report_section_text = (
            f"📄 *상세 보고서*\n<{download_url}|{report_filename} 다운로드>"
        )
    else:
        logger.warning(f"[Slack-HR] Report file not ready: {report_path}")
        report_section_text = "📄 *상세 보고서*\n보고서 생성 중..."

    # 요약 구조화
    final_grade = summary.get("final_grade", "N/A")
    
    # key_points에서 등급 추출
    key_points = summary.get("key_points", [])
    collateral = peg = liquidity = por = "N/A"
    
    for point in key_points:
        if "Collateral grade:" in point:
            collateral = point.split(":")[-1].strip()
        elif "Peg grade:" in point:
            peg = point.split(":")[-1].strip()
        elif "Liquidity grade:" in point:
            liquidity = point.split(":")[-1].strip()
        elif "PoR grade:" in point:
            por = point.split(":")[-1].strip()

    # 🔹 재생성 정보 텍스트
    revision_header = ""
    if revision_count and revision_count > 0:
        revision_header = f"*재생성 횟수*: {revision_count}회\n\n"

    summary_text = (
        revision_header
        + f"*최종 등급*: {grade_emoji(final_grade)} *{final_grade}*\n\n"
        + "*세부 평가*\n"
        + f"{grade_emoji(collateral)} 담보율: {collateral}\n"
        + f"{grade_emoji(peg)} 페그 안정성: {peg}\n"
        + f"{grade_emoji(liquidity)} 유동성: {liquidity}\n"
        + f"{grade_emoji(por)} PoR 검증: {por}"
    )

    # 🔹 헤더에 (재생성 n회차) 붙이기
    if revision_count and revision_count > 0:
        header_suffix = f" (재생성 {revision_count}회차)"
    else:
        header_suffix = ""

    payload = {
        "text": f"📊 {period} 보고서 Human Review 요청",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📊 {period} 월간 보고서 Human Review{header_suffix}",
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
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": report_section_text,
                },
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "👉 *승인 여부를 선택해주세요.*"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✅ 승인"
                        },
                        "style": "primary",
                        "action_id": "approve_button",
                        "value": str(task_id)
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "❌ 반려"
                        },
                        "style": "danger",
                        "action_id": "reject_button",
                        "value": str(task_id)
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🔄 보수적 재생성"
                        },
                        "action_id": "revise_button",
                        "value": str(task_id)
                    }
                ]
            }
        ],
    }

    try:
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code // 100 == 2:
            logger.info(
                "[Slack-HR] ✓ Review sent (task=%s, rev=%s)",
                task_id,
                revision_count,
            )
            return {"success": True, "error": None}
        err = f"Slack returned {resp.status_code}: {resp.text}"
        logger.error("[Slack-HR] ✗ %s", err)
        return {"success": False, "error": err}
    except Exception as e:
        logger.error("[Slack-HR] ✗ Exception: %s", e)
        return {"success": False, "error": str(e)}


# -------------------------------------------------
# 3) 이메일 보고서 전송 (파일 크기 체크 추가)
# -------------------------------------------------
def send_email_monthly_report(
    period: str,
    report_path: str,
    summary: dict | None = None,
    to_address: str | None = None,
) -> dict:
    """DOCX 보고서를 이메일로 전송 (20MB 제한)"""
    smtp_host = os.getenv("MAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("MAIL_SMTP_PORT", 587))
    smtp_user = os.getenv("MAIL_USERNAME")
    smtp_password = os.getenv("MAIL_PASSWORD")
    mail_from = os.getenv("MAIL_FROM", smtp_user)
    mail_to = to_address or os.getenv("MAIL_TO") or smtp_user

    if not smtp_user or not smtp_password:
        msg = "SMTP config missing"
        logger.warning(f"[Email] {msg}")
        return {"success": False, "error": msg}

    if not os.path.exists(report_path):
        msg = f"File not found: {report_path}"
        logger.error(f"[Email] {msg}")
        return {"success": False, "error": msg}

    # 파일 크기 확인 (20MB 제한)
    file_size_mb = os.path.getsize(report_path) / (1024 * 1024)
    MAX_SIZE_MB = 20

    if file_size_mb > MAX_SIZE_MB:
        msg = f"File too large: {file_size_mb:.1f}MB (max {MAX_SIZE_MB}MB)"
        logger.error(f"[Email] {msg}")
        return {"success": False, "error": msg}

    final_grade = (summary or {}).get("final_grade", "N/A")

    subject = f"[K-WON] {period} 월간 보고서 (등급 {final_grade})"
    body_lines = [
        f"{period} 월간 K-WON 스테이블코인 컴플라이언스 보고서를 첨부드립니다.",
        "",
        f"- 최종 등급: {final_grade}",
    ]
    body_text = "\n".join(body_lines)

    msg = MIMEMultipart()
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain"))

    # 첨부 파일
    with open(report_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f'attachment; filename="{os.path.basename(report_path)}"',
    )
    msg.attach(part)

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()

        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()

        logger.info(
            "[Email] ✓ Sent to %s (%.1fMB)",
            mask_email(mail_to),
            file_size_mb,
        )
        return {"success": True, "error": None}
    except Exception as e:
        logger.error("[Email] ✗ Failed: %s", e)
        return {"success": False, "error": str(e)}


# -------------------------------------------------
# 4) Scheduler / LangGraph용 알림 래퍼
# -------------------------------------------------
def notify_monthly_report(
    *,
    period: str,
    status: str,
    summary: dict | None = None,
    report_path: str | None = None,
    error: str | None = None,
    webhook_url: str | None = None,
) -> dict:
    """
    Scheduler / LangGraph에서 사용하는 월간 보고서 알림 래퍼.

    ❗이제는 Slack으로 요약 카드를 보내지 않고,
    단순히 로그만 남기도록 변경했다.
    (승인/반려 알림은 slack_interactions.py에서 처리)
    """
    summary = summary or {}

    # 성공이 아닌 경우: 에러 요약 메시지 구성
    if status not in ("SUCCESS", "COMPLETED"):
        error_msg = error or "월간 보고서 생성 중 오류가 발생했습니다."
        logger.error(
            "[notify_monthly_report] report failed: period=%s, status=%s, error=%s",
            period,
            status,
            error_msg,
        )
    else:
        logger.info(
            "[notify_monthly_report] report succeeded: period=%s "
            "(Slack summary disabled)",
            period,
        )

    # 호출부가 결과를 기대할 수 있으니 형식만 맞춰서 반환
    return {
        "success": True,
        "error": None,
        "status": status,
    }
