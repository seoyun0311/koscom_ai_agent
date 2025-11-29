# app_mcp/services/mail_service.py

import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, Tuple
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# .env 로딩
load_dotenv()

MAIL_SMTP_HOST = os.getenv("MAIL_SMTP_HOST", "smtp.gmail.com")
MAIL_SMTP_PORT = int(os.getenv("MAIL_SMTP_PORT", "465"))
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM", MAIL_USERNAME)
MAIL_TO = os.getenv("MAIL_TO", MAIL_USERNAME)


def _log_mail_config():
    logger.info(
        "[mail_service] host=%s, port=%s, from=%s, to=%s, user=%s",
        MAIL_SMTP_HOST,
        MAIL_SMTP_PORT,
        MAIL_FROM,
        MAIL_TO,
        MAIL_USERNAME,
    )


def _decision_label(decision: str) -> Tuple[str, str]:
    mapping = {
        "approved": ("✅ [승인 완료]", "승인"),
        "rejected": ("❌ [반려]", "반려"),
        "revised": ("🔄 [재생성 요청]", "보수적 재생성 요청"),
    }
    return mapping.get(decision, ("📄 [알림]", decision))


async def send_approval_email(
    task_id: int,
    period: str,
    decision: str,
    comment: str = "",
    report_path: Optional[str] = None,
):
    """Slack Human Review 결과를 이메일로 발송 (+ 보고서 첨부)"""

    _log_mail_config()

    if not MAIL_USERNAME or not MAIL_PASSWORD:
        logger.error("[mail_service] MAIL_USERNAME or MAIL_PASSWORD missing")
        return

    # 결정 라벨
    prefix, decision_kr = _decision_label(decision)
    subject = f"{prefix} K-WON {period} 월간 보고서"

    clean_comment = (comment or "").strip() or "없음"

    body = f"""K-WON 스테이블코인 컴플라이언스 시스템입니다.

========================================
Task ID : {task_id}
기간    : {period}
결정    : {decision_kr} ({decision})
========================================

코멘트:
{clean_comment}

---
본 메일은 자동 발송되었습니다.
"""

    try:
        msg = MIMEMultipart()
        msg["From"] = MAIL_FROM
        msg["To"] = MAIL_TO
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # 📎 파일 첨부
        if report_path and os.path.exists(report_path):
            try:
                filename = os.path.basename(report_path)

                with open(report_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())

                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{filename}"',
                )

                msg.attach(part)
                logger.info(f"[mail_service] Attached report: {filename}")

            except Exception as e:
                logger.error(f"[mail_service] Failed to attach file: {e}")

        logger.info(
            "[mail_service] connecting to SMTP %s:%s",
            MAIL_SMTP_HOST,
            MAIL_SMTP_PORT,
        )

        # SSL or TLS
        if MAIL_SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(MAIL_SMTP_HOST, MAIL_SMTP_PORT)
        else:
            server = smtplib.SMTP(MAIL_SMTP_HOST, MAIL_SMTP_PORT)
            server.starttls()

        try:
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)
            logger.info(f"✉️ Email sent with attachment: {subject}")
        finally:
            server.quit()

    except Exception as e:
        logger.error("❌ Failed to send email", exc_info=True)
