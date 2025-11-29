# app_mcp/models/realtime_snapshot.py
# from __future__ import annotations
#from dataclasses import dataclass
from datetime import datetime
#from typing import Optional, Dict, Any
from sqlalchemy import Column, Integer, Float, String, DateTime, JSON
from app_mcp.core.db import Base





class RealtimeSnapshot(Base):
    __tablename__ = "realtime_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 언제 찍힌 스냅샷인지 (UTC 기준 or KST 기준 – 내부적으로는 UTC 추천)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # 핵심 지표들 (필요하면 나중에 추가/수정)
    tvl = Column(Float, nullable=True)                # 총 락업 자산(Total Value Locked)
    reserve_ratio = Column(Float, nullable=True)      # 준비자산 / 부채 비율
    peg_deviation = Column(Float, nullable=True)      # 1달러에서 얼마나 벗어났는지 (절댓값)
    liquidity_score = Column(Float, nullable=True)    # 유동성 지표(원하면 나중에 정의)

    # 전체 리스크 레벨 (LOW / MEDIUM / HIGH / CRITICAL 등)
    risk_level = Column(String(20), nullable=False, index=True)

    # 원시 데이터 전체를 남기고 싶으면 (나중에 구조 바뀌어도 디버깅 가능)
    raw_payload = Column(JSON, nullable=True)