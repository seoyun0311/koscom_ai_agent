# app_mcp/api/debug_email.py

from fastapi import APIRouter
import logging

from app_mcp.services.mail_service import send_approval_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"])


@router.post("/test-email")
async def test_email():
    """
    Slack / LangGraph 다 빼고
    메일 전송만 단독으로 테스트하는 엔드포인트
    """
    logger.warning("[DEBUG] /debug/test-email called")

    await send_approval_email(
        task_id=999,
        period="2099-01",
        decision="approved",
        comment="TEST from /debug/test-email"
    )

    return {"ok": True, "message": "Email send_approval_email() 호출 완료"}
