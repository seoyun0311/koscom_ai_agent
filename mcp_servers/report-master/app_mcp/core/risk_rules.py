# core/risk_rules.py

from enum import Enum


class RiskLevel(str, Enum):
    """
    실시간/월간 공통 리스크 레벨 (운영/알림 기준)
    - OK   : 정상 범위
    - WARN : 주의 / 모니터링 필요
    - CRIT : 즉시 조치 필요(심각)
    """
    OK = "OK"
    WARN = "WARN"
    CRIT = "CRIT"


class ComponentGrade(str, Enum):
    """
    지표별 등급 (월간 리포트에서 A~D로 표현)
    - A: 매우 양호
    - B: 양호
    - C: 주의
    - D: 심각
    """
    A = "A"
    B = "B"
    C = "C"
    D = "D"


# ---------------------------
# ① 기본 임계값 설정 (한 군데만!)
# ---------------------------

# 담보 비율 (준비금 / 발행량)
COLLATERAL_THRESHOLDS = {
    "A": 1.15,   # >= 115% (안전 마진 확보)
    "B": 1.10,   # >= 110% (양호)
    "C": 1.03,   # >= 103% (최소 안전 마진)
    # < 103% → D (즉시 조치 필요)
}

# 페그 이탈 (1원 기준 절댓값, 작을수록 좋음)
PEG_DEVIATION_THRESHOLDS = {
    "A": 0.002,  # <= 0.2% (정상)
    "B": 0.005,  # <= 0.5% (주의)
    "C": 0.010,  # <= 1.0% (경고)
    # > 1.0% → D (위기)
}

# 즉시 현금화 가능 자산 / 총 부채 (유동성 비율)
LIQUIDITY_RATIO_THRESHOLDS = {
    "A": 0.30,   # >= 30% (뱅크런 대응 가능)
    "B": 0.20,   # >= 20% (일반적 인출 대응)
    "C": 0.10,   # >= 10% (최소 유동성)
    # < 10% → D (인출 제한 위험)
}


# ---------------------------
# ② 컴포넌트별 등급 함수 (A~D)
# ---------------------------

def grade_collateral_ratio(collateral_ratio: float) -> ComponentGrade:
    if collateral_ratio >= COLLATERAL_THRESHOLDS["A"]:
        return ComponentGrade.A
    if collateral_ratio >= COLLATERAL_THRESHOLDS["B"]:
        return ComponentGrade.B
    if collateral_ratio >= COLLATERAL_THRESHOLDS["C"]:
        return ComponentGrade.C
    return ComponentGrade.D


def grade_peg_deviation(peg_deviation: float) -> ComponentGrade:
    """
    peg_deviation는 (목표가 1원일 때) |price - 1.0| 형태로 들어온다고 가정.
    값이 작을수록 좋기 때문에 부등호 방향이 반대.
    """
    if peg_deviation <= PEG_DEVIATION_THRESHOLDS["A"]:
        return ComponentGrade.A
    if peg_deviation <= PEG_DEVIATION_THRESHOLDS["B"]:
        return ComponentGrade.B
    if peg_deviation <= PEG_DEVIATION_THRESHOLDS["C"]:
        return ComponentGrade.C
    return ComponentGrade.D


def grade_liquidity_ratio(liquidity_ratio: float) -> ComponentGrade:
    if liquidity_ratio >= LIQUIDITY_RATIO_THRESHOLDS["A"]:
        return ComponentGrade.A
    if liquidity_ratio >= LIQUIDITY_RATIO_THRESHOLDS["B"]:
        return ComponentGrade.B
    if liquidity_ratio >= LIQUIDITY_RATIO_THRESHOLDS["C"]:
        return ComponentGrade.C
    return ComponentGrade.D


# ---------------------------
# ③ 전체 RiskLevel 산출 로직
#    (실시간 모니터링 / 월간 공통)
# ---------------------------

def overall_risk_level(
    collateral_ratio: float,
    peg_deviation: float,
    liquidity_ratio: float,
) -> RiskLevel:
    """
    컴포넌트 등급 3개를 기반으로 전체 리스크 레벨(OK / WARN / CRIT) 산출.

    기본 아이디어:
    - 담보/페그에서 D 등급 → CRIT (가장 핵심 지표)
    - 그 외에 하나라도 D → CRIT
    - 하나라도 C → WARN
    - 전부 A 또는 B → OK
    """

    col_grade = grade_collateral_ratio(collateral_ratio)
    peg_grade = grade_peg_deviation(peg_deviation)
    liq_grade = grade_liquidity_ratio(liquidity_ratio)

    grades = [col_grade, peg_grade, liq_grade]

    # 1) 담보 또는 페그가 D면 무조건 CRIT
    if col_grade == ComponentGrade.D or peg_grade == ComponentGrade.D:
        return RiskLevel.CRIT

    # 2) 나머지 지표에서라도 D가 있으면 CRIT
    if ComponentGrade.D in grades:
        return RiskLevel.CRIT

    # 3) 하나라도 C가 있으면 WARN
    if ComponentGrade.C in grades:
        return RiskLevel.WARN

    # 4) 전부 A 또는 B면 OK
    return RiskLevel.OK


# 등급(A~D)을 RiskLevel(OK/WARN/CRIT)로 맵핑 – 월간/실시간 같이 사용 가능
def grade_to_risk_level(grade: ComponentGrade) -> RiskLevel:
    if grade == ComponentGrade.D:
        return RiskLevel.CRIT
    if grade == ComponentGrade.C:
        return RiskLevel.WARN
    return RiskLevel.OK


# 등급(A~D)을 점수(0~1)로 맵핑 – 리포트에서 score 쓰고 싶을 때 사용
def grade_to_score(grade: ComponentGrade) -> float:
    """
    0에 가까울수록 양호, 1에 가까울수록 위험.
    (예: 히트맵/레이다 차트용 스코어)
    """
    mapping = {
        ComponentGrade.A: 0.0,
        ComponentGrade.B: 0.3,
        ComponentGrade.C: 0.6,
        ComponentGrade.D: 1.0,
    }
    return mapping.get(grade, 0.6)


# PoR 전용 임계값 (월간 그래프에서 사용)
class RiskThresholds:
    POR_FAILURE_CRITICAL = 0.01  # 1% 이상 실패 → CRIT 후보
    POR_FAILURE_WARNING = 0.001  # 0.1% 이상 실패 → WARN 후보


def classify_por_failure_rate(failure_rate: float) -> RiskLevel:
    """
    PoR(Proof of Reserve) 실패율로만 본 리스크 레벨.
    - >= 1%   → CRIT
    - >= 0.1% → WARN
    - 그 외   → OK
    """
    if failure_rate >= RiskThresholds.POR_FAILURE_CRITICAL:
        return RiskLevel.CRIT
    if failure_rate >= RiskThresholds.POR_FAILURE_WARNING:
        return RiskLevel.WARN
    return RiskLevel.OK
