# app_mcp/models/human_review_task.py
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app_mcp.core.db import Base


class HumanReviewTask(Base):
    __tablename__ = "human_review_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # ex) "2025-10"
    period: Mapped[str] = mapped_column(String(10), index=True)

    # "pending" | "approved" | "rejected" | "revised" | "completed"
    status: Mapped[str] = mapped_column(String(20), index=True, default="pending")

    # 생성된 DOCX 파일 경로
    report_path: Mapped[str] = mapped_column(Text)

    # 최종 등급/요약/지표 등 JSON 문자열
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # LangGraph 연동용 (thread_id 등)
    flow_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    checkpoint_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ✅ 리뷰 히스토리 추적
    reviewer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # ✅ 재생성 관련
    revision_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "approve" | "reject" | "revise"
    
    # ✅ 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_revised_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_revised_by: Mapped[str | None] = mapped_column(String(100), nullable=True)