# app_mcp/models/realtime_risk_snapshot.py
from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, Numeric, String,
    DateTime, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app_mcp.core.db import Base


class RealtimeRiskSnapshot(Base):
    __tablename__ = "realtime_risk_snapshot"
    __table_args__ = {"schema": "stablecoin"}  # ★ PostgreSQL 스키마 지정

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # PostgreSQL TIMESTAMPTZ 사용
    occurred_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # 실수/비율 계열은 Numeric(12,6) 사용
    tvl = Column(BigInteger, nullable=False)
    reserve_ratio = Column(Numeric(12, 6), nullable=False)
    peg_deviation = Column(Numeric(12, 6), nullable=False)
    liquidity_score = Column(Numeric(12, 6), nullable=False)

    # CRIT 전용 저장
    risk_level = Column(String, nullable=False)

    # 원본 메트릭 전체
    metrics_json = Column(JSONB)
