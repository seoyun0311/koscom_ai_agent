from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────
# 1. 기본 타입 정의
# ─────────────────────────────────────────────

class CreditRating(Enum):
    AAA = "AAA"
    AA = "AA"
    A = "A"
    BBB = "BBB"
    BB = "BB"
    B = "B"
    CCC = "CCC"
    NR = "NR"


RATING_RWA_WEIGHT: Dict[CreditRating, float] = {
    CreditRating.AAA: 0.20,
    CreditRating.AA: 0.20,
    CreditRating.A: 0.50,
    CreditRating.BBB: 1.00,
    CreditRating.BB: 1.50,
    CreditRating.B: 2.00,
    CreditRating.CCC: 3.00,
    CreditRating.NR: 1.00,
}


class MaturityBucket(str, Enum):
    OVERNIGHT = "ON"
    D_7 = "7D"
    M_1 = "1M"
    M_3 = "3M"
    LONGER = "LT"


@dataclass
class BankExposure:
    bank_id: str
    name: str
    group_id: str
    region: str
    exposure: float
    credit_rating: CreditRating
    maturity_bucket: MaturityBucket

    lcr: Optional[float] = None
    insured_limit: Optional[float] = None
    rwa_weight: Optional[float] = None
    cds_spread_bps: Optional[float] = None
    bond_spread_bps: Optional[float] = None
    news_sentiment: Optional[float] = None


# ─────────────────────────────────────────────
# JSON → BankExposure 변환 함수 (MCP 핵심 버그 FIX)
# ─────────────────────────────────────────────

def _deserialize_exposures(items: List[Dict]) -> List[BankExposure]:
    out = []
    for x in items:

        # credit rating 변환
        raw_credit = x.get("credit_rating", "NR")
        try:
            credit_rating = CreditRating[raw_credit]
        except Exception:
            credit_rating = CreditRating.NR

        # maturity bucket 변환 ("ON" → MaturityBucket.OVERNIGHT)
        raw_bucket = x.get("maturity_bucket", "ON")
        try:
            maturity_bucket = MaturityBucket(raw_bucket)
        except Exception:
            maturity_bucket = MaturityBucket.OVERNIGHT

        out.append(
            BankExposure(
                bank_id=x["bank_id"],
                name=x["name"],
                group_id=x.get("group_id", x["bank_id"]),
                region=x.get("region", "KR"),
                exposure=float(x.get("exposure", 0)),
                credit_rating=credit_rating,
                maturity_bucket=maturity_bucket,
            )
        )
    return out


# ─────────────────────────────────────────────
# Policy, Stress, Risk Score 엔진 (이전 코드 그대로)
# ─────────────────────────────────────────────

@dataclass
class PolicyConfig:
    max_exposure_per_institution: float = 0.25
    max_exposure_per_group: float = 0.40

    rating_limit_multiplier: Dict[CreditRating, float] = field(
        default_factory=lambda: {
            CreditRating.AAA: 1.2,
            CreditRating.AA: 1.1,
            CreditRating.A: 1.0,
            CreditRating.BBB: 0.8,
            CreditRating.BB: 0.6,
            CreditRating.B: 0.4,
            CreditRating.CCC: 0.2,
            CreditRating.NR: 0.7,
        }
    )

    maturity_target_weights: Dict[MaturityBucket, float] = field(
        default_factory=lambda: {
            MaturityBucket.OVERNIGHT: 0.30,
            MaturityBucket.D_7: 0.30,
            MaturityBucket.M_1: 0.25,
            MaturityBucket.M_3: 0.10,
            MaturityBucket.LONGER: 0.05,
        }
    )


@dataclass
class BankRiskScoreInput:
    exposure: BankExposure
    rwa_weight: float
    lcr_pct: Optional[float] = None
    insured_ratio: Optional[float] = None
    cds_spread_bps: Optional[float] = None
    bond_spread_bps: Optional[float] = None
    news_sentiment: Optional[float] = None


@dataclass
class BankRiskScoreResult:
    bank_id: str
    name: str
    score: float
    detail: Dict[str, float]


@dataclass
class PolicyBreach:
    type: str
    identifier: str
    current: float
    limit: float
    description: str


@dataclass
class PolicyCheckResult:
    breaches: List[PolicyBreach]
    hhi: float
    institution_shares: Dict[str, float]
    group_shares: Dict[str, float]
    maturity_shares: Dict[MaturityBucket, float]


