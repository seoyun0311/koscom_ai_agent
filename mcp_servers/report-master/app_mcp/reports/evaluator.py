# app_mcp/reports/evaluator.py
from typing import List
from app_mcp.models import ReservesPayload, BanksPayload, AuditPayload, ComplianceFinding

# -----------------------------
# 🌟 (임시) 목업 헬퍼들
#   → 친구 서버 붙으면 여기만 교체하면 됨
# -----------------------------
def mock_peg_error() -> float:
    """
    환산기준(페깅) 이탈 정도를 임시로 목업.
    나중에: 가격 오라클 서버에서 market_price 받아서 계산.
    """
    return 0.003  # 0.3% 이탈 정도라고 가정 (정상 범위)

def mock_report_on_time() -> bool:
    """
    정기보고 기한 내 제출 여부 목업.
    나중에: report_logs 테이블이나 친구 서버에서 상태 가져오기.
    """
    return True

# 유동성 관리: 어떤 자산을 '현금성 자산'으로 볼지 타입 기준
CASH_LIKE_TYPES = {
    "CASH",        # 현금
    "DEPOSIT",     # 요구불/보통 예금
    "T1_BOND",     # T+1 국채
    "MMF",         # 머니마켓펀드 등
}

def compute_liquidity_ratio(reserves: ReservesPayload) -> float:
    total = 0.0
    cash_like = 0.0
    for a in reserves.assets_breakdown:
        total += a.amount
        if a.type in CASH_LIKE_TYPES:
            cash_like += a.amount
    if total <= 0:
        return 0.0
    return cash_like / total


def evaluate_rules(reserves: ReservesPayload,
                   banks: BanksPayload,
                   audit: AuditPayload) -> List[ComplianceFinding]:
    """
    MCP 보고서 5개 항목에 맞춰 ComplianceFinding 생성:
      1. 예치금 보관 의무
      2. 페깅 유지 의무
      3. 정기보고 이행 여부
      4. 유동성 관리
      5. PoR (준비금 공개, 발행량 공개, 감사/무결성)
    """
    out: List[ComplianceFinding] = []

    # ---------------- 1. 예치금 보관 의무 (담보율) ----------------
    cov = reserves.coverage_ratio
    if cov >= 1.0:
        out.append(ComplianceFinding(
            article="reserve_requirement",
            status="compliant",
            summary=f"담보율 {cov:.3f} (기준 ≥ 1.0) 충족",
            evidence_ref=["reserves.coverage_ratio"]
        ))
    elif cov >= 0.95:
        out.append(ComplianceFinding(
            article="reserve_requirement",
            status="conditional",
            summary=f"담보율 {cov:.3f} (0.95~1.0) – 단기 개입 필요",
            evidence_ref=["reserves.coverage_ratio"]
        ))
    else:
        out.append(ComplianceFinding(
            article="reserve_requirement",
            status="non-compliant",
            summary=f"담보율 {cov:.3f} (기준 0.95 미만) – 심각한 담보 부족",
            evidence_ref=["reserves.coverage_ratio"]
        ))

    # ---------------- 2. 페깅 유지 의무 (목업) ----------------
    peg_error = mock_peg_error()
    if peg_error <= 0.005:
        out.append(ComplianceFinding(
            article="peg_stability",
            status="compliant",
            summary=f"페깅 이탈 {peg_error*100:.2f}% (기준 ±0.5% 이내) – 안정",
            evidence_ref=[]
        ))
    elif peg_error <= 0.02:
        out.append(ComplianceFinding(
            article="peg_stability",
            status="conditional",
            summary=f"페깅 이탈 {peg_error*100:.2f}% (0.5~2%) – 모니터링 필요",
            evidence_ref=[]
        ))
    else:
        out.append(ComplianceFinding(
            article="peg_stability",
            status="non-compliant",
            summary=f"페깅 이탈 {peg_error*100:.2f}% (2% 초과) – 디페깅 위험",
            evidence_ref=[]
        ))

    # ---------------- 3. 정기보고 이행 여부 (목업) ----------------
    report_ok = mock_report_on_time()
    if report_ok:
        out.append(ComplianceFinding(
            article="periodic_reporting",
            status="compliant",
            summary="정기보고서가 기한 내 제출된 것으로 확인(임시 목업 기준).",
            evidence_ref=[]
        ))
    else:
        out.append(ComplianceFinding(
            article="periodic_reporting",
            status="non-compliant",
            summary="정기보고서 제출 지연 또는 미제출 상태(임시 목업 기준).",
            evidence_ref=[]
        ))

    # ---------------- 4. 유동성 관리 ----------------
    liq = compute_liquidity_ratio(reserves)
    if liq >= 0.7:
        out.append(ComplianceFinding(
            article="liquidity_management",
            status="compliant",
            summary=f"현금성 자산 비율 {liq:.2%} (기준 ≥ 70%) 충족",
            evidence_ref=["reserves.assets_breakdown"]
        ))
    elif liq >= 0.5:
        out.append(ComplianceFinding(
            article="liquidity_management",
            status="conditional",
            summary=f"현금성 자산 비율 {liq:.2%} (50~70%) – 버퍼 축소, 모니터링 필요",
            evidence_ref=["reserves.assets_breakdown"]
        ))
    else:
        out.append(ComplianceFinding(
            article="liquidity_management",
            status="non-compliant",
            summary=f"현금성 자산 비율 {liq:.2%} (기준 50% 미만) – 환매 대응 위험",
            evidence_ref=["reserves.assets_breakdown"]
        ))

    # ---------------- 5. Proof of Reserve (PoR) ----------------
    # 5-1. 준비금 전체 공개
    if reserves.assets_breakdown and reserves.liabilities:
        out.append(ComplianceFinding(
            article="por_reserves_disclosure",
            status="compliant",
            summary="준비자산 구성 및 부채(발행량)가 보고서에 포함되어 PoR 기반 공개가 가능.",
            evidence_ref=["reserves.assets_breakdown", "reserves.liabilities"]
        ))
    else:
        out.append(ComplianceFinding(
            article="por_reserves_disclosure",
            status="non-compliant",
            summary="준비자산/부채 정보가 부족하여 PoR 공개 기준을 충족하지 못함.",
            evidence_ref=[]
        ))

    # 5-2. 총발행량 공개
    try:
        supply = reserves.liabilities.circulating_supply
    except Exception:
        supply = None

    if supply is not None:
        out.append(ComplianceFinding(
            article="por_supply_disclosure",
            status="compliant",
            summary=f"총 발행량(circulating supply={supply}) 정보가 공개되어 PoR 계산 가능.",
            evidence_ref=["reserves.liabilities.circulating_supply"]
        ))
    else:
        out.append(ComplianceFinding(
            article="por_supply_disclosure",
            status="non-compliant",
            summary="총 발행량 정보가 없어 PoR 계산 및 공개가 불가능.",
            evidence_ref=[]
        ))

    # 5-3. 감사·무결성 (Merkle, Hash, Audit Log)
    if audit.merkle_root and len(audit.events) > 0:
        out.append(ComplianceFinding(
            article="por_audit_integrity",
            status="compliant",
            summary="Merkle 루트 및 감사 이벤트 로그가 존재하여 무결성 검증 가능.",
            evidence_ref=["audit.merkle_root", "audit.events"]
        ))
    else:
        out.append(ComplianceFinding(
            article="por_audit_integrity",
            status="non-compliant",
            summary="감사 로그 또는 Merkle 정보가 부족하여 무결성 보장이 어려움.",
            evidence_ref=[]
        ))

    return out
