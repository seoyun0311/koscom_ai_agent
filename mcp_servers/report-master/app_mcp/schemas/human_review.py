# app_mcp/schemas/human_review.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class HumanReviewTaskBase(BaseModel):
    id: int
    period: str
    status: str
    report_path: str
    created_at: datetime

    
    # ✅ 추가 필드
    revision_count: int = 0
    last_decision: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class HumanReviewTaskListItem(HumanReviewTaskBase):
    final_grade: Optional[str] = None  # summary_json에서 파싱해 넣어도 되고, 지금은 None


class HumanReviewTaskDetail(HumanReviewTaskBase):
    summary_json: Optional[str] = None
    flow_run_id: Optional[str] = None
    checkpoint_id: Optional[str] = None
    reviewer: Optional[str] = None
    comment: Optional[str] = None
    decided_at: Optional[datetime] = None


class HumanReviewDecisionRequest(BaseModel):
    decision: str  # "approve" or "reject"
    comment: Optional[str] = None