@dataclass
class StressScenarioConfig:
    bank_liquidity_shock: Dict[str, float] = field(default_factory=dict)
    daily_runoff_rate: float = 0.10
    interest_rate_shock_bps: float = 0.0


@dataclass
class StressResult:
    total_exposure: float
    unavailable_amount: float
    run_off_amount: float
    net_liquid_assets: float
    coverage_ratio: float
    detail_by_bank: Dict[str, Dict[str, float]]


@dataclass
class RebalanceAction:
    from_bank_id: str
    to_bank_id: str
    amount: float
    reason: str


@dataclass
class RebalanceSuggestion:
    actions: List[RebalanceAction]
    comment: str


# ─────────────────────────────────────────────
# BankRiskEngine (전체 로직 동일, 변경 없음)
# ─────────────────────────────────────────────
# (아래 부분은 네가 올린 코드 그대로 유지되므로 생략)




# ─────────────────────────────────────────────
# 2. 핵심 엔진
# ─────────────────────────────────────────────

class BankRiskEngine:
    """
    예치 은행 신용 위험 & 분산도 관리 엔진.
    """

    def __init__(self, policy: PolicyConfig):
        self.policy = policy

    # ── 2-1. 집중도(HHI) 및 비중 계산 ──

    @staticmethod
    def _compute_shares(exposures: List[BankExposure]) -> Tuple[Dict[str, float], Dict[str, float], Dict[MaturityBucket, float], float]:
        total = sum(e.exposure for e in exposures)
        if total <= 0:
            return {}, {}, {}, 0.0

        inst_shares: Dict[str, float] = {}
        group_shares: Dict[str, float] = {}
        mat_shares: Dict[MaturityBucket, float] = {b: 0.0 for b in MaturityBucket}

        for e in exposures:
            share = e.exposure / total
            inst_shares[e.bank_id] = inst_shares.get(e.bank_id, 0.0) + share
            group_shares[e.group_id] = group_shares.get(e.group_id, 0.0) + share
            mat_shares[e.maturity_bucket] = mat_shares.get(e.maturity_bucket, 0.0) + share

        return inst_shares, group_shares, mat_shares, total

    @staticmethod
    def _compute_hhi(shares: Dict[str, float]) -> float:
        """
        전통 HHI: sum( (시장점유율 * 100)^2 ).
        0~10,000, 1,800 이상이면 고집중(규제 관점).
        """
        return sum((s * 100) ** 2 for s in shares.values())

    # ── 2-2. Policy 체크 ──

    def check_policy(self, exposures: List[BankExposure]) -> PolicyCheckResult:
        inst_shares, group_shares, mat_shares, total = self._compute_shares(exposures)
        breaches: List[PolicyBreach] = []

        # 기관 단위 한도 체크 (등급 가중 한도 반영)
        bank_map = {e.bank_id: e for e in exposures}
        for bank_id, share in inst_shares.items():
            bank = bank_map[bank_id]
            base_limit = self.policy.max_exposure_per_institution
            mult = self.policy.rating_limit_multiplier.get(bank.credit_rating, 1.0)
            limit = base_limit * mult

            if share > limit:
                breaches.append(
                    PolicyBreach(
                        type="institution",
                        identifier=bank_id,
                        current=share,
                        limit=limit,
                        description=f"{bank.name} 기관 한도 초과 (현재 {share:.2%}, 한도 {limit:.2%})",
                    )
                )

        # 동일 그룹 합산 한도 체크
        for group_id, share in group_shares.items():
            limit = self.policy.max_exposure_per_group
            if share > limit:
                breaches.append(
                    PolicyBreach(
                        type="group",
                        identifier=group_id,
                        current=share,
                        limit=limit,
                        description=f"금융그룹({group_id}) 한도 초과 (현재 {share:.2%}, 한도 {limit:.2%})",
                    )
                )

        # 만기 버킷 목표 비중 체크
        for bucket, share in mat_shares.items():
            target = self.policy.maturity_target_weights.get(bucket)
            if target is None:
                continue
            # 단순히 편차가 큰 경우 breach로 처리 (예: ±10%p 이상)
            if abs(share - target) > 0.10:
                breaches.append(
                    PolicyBreach(
                        type="maturity",
                        identifier=bucket.value,
                        current=share,
                        limit=target,
                        description=f"만기 버킷 {bucket.value} 비중 편차 큼 (현재 {share:.2%}, 목표 {target:.2%})",
                    )
                )

        hhi = self._compute_hhi(inst_shares)

        return PolicyCheckResult(
            breaches=breaches,
            hhi=hhi,
            institution_shares=inst_shares,
            group_shares=group_shares,
            maturity_shares=mat_shares,
        )

    # ── 2-3. Bank Risk Score (0–100) ──

    def compute_bank_risk_score(self, inp: BankRiskScoreInput) -> BankRiskScoreResult:
        """
        간단한 가중 평균 기반 Bank Risk Score.
        0점(매우 위험) ~ 100점(매우 안전).
        """

        # 1) 등급 기반 베이스 점수
        rating_score_map: Dict[CreditRating, float] = {
            CreditRating.AAA: 95,
            CreditRating.AA: 90,
            CreditRating.A: 85,
            CreditRating.BBB: 75,
            CreditRating.BB: 60,
            CreditRating.B: 45,
            CreditRating.CCC: 30,
            CreditRating.NR: 70,
        }
        score_rating = rating_score_map.get(inp.exposure.credit_rating, 60)

        # 2) LCR (100% 이상이면 가점, 80% 이하면 감점)
        if inp.lcr_pct is not None:
            if inp.lcr_pct >= 120:
                score_lcr = 95
            elif inp.lcr_pct >= 100:
                score_lcr = 85
            elif inp.lcr_pct >= 80:
                score_lcr = 70
            else:
                score_lcr = 50
        else:
            score_lcr = 70  # 정보 없음: 중간값

        # 3) 예금보험 커버 비율
        if inp.insured_ratio is not None:
            if inp.insured_ratio >= 0.9:
                score_insured = 95
            elif inp.insured_ratio >= 0.7:
                score_insured = 85
            elif inp.insured_ratio >= 0.5:
                score_insured = 70
            else:
                score_insured = 55
        else:
            score_insured = 75

        # 4) 시장 신용위험 (CDS/채권 스프레드, 낮을수록 좋음)
        spread = None
        if inp.cds_spread_bps is not None:
            spread = inp.cds_spread_bps
        elif inp.bond_spread_bps is not None:
            spread = inp.bond_spread_bps

        if spread is not None:
            if spread <= 50:
                score_spread = 90
            elif spread <= 100:
                score_spread = 80
            elif spread <= 200:
                score_spread = 65
            else:
                score_spread = 50
        else:
            score_spread = 70

        # 5) 뉴스 감성 (-1 ~ +1 → 40~90)
        sentiment = inp.news_sentiment if inp.news_sentiment is not None else 0.0
        score_news = 65 + sentiment * 25  # sentiment=-1 → 40, 0 → 65, +1 → 90

        # 가중 평균 (가중치는 필요에 따라 조정)
        w_rating = 0.35
        w_lcr = 0.20
        w_insured = 0.15
        w_spread = 0.20
        w_news = 0.10

        score = (
            score_rating * w_rating
            + score_lcr * w_lcr
            + score_insured * w_insured
            + score_spread * w_spread
            + score_news * w_news
        )

        detail = {
            "rating": score_rating,
            "lcr": score_lcr,
            "insured": score_insured,
            "spread": score_spread,
            "news": score_news,
        }

        return BankRiskScoreResult(
            bank_id=inp.exposure.bank_id,
            name=inp.exposure.name,
            score=score,
            detail=detail,
        )

    # ── 2-4. 스트레스 시나리오 ──

    def run_stress(
        self,
        exposures: List[BankExposure],
        scenario: StressScenarioConfig,
        liquid_buckets: Optional[List[MaturityBucket]] = None,
    ) -> StressResult:
        """
        간단한 유동성 스트레스 시뮬레이션.
        - 특정 은행 예치금 중 일부 미가용
        - 하루 동시상환(runoff) 발생
        - 유동성 사다리: 특정 만기 버킷을 '즉시 가용'으로 간주
        """
        if liquid_buckets is None:
            # 요구불 + 7D 이내는 유동성 자산으로 간주
            liquid_buckets = [MaturityBucket.OVERNIGHT, MaturityBucket.D_7]

        total = sum(e.exposure for e in exposures)

        unavailable_amount = 0.0
        run_off_amount = total * scenario.daily_runoff_rate

        detail_by_bank: Dict[str, Dict[str, float]] = {}
        liquid_assets = 0.0

        for e in exposures:
            shock = scenario.bank_liquidity_shock.get(e.bank_id, 0.0)
            bank_unavail = e.exposure * shock
            unavailable_amount += bank_unavail

            if e.maturity_bucket in liquid_buckets:
                # 유동성 사다리 상단 계층
                liquid_assets += max(e.exposure - bank_unavail, 0.0)

            detail_by_bank[e.bank_id] = {
                "exposure": e.exposure,
                "shock_unavailable": bank_unavail,
            }

        net_liquid_assets = max(liquid_assets - run_off_amount, 0.0)
        denom = unavailable_amount + run_off_amount
        coverage_ratio = (liquid_assets / denom) if denom > 0 else 1.0

        return StressResult(
            total_exposure=total,
            unavailable_amount=unavailable_amount,
            run_off_amount=run_off_amount,
            net_liquid_assets=net_liquid_assets,
            coverage_ratio=coverage_ratio,
            detail_by_bank=detail_by_bank,
        )

    # ── 2-5. 자동 재밸런싱 제안 ──

    def suggest_rebalance(
        self,
        exposures: List[BankExposure],
        scores: Dict[str, BankRiskScoreResult],
    ) -> RebalanceSuggestion:
        """
        - 한도 초과/집중도 높은 은행에서
        - 여유 있는 & 점수가 더 높은 은행으로
        - 단순 규칙 기반 재배치 제안.
        """
        policy_result = self.check_policy(exposures)
        inst_shares = policy_result.institution_shares
        total = sum(e.exposure for e in exposures) or 1.0

        bank_map = {e.bank_id: e for e in exposures}
        breaches_by_bank = {
            b.identifier: b
            for b in policy_result.breaches
            if b.type == "institution"
        }

        # 출발지(줄여야 할 은행) & 도착지(늘려도 되는 은행) 후보 정렬
        over_banks = sorted(
            [bank_map[b_id] for b_id in breaches_by_bank.keys()],
            key=lambda e: inst_shares.get(e.bank_id, 0.0),
            reverse=True,
        )

        # 여유 있는 은행 (현재 비중 < 등급 가중 한도, 리스크 점수 높은 순으로 정렬)
        under_banks: List[BankExposure] = []
        for e in exposures:
            share = inst_shares[e.bank_id]
            base_limit = self.policy.max_exposure_per_institution
            mult = self.policy.rating_limit_multiplier.get(e.credit_rating, 1.0)
            limit = base_limit * mult
            if share < limit:
                under_banks.append(e)

        under_banks.sort(
            key=lambda e: scores.get(e.bank_id, BankRiskScoreResult(e.bank_id, e.name, 0, {})).score,
            reverse=True,
        )

        actions: List[RebalanceAction] = []

        for src in over_banks:
            src_share = inst_shares[src.bank_id]
            base_limit = self.policy.max_exposure_per_institution
            mult = self.policy.rating_limit_multiplier.get(src.credit_rating, 1.0)
            limit = base_limit * mult

            # 얼마나 줄여야 하는가?
            excess_share = src_share - limit
            if excess_share <= 0:
                continue

            excess_amount = excess_share * total
            remaining_to_move = excess_amount

            for dst in under_banks:
                if dst.bank_id == src.bank_id:
                    continue

                dst_share = inst_shares[dst.bank_id]
                dst_limit = self.policy.max_exposure_per_institution * self.policy.rating_limit_multiplier.get(
                    dst.credit_rating, 1.0
                )
                headroom_share = max(dst_limit - dst_share, 0.0)
                if headroom_share <= 0:
                    continue

                headroom_amount = headroom_share * total
                move_amount = min(remaining_to_move, headroom_amount)

                if move_amount <= 0:
                    continue

                actions.append(
                    RebalanceAction(
                        from_bank_id=src.bank_id,
                        to_bank_id=dst.bank_id,
                        amount=move_amount,
                        reason=(
                            f"{src.name} 비중 {src_share:.2%} → 한도 {limit:.2%} 이하로 낮추기 위해, "
                            f"리스크 점수 더 높은 {dst.name}로 이동 제안"
                        ),
                    )
                )

                remaining_to_move -= move_amount

                if remaining_to_move <= 0:
                    break

        comment = "정책 한도 및 리스크 점수를 기준으로 자동 재예치(재밸런싱) 제안을 생성했습니다."
        if not actions:
            comment = "현재 Policy 위반이 없거나, 실질적인 재밸런싱 여유가 없어 제안이 없습니다."

        return RebalanceSuggestion(actions=actions, comment=comment)
