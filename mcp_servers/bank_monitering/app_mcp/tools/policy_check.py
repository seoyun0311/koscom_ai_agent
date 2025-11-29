# app_mcp/tools/policy_check.py

from __future__ import annotations

from typing import Any, Dict, List
import logging
from mcp.server.fastmcp import FastMCP

from core.policy_engine import (
    PolicyEngine,
    BankExposureInput,
    PolicyEvaluationResult,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────
# 만기 표준화
# ──────────────────────────────────────

def _normalize_maturity_bucket(raw: Any) -> str:
    if raw is None:
        return "UNKNOWN"

    bucket = str(raw).strip().upper()

    if bucket in ("ON", "O/N", "CALL", "OVERNIGHT"):
        return "OVERNIGHT"
    if bucket in ("7D", "7_DAY", "WITHIN_7D"):
        return "WITHIN_7D"
    if bucket in ("1M", "1_MONTH", "WITHIN_1M"):
        return "WITHIN_1M"
    if bucket in ("3M", "3_MONTH", "WITHIN_3M"):
        return "WITHIN_3M"

    return "UNKNOWN"


# ──────────────────────────────────────
# 기관 타입 자동 감지 (🔥 버그 수정 버전)
# ──────────────────────────────────────

def _detect_institution_type(bank_id: str | None, name: str | None) -> str:
    key = (bank_id or name or "").lower()

    # 1) 증권사
    # - nh투자, 미래에셋, 키움, 삼성증권 등
    if any(x in key for x in ["nh투자", "증권", "미래에셋", "키움", "대신증권"]):
        return "broker"

    # "nh" 를 prefix 로만 허용 (shinhan, kbnh 등 오차 방지)
    if key.startswith("nh") and "은행" not in key:
        return "broker"

    # 2) 시중은행
    if "신한" in key or "shinhan" in key:
        return "commercial_bank"
    if "국민" in key or "kb" in key or "kbstar" in key:
        return "commercial_bank"
    if "우리은행" in key or "woori" in key:
        return "commercial_bank"
    if "하나은행" in key or "hana" in key:
        return "commercial_bank"

    # 3) 정책 금융기관
    if "kdb" in key or "산업은행" in key:
        return "policy_bank"
    if "ibk" in key or "기업은행" in key:
        return "policy_bank"

    # 4) 예탁결제원
    if "ksd" in key or "예탁" in key:
        return "custody_agent"

    return "other"


# ───────────────────────────────────────────────────────
# 자동 분해
# ───────────────────────────────────────────────────────

AUTO_MATURITY_DISTRIBUTION = {
    "OVERNIGHT": 0.80,
    "WITHIN_7D": 0.10,
    "WITHIN_1M": 0.07,
    "WITHIN_3M": 0.03,
}


def _split_auto_maturity(
    bank_id: str,
    name: str,
    group_id: str | None,
    inst_type: str,
    is_policy: bool,
    balance: float,
    credit_rating: str | None,
) -> List[BankExposureInput]:

    out: List[BankExposureInput] = []

    for bucket, ratio in AUTO_MATURITY_DISTRIBUTION.items():
        out.append(
            BankExposureInput(
                bank_id=bank_id,
                name=name,
                group_id=group_id,
                is_policy_bank=is_policy,
                exposure=balance * ratio,
                credit_rating=credit_rating,
                maturity_bucket=bucket,
                type=inst_type,
            )
        )

    return out


# ──────────────────────────────────────
# Payload → BankExposureInput 변환 (🔥 role 처리 수정)
# ──────────────────────────────────────

def _parse_exposures_payload(payload: Dict[str, Any]) -> List[BankExposureInput]:

    if not payload:
        return []

    items = payload.get("exposures")
    if isinstance(items, list):
        result: List[BankExposureInput] = []

        for x in items:
            bank_id = str(x.get("bank_id") or x.get("id") or "")
            name = str(x.get("name") or x.get("bank_name") or bank_id)
            group_id = x.get("group_id")
            balance = float(x.get("exposure") or x.get("balance") or 0.0)
            credit_rating = x.get("credit_rating")

            inst_type = _detect_institution_type(bank_id, name)
            maturity_bucket = _normalize_maturity_bucket(x.get("maturity_bucket"))

            is_policy = bool(x.get("is_policy_bank") or inst_type == "policy_bank")

            # 🔥 자동 분해
            if maturity_bucket in ("UNKNOWN", "OVERNIGHT"):
                result.extend(
                    _split_auto_maturity(
                        bank_id, name, group_id,
                        inst_type, is_policy, balance, credit_rating
                    )
                )
                continue

            result.append(
                BankExposureInput(
                    bank_id=bank_id,
                    name=name,
                    group_id=group_id,
                    is_policy_bank=is_policy,
                    exposure=balance,
                    credit_rating=credit_rating,
                    maturity_bucket=maturity_bucket,
                    type=inst_type,
                )
            )

        return result

    # UI 구조 (banks)
    banks = payload.get("banks", [])
    result = []

    for b in banks:
        bank_id = str(b.get("id") or b.get("bank_id") or "")
        name = str(b.get("name") or b.get("bank_name") or "")
        balance = float(b.get("balance") or b.get("exposure") or 0.0)
        group_id = b.get("group_id")
        credit_rating = b.get("credit_rating")

        inst_type = _detect_institution_type(bank_id, name)
        maturity_bucket = _normalize_maturity_bucket(b.get("maturity_bucket"))
        is_policy = bool(b.get("is_policy_bank") or inst_type == "policy_bank")

        if maturity_bucket in ("UNKNOWN", "OVERNIGHT"):
            result.extend(
                _split_auto_maturity(
                    bank_id, name, group_id,
                    inst_type, is_policy, balance, credit_rating
                )
            )
            continue

        result.append(
            BankExposureInput(
                bank_id=bank_id,
                name=name,
                group_id=group_id,
                is_policy_bank=is_policy,
                exposure=balance,
                credit_rating=credit_rating,
                maturity_bucket=maturity_bucket,
                type=inst_type,
            )
        )

    return result


# ──────────────────────────────────────
# MCP Tools
# ──────────────────────────────────────

async def check_policy_compliance(exposures: Dict[str, Any]) -> Dict[str, Any]:

    engine = PolicyEngine()
    exp_list = _parse_exposures_payload(exposures)

    # 🔥 custody 제거가 이제 정상 작동함
    exp_list = [b for b in exp_list if b.type != "custody_agent"]

    logger.info("check_policy_compliance: %d banks after filter", len(exp_list))

    report: PolicyEvaluationResult = await engine.generate_violations_report(exp_list)

    return {
        "highest_level": report.highest_level.value,
        "summary": report.summary,
        "violations": [v.model_dump() for v in report.violations],
    }


async def get_rebalancing_suggestions(
    violations: List[Dict[str, Any]],
) -> Dict[str, Any]:

    suggestions = []

    for v in violations or []:
        v_type = v.get("type")
        level = v.get("level")
        details = v.get("details", {})

        # unwrap enum
        if hasattr(v_type, "value"):
            v_type = v_type.value
        if hasattr(level, "value"):
            level = level.value

        if v_type in ("EXPOSURE_LIMIT", "CREDIT_RATING_LIMIT") and level == "CRITICAL":
            bank_name = details.get("bank_name")
            excess_amt = details.get("excess_amount")

            suggestions.append({
                "category": "EXPOSURE_REDUCTION",
                "target": bank_name,
                "excess_amount": excess_amt,
                "comment": (
                    f"{bank_name} 익스포저가 한도를 초과했습니다. "
                    f"{excess_amt:,.0f}원 이상 회수하십시오."
                ),
            })

        elif v_type == "MATURITY_DISTRIBUTION":
            bucket = details.get("bucket")
            direction = details.get("direction")

            suggestions.append({
                "category": "MATURITY_ADJUSTMENT",
                "bucket": bucket,
                "direction": direction,
                "comment": (
                    f"{bucket} 만기 비중이 기준을 벗어났습니다. 조정이 필요합니다."
                ),
            })

    return {"suggestions": suggestions}


# ──────────────────────────────────────
# MCP 등록
# ──────────────────────────────────────

def register(mcp: FastMCP) -> None:
    mcp.add_tool(
        check_policy_compliance,
        name="check_policy_compliance",
        description="은행별 예치 정책 준수 여부 검사",
    )
    mcp.add_tool(
        get_rebalancing_suggestions,
        name="get_rebalancing_suggestions",
        description="Policy 위반 기반 재배치 권고 생성",
    )
