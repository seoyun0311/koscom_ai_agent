from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, JSON, DateTime, ForeignKey, Text
from datetime import datetime
from app_mcp.core import Base

# ---------- ORM ----------
class ReportLog(Base):
    __tablename__ = "report_logs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(String(64), index=True, unique=True)
    period: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))  # generated/failed
    conclusion: Mapped[str] = mapped_column(String(16))
    findings_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    artifacts = relationship("Artifact", back_populates="report", cascade="all,delete")

class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_id_fk: Mapped[int] = mapped_column(ForeignKey("report_logs.id"))
    kind: Mapped[str] = mapped_column(String(16))  # html/pdf/json
    path: Mapped[str] = mapped_column(Text)

    report = relationship("ReportLog", back_populates="artifacts")

class RawSource(Base):
    __tablename__ = "raw_sources"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(32))  # reserves/banks/audit
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# ---------- Pydantic I/O ----------
from pydantic import BaseModel, Field
from typing import List, Optional

class ReservesAsset(BaseModel):
    type: str
    amount: float

class ReservesPayload(BaseModel):
    as_of: str
    coverage_ratio: float
    valuation_method: str
    assets_breakdown: List[ReservesAsset]
    liabilities: dict
    flags: List[dict] = Field(default_factory=list)

class Custodian(BaseModel):
    name: str
    country: str
    credit_tier: str
    share: float

class BanksPayload(BaseModel):
    as_of: str
    custodians: List[Custodian]
    concentration_index: float
    alerts: List[dict] = Field(default_factory=list)

class AuditEvent(BaseModel):
    kind: str
    tx: str
    timestamp: str

class AuditPayload(BaseModel):
    as_of_block: str
    events: List[AuditEvent]
    merkle_root: str
    proof_url: Optional[str] = None

class ComplianceFinding(BaseModel):
    article: str
    status: str            # compliant/conditional/non-compliant
    summary: str
    evidence_ref: List[str] = Field(default_factory=list)

class ComplianceReportOut(BaseModel):
    report_id: str
    period: str
    conclusion: str
    findings: List[ComplianceFinding]
    artifacts: dict
