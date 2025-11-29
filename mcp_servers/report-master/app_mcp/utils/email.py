# app_mcp/utils/email.py
import os
import smtplib
from email.message import EmailMessage

from app_mcp.core.config import get_settings


def send_report_mail(subject: str, body: str, attachment_path: str):
    """
    MCP 보고서를 워드 파일(docx)로 메일 발송.
    """
    s = get_settings()
    print("[email] username:", repr(s.mail_username))
    print("[email] password:", repr(s.mail_password))
    
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = s.mail_from
    msg["To"] = s.mail_to
    msg.set_content(body)

    # 첨부파일(docx)
    filename = os.path.basename(attachment_path)
    with open(attachment_path, "rb") as f:
        data = f.read()

    msg.add_attachment(
        data,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )

    # SMTP 연결 (Gmail 기준)
    with smtplib.SMTP_SSL(s.mail_smtp_host, s.mail_smtp_port) as server:
        server.login(s.mail_username, s.mail_password)
        server.send_message(msg)
