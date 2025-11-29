# app_mcp/services/risk_rules.py
from __future__ import annotations
from enum import Enum
from typing import Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """리스크 등급"""
    OK = "OK"
    WARNING = "WARN"
    CRITICAL = "CRIT"


class RiskThresholds:
    """
    모든 리스크 판단 기준을 한 곳에서 관리.
    15분 모니터링 + 월간 LangGraph 모두 이 값을 참조.
    """
    # 담보율 (Collateral Ratio)
    COLLATERAL_CRITICAL = 1.05
    COLLATERAL_WARNING = 1.08
    COLLATERAL_SAFE = 1.10

    # 페깅 (Peg Deviation)
    PEG_CRITICAL = 0.01       # 1%
    PEG_WARNING = 0.005       # 0.5%

    # 유동성 (Liquidity Ratio)
    LIQUIDITY_CRITICAL = 0.15
    LIQUIDITY_WARNING = 0.20

    # PoR 실패율
    POR_FAILURE_CRITICAL = 0.1   # 10%
    POR_FAILURE_WARNING = 0.05   # 5%


@dataclass
class RiskEvaluation:
    """리스크 평가 결과"""
    level: RiskLevel
    score: float         # 0~100
    alert_type: str
    message: str
    details: Dict[str, Any]


def evaluate_collateral_risk(ratio: float) -> RiskEvaluation:
    """담보율 리스크 평가"""
    if ratio < RiskThresholds.COLLATERAL_CRITICAL:
        return RiskEvaluation(
            level=RiskLevel.CRITICAL,
            score=20,
            alert_type="collateral_critical",
            message=f"Collateral ratio critically low: {ratio:.4f}",
            details={"ratio": ratio, "threshold": RiskThresholds.COLLATERAL_CRITICAL},
        )
    elif ratio < RiskThresholds.COLLATERAL_WARNING:
        return RiskEvaluation(
            level=RiskLevel.WARNING,
            score=50,
            alert_type="collateral_warning",
            message=f"Collateral ratio below warning: {ratio:.4f}",
            details={"ratio": ratio, "threshold": RiskThresholds.COLLATERAL_WARNING},
        )
    else:
        return RiskEvaluation(
            level=RiskLevel.OK,
            score=80,
            alert_type="",
            message="Collateral ratio healthy",
            details={"ratio": ratio},
        )


def evaluate_peg_risk(deviation: float) -> RiskEvaluation:
    """페깅 리스크 평가"""
    abs_dev = abs(deviation)

    if abs_dev > RiskThresholds.PEG_CRITICAL:
        return RiskEvaluation(
            level=RiskLevel.CRITICAL,
            score=15,
            alert_type="peg_critical",
            message=f"Peg deviation CRITICAL: {deviation:.4f}",
            details={"deviation": deviation, "threshold": RiskThresholds.PEG_CRITICAL},
        )
    elif abs_dev > RiskThresholds.PEG_WARNING:
        return RiskEvaluation(
            level=RiskLevel.WARNING,
            score=55,
            alert_type="peg_warning",
            message=f"Peg deviation warning: {deviation:.4f}",
            details={"deviation": deviation, "threshold": RiskThresholds.PEG_WARNING},
        )
    else:
        return RiskEvaluation(
            level=RiskLevel.OK,
            score=85,
            alert_type="",
            message="Peg stable",
            details={"deviation": deviation},
        )


def evaluate_liquidity_risk(ratio: float) -> RiskEvaluation:
    """유동성 리스크 평가"""
    if ratio < RiskThresholds.LIQUIDITY_CRITICAL:
        return RiskEvaluation(
            level=RiskLevel.CRITICAL,
            score=25,
            alert_type="liquidity_critical",
            message=f"Liquidity CRITICAL: {ratio:.4f}",
            details={"ratio": ratio, "threshold": RiskThresholds.LIQUIDITY_CRITICAL},
        )
    elif ratio < RiskThresholds.LIQUIDITY_WARNING:
        return RiskEvaluation(
            level=RiskLevel.WARNING,
            score=60,
            alert_type="liquidity_warning",
            message=f"Liquidity warning: {ratio:.4f}",
            details={"ratio": ratio, "threshold": RiskThresholds.LIQUIDITY_WARNING},
        )
    else:
        return RiskEvaluation(
            level=RiskLevel.OK,
            score=85,
            alert_type="",
            message="Liquidity healthy",
            details={"ratio": ratio},
        )


def evaluate_overall_risk(
    collateral_ratio: float,
    peg_deviation: float,
    liquidity_ratio: float,
    por_failure_rate: float = 0.0,
) -> RiskEvaluation:
    """
    전체 리스크 종합 평가 (15분 모니터링 + 월간 보고서 공통)
    """
    evaluations = [
        evaluate_collateral_risk(collateral_ratio),
        evaluate_peg_risk(peg_deviation),
        evaluate_liquidity_risk(liquidity_ratio),
    ]

    # 가장 위험한 평가 찾기
    worst_eval = min(evaluations, key=lambda e: e.score)

    # 평균 점수 (월간 보고서 가중치 등 활용 가능)
    avg_score = sum(e.score for e in evaluations) / len(evaluations)

    alert_types = [e.alert_type for e in evaluations if e.alert_type]

    return RiskEvaluation(
        level=worst_eval.level,
        score=avg_score,
        alert_type=",".join(alert_types) if alert_types else "",
        message=f"Overall risk: {worst_eval.level.value}",
        details={
            "collateral": collateral_ratio,
            "peg_deviation": peg_deviation,
            "liquidity": liquidity_ratio,
            "individual_evaluations": [
                {"type": "collateral", "level": evaluations[0].level.value, "score": evaluations[0].score},
                {"type": "peg", "level": evaluations[1].level.value, "score": evaluations[1].score},
                {"type": "liquidity", "level": evaluations[2].level.value, "score": evaluations[2].score},
            ],
        },
    )


def map_risk_level_to_grade(level: RiskLevel) -> str:
    """RiskLevel → 월간 보고서 grade(A~D) 변환"""
    mapping = {
        RiskLevel.OK: "A",
        RiskLevel.WARNING: "B",
        RiskLevel.CRITICAL: "D",
    }
    return mapping.get(level, "C")
