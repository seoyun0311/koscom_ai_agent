# app_mcp/reports/generator.py
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict

from app_mcp.core.config import ARTIFACTS_DIR, ensure_artifacts_dir
from app_mcp.reports.fill_docx_template import fill_docx_template

logger = logging.getLogger(__name__)

StateDict = Dict[str, Any]


def _build_report_context(period: str, state: StateDict) -> Dict[str, Any]:
    """
    월간 MCP DOCX 보고서에 들어갈 context 생성 함수.

    state 구조 예시:
        - summary.final_grade
        - collateral_monthly.{grade, avg_ratio, min_ratio, risk_level}
        - peg_monthly.{grade, avg_depeg, alert_count, risk_level}
        - liquidity_monthly.{grade, avg_liquidity_ratio, risk_level}
        - por_monthly.{grade, avg_failure_rate, risk_level}
        - consistency.{status, issues}
    """

    summary = state.get("summary", {})
    collateral = state.get("collateral_monthly", {})
    peg = state.get("peg_monthly", {})
    disclosure = state.get("disclosure_monthly", {})  # 필요 시 확장
    liquidity = state.get("liquidity_monthly", {})
    por = state.get("por_monthly", {})
    consistency = state.get("consistency", {})

    final_grade = summary.get("final_grade", "N/A")

    context: Dict[str, Any] = {
        # 기본 정보
        "period": period,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),

        # 종합 평가
        "final_grade": final_grade,

        # 담보(Collateral)
        "collateral_grade": collateral.get("grade", "N/A"),
        "collateral_avg_ratio": f"{collateral.get('avg_ratio', 0):.2%}",
        "collateral_min_ratio": f"{collateral.get('min_ratio', 0):.2%}",
        "collateral_risk_level": collateral.get("risk_level", "N/A"),

        # 페깅(Peg)
        "peg_grade": peg.get("grade", "N/A"),
        "peg_avg_depeg": f"{peg.get('avg_depeg', 0):.3%}",
        "peg_alert_count": peg.get("alert_count", 0),
        "peg_risk_level": peg.get("risk_level", "N/A"),

        # 유동성(Liquidity)
        "liquidity_grade": liquidity.get("grade", "N/A"),
        "liquidity_avg_ratio": f"{liquidity.get('avg_liquidity_ratio', 0):.1%}",
        "liquidity_risk_level": liquidity.get("risk_level", "N/A"),

        # PoR(Proof of Reserves)
        "por_grade": por.get("grade", "N/A"),
        "por_failure_rate": f"{por.get('avg_failure_rate', 0):.2%}",
        "por_risk_level": por.get("risk_level", "N/A"),

        # 일관성(Consistency)
        "consistency_status": consistency.get("status", "ok"),
        "consistency_issues": ", ".join(consistency.get("issues", [])) or "없음",

        # 주요 포인트 (줄바꿈 포함)
        "key_points": "\n".join(summary.get("key_points", [])),
    }

    # 등급별 권고사항 (보고서에 넣기 좋게 미리 결정)
    recommendations = {
        "A": "모든 컴플라이언스 요구사항을 충족하고 있습니다.",
        "B": "대부분의 요구사항을 충족하나, 일부 지표 모니터링이 필요합니다.",
        "C": "개선이 필요한 영역이 있습니다. 개선 계획 수립을 권고합니다.",
        "D": "즉시 조치가 필요합니다. 긴급 대응팀 소집을 권고합니다.",
        "F": "치명적인 위반이 확인되었습니다. 즉시 운영 중단이 필요합니다.",
    }
    context["recommendation"] = recommendations.get(final_grade, "평가 불가")

    return context


def generate_monthly_report(period: str, state: StateDict, rel_output_path: str) -> str:
    """
    월간 MCP DOCX 리포트를 생성하는 함수.

    - LangGraph의 최종 state를 받아서
    - DOCX 템플릿을 채워
    - artifacts 디렉토리에 저장한다.
    """

    # artifacts 디렉토리 보장
    ensure_artifacts_dir()

    # 템플릿 경로
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(base_dir, "templates")
    template_path = os.path.join(template_dir, "monthly_report_template.docx")

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Monthly report template not found: {template_path}")

    # 출력 경로 (상대 경로면 ARTIFACTS_DIR 기준)
    if os.path.isabs(rel_output_path):
        output_path = rel_output_path
    else:
        output_path = str(ARTIFACTS_DIR / rel_output_path)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 템플릿에 주입할 context 생성
    context = _build_report_context(period, state)

    # DOCX 생성
    saved_path = fill_docx_template(template_path, output_path, context)

    logger.info("[generate_monthly_report] DOCX report written to %s", saved_path)
    return saved_path


# ─────────────────────────────────────────
# 테스트/개발용 헬퍼 (DOCX 버전)
# ─────────────────────────────────────────

def generate_sample_report(period: str = "2025-10") -> str:
    """
    테스트용 샘플 DOCX 리포트 생성.

    사용 예:
        >>> from app_mcp.reports.generator import generate_sample_report
        >>> path = generate_sample_report()
        >>> print(path)
    """

    dummy_state: StateDict = {
        "period": period,
        "summary": {
            "final_grade": "B",
            "key_points": [
                "All systems operational",
                "No critical issues detected",
            ],
        },
        "collateral_monthly": {
            "grade": "A",
            "avg_ratio": 1.15,
            "min_ratio": 1.08,
            "risk_level": "LOW",
        },
        "peg_monthly": {
            "grade": "B",
            "avg_depeg": 0.003,
            "alert_count": 2,
            "risk_level": "MEDIUM",
        },
        "disclosure_monthly": {
            "grade": "A",
        },
        "liquidity_monthly": {
            "grade": "B",
            "avg_liquidity_ratio": 0.22,
            "risk_level": "MEDIUM",
        },
        "por_monthly": {
            "grade": "A",
            "avg_failure_rate": 0.0005,
            "risk_level": "LOW",
        },
        "consistency": {
            "status": "ok",
            "issues": [],
        },
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_rel = f"SAMPLE-{period}-{timestamp}.docx"
    output_path = str(ARTIFACTS_DIR / output_rel)

    return generate_monthly_report(period, dummy_state, output_path)


if __name__ == "__main__":
    import sys

    p = sys.argv[1] if len(sys.argv) > 1 else "2025-10"
    print(f"Generating sample DOCX report for {p}...")
    path = generate_sample_report(p)
    print(f"✓ Report created: {path}")
