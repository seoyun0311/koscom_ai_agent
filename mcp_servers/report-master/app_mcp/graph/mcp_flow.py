from __future__ import annotations

from typing import Any, Dict, TypedDict
import logging
import os

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from app_mcp.services.notifications import notify_monthly_report

from app_mcp.reports.generator import generate_monthly_report
from app_mcp.core.risk_rules import (
    grade_collateral_ratio,
    grade_peg_deviation,
    grade_liquidity_ratio,
    grade_to_risk_level,
    grade_to_score,
    RiskThresholds,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 1) LangGraph State 정의 (단일 버전)
# ─────────────────────────────────────────────

class MCPState(TypedDict, total=False):
    # 입력
    period: str  # "2025-10" 같은 월 단위

    # (1) 로드 결과
    raw_data: Dict[str, Any]

    # (1-α) 데이터 품질
    data_quality: Dict[str, Any]

    # (2)~(6) 평가 결과
    collateral_monthly: Dict[str, Any]
    peg_monthly: Dict[str, Any]
    disclosure_monthly: Dict[str, Any]
    liquidity_monthly: Dict[str, Any]
    por_monthly: Dict[str, Any]

    # (6-α) 모순/일관성 체크
    consistency: Dict[str, Any]

    # (7) 종합 요약
    summary: Dict[str, Any]

    # (7-α) 사람 검토 결과
    human_review: Dict[str, Any]

    # (8) 리포트 생성 결과
    report_path: str

    # 재시도 관련 메타 정보 (무한 루프 방지용)
    retry_counts: Dict[str, int]
    max_retries: Dict[str, int]

    # Human Review / Loop 제어용
    task_id: int
    human_decision: str | None        # "pending" | "approve" | "revise"
    human_feedback: str | None
    revision_count: int
    max_revisions: int


# ─────────────────────────────────────────────
# 2) 각 노드 구현
# ─────────────────────────────────────────────

def load_period_data(state: MCPState) -> MCPState:
    """
    (1) 기간 데이터 로드

    - state에 raw_data가 이미 있으면 (실제 DB/API에서 채워준 것) 그대로 사용
    - 없으면 디버깅/테스트용 mock 데이터를 생성
      → 나중에 monthly_data_service.load_monthly_raw_data()랑 연동 예정
    """
    if state.get("raw_data"):
        logger.info(
            "[load_period_data] Using preloaded raw_data for period=%s",
            state.get("period"),
        )
        return state

    period = state.get("period", "2025-10")

    # TODO: 나중에 snapshot 집계로 대체
    raw_data = {
        "period": period,
        "metrics": {
            "collateral_samples": 120,
            "peg_samples": 120,
            "liquidity_samples": 120,
        },
        "alerts": [],
        "por_logs": [],
        "disclosure_logs": [],
        "days_covered": 28,
        "total_days": 31,
        "last_update_hours_ago": 1,
        "avg_collateral_ratio": 1.12,
        "min_collateral_ratio": 1.03,
        "avg_peg_deviation": 0.002,
        "peg_alert_count": 3,
        "avg_liquidity_ratio": 0.25,
        "avg_por_failure_rate": 0.03,
    }

    logger.info(f"[load_period_data] Loaded MOCK data for period={period}")

    new_state: MCPState = dict(state)
    new_state["raw_data"] = raw_data
    return new_state


def data_quality_check(state: MCPState) -> MCPState:
    """
    (1-α) 데이터 품질 체크 + 재시도 카운트 관리.

    - 커버리지
    - 샘플 수
    - 지표별 completeness
    - 최신성
    - max_retry 초과 여부
    """
    raw = state.get("raw_data", {})

    retry_counts = dict(state.get("retry_counts", {}))
    max_retries = state.get("max_retries") or {"data_load": 3}

    current_retries = retry_counts.get("data_load", 0)

    metrics = raw.get("metrics", {})
    coverage = raw.get("days_covered", 0) / max(raw.get("total_days", 30), 1)
    sample_size_ok = metrics.get("collateral_samples", 0) >= 100
    completeness = all(
        metrics.get(f"{cat}_samples", 0) > 0
        for cat in ["collateral", "peg", "liquidity"]
    )
    recent_data = raw.get("last_update_hours_ago", 999) < 24

    checks = {
        "coverage": coverage,          # 0~1
        "sample_size_ok": sample_size_ok,
        "completeness": completeness,
        "recent_data": recent_data,
    }

    critical_issues = [
        key
        for key, value in checks.items()
        if (isinstance(value, bool) and not value)
        or (isinstance(value, float) and value < 0.8)
    ]

    has_critical_gap = len(critical_issues) > 0
    max_retry_exceeded = (
        current_retries >= max_retries.get("data_load", 3)
        if has_critical_gap
        else False
    )

    data_quality = {
        **checks,
        "critical_issues": critical_issues,
        "has_critical_gap": has_critical_gap,
        "retry_count": current_retries,
        "max_retry_exceeded": max_retry_exceeded,
    }

    # 다음번 재시도를 위해 카운트 증가 (critical할 때만)
    if has_critical_gap and not max_retry_exceeded:
        retry_counts["data_load"] = current_retries + 1

    logger.info(
        "[data_quality_check] coverage=%.3f, issues=%s, retry=%d, max_exceeded=%s",
        coverage,
        critical_issues,
        current_retries,
        max_retry_exceeded,
    )

    new_state: MCPState = dict(state)
    new_state["data_quality"] = data_quality
    new_state["retry_counts"] = retry_counts
    new_state["max_retries"] = max_retries
    return new_state


# ─────────────────────────────────────────────
# (2)~(6) 월간 평가 노드 – RiskRules 기반
# ─────────────────────────────────────────────

def eval_collateral_monthly(state: MCPState) -> MCPState:
    """(2) 담보율 평가 – 공통 리스크 룰 사용."""
    new_state: MCPState = dict(state)

    try:
        raw_data = state.get("raw_data")
        if not raw_data:
            raise ValueError("raw_data missing for collateral evaluation")

        avg_ratio = raw_data.get("avg_collateral_ratio", 1.12)
        min_ratio = raw_data.get("min_collateral_ratio", 1.03)

        grade_enum = grade_collateral_ratio(avg_ratio)
        risk_level_enum = grade_to_risk_level(grade_enum)
        risk_score = grade_to_score(grade_enum)

        collateral = {
            "grade": grade_enum.value,
            "avg_ratio": avg_ratio,
            "min_ratio": min_ratio,
            "risk_level": risk_level_enum.value,
            "risk_score": risk_score,
        }

        logger.info(
            "[eval_collateral_monthly] grade=%s, risk=%s, avg=%.4f",
            grade_enum.value,
            risk_level_enum.value,
            avg_ratio,
        )

    except Exception as e:
        logger.error(f"[eval_collateral_monthly] Failed: {e}")
        collateral = {
            "grade": "F",
            "error": str(e),
            "fallback": True,
        }

    new_state["collateral_monthly"] = collateral
    return new_state


def eval_peg_monthly(state: MCPState) -> MCPState:
    """(3) 페깅 평가 – 공통 리스크 룰 사용."""
    new_state: MCPState = dict(state)

    try:
        raw_data = state.get("raw_data")
        if not raw_data:
            raise ValueError("raw_data missing for peg evaluation")

        avg_depeg = raw_data.get("avg_peg_deviation", 0.002)

        grade_enum = grade_peg_deviation(avg_depeg)
        risk_level_enum = grade_to_risk_level(grade_enum)
        risk_score = grade_to_score(grade_enum)

        peg = {
            "grade": grade_enum.value,
            "avg_depeg": avg_depeg,
            "risk_level": risk_level_enum.value,
            "risk_score": risk_score,
            "alert_count": raw_data.get("peg_alert_count", 0),
        }

        logger.info(
            "[eval_peg_monthly] grade=%s, risk=%s, avg_depeg=%.4f",
            grade_enum.value,
            risk_level_enum.value,
            avg_depeg,
        )

    except Exception as e:
        logger.error(f"[eval_peg_monthly] Failed: {e}")
        peg = {
            "grade": "F",
            "error": str(e),
            "fallback": True,
        }

    new_state["peg_monthly"] = peg
    return new_state


def eval_disclosure_monthly(state: MCPState) -> MCPState:
    """(4) 보고의무(공시) 평가 – 일단 단순 Mock."""
    new_state: MCPState = dict(state)

    try:
        disclosure = {
            "grade": "A",
            "late_reports": 0,
            "missing_reports": 0,
            "notes": "All disclosures submitted on time.",
        }

        logger.info(
            "[eval_disclosure_monthly] Completed: grade=%s, late=%d, missing=%d",
            disclosure["grade"],
            disclosure["late_reports"],
            disclosure["missing_reports"],
        )
    except Exception as e:
        logger.error(f"[eval_disclosure_monthly] Failed: {e}")
        disclosure = {
            "grade": "F",
            "error": str(e),
            "fallback": True,
        }

    new_state["disclosure_monthly"] = disclosure
    return new_state


def eval_liquidity_monthly(state: MCPState) -> MCPState:
    """(5) 유동성 평가 – 공통 리스크 룰 사용."""
    new_state: MCPState = dict(state)

    try:
        raw_data = state.get("raw_data")
        if not raw_data:
            raise ValueError("raw_data missing for liquidity evaluation")

        avg_liquidity = raw_data.get("avg_liquidity_ratio", 0.25)

        grade_enum = grade_liquidity_ratio(avg_liquidity)
        risk_level_enum = grade_to_risk_level(grade_enum)
        risk_score = grade_to_score(grade_enum)

        liquidity = {
            "grade": grade_enum.value,
            "avg_liquidity_ratio": avg_liquidity,
            "risk_level": risk_level_enum.value,
            "risk_score": risk_score,
        }

        logger.info(
            "[eval_liquidity_monthly] grade=%s, risk=%s, avg_liq=%.4f",
            grade_enum.value,
            risk_level_enum.value,
            avg_liquidity,
        )

    except Exception as e:
        logger.error(f"[eval_liquidity_monthly] Failed: {e}")
        liquidity = {
            "grade": "F",
            "error": str(e),
            "fallback": True,
        }

    new_state["liquidity_monthly"] = liquidity
    return new_state


def eval_por_monthly(state: MCPState) -> MCPState:
    """(6) PoR / 무결성 평가 – PoR 실패율 기준."""
    new_state: MCPState = dict(state)

    try:
        raw_data = state.get("raw_data")
        if not raw_data:
            raise ValueError("raw_data missing for PoR evaluation")

        por_failure_rate = raw_data.get("avg_por_failure_rate", 0.03)

        if por_failure_rate > RiskThresholds.POR_FAILURE_CRITICAL:
            level = "CRIT"
            grade = "D"
        elif por_failure_rate > RiskThresholds.POR_FAILURE_WARNING:
            level = "WARN"
            grade = "B"
        else:
            level = "OK"
            grade = "A"

        por = {
            "grade": grade,
            "avg_failure_rate": por_failure_rate,
            "risk_level": level,
        }

        logger.info(
            "[eval_por_monthly] grade=%s, level=%s, failure_rate=%.4f",
            grade,
            level,
            por_failure_rate,
        )

    except Exception as e:
        logger.error(f"[eval_por_monthly] Failed: {e}")
        por = {
            "grade": "F",
            "error": str(e),
            "fallback": True,
        }

    new_state["por_monthly"] = por
    return new_state


def cross_check_consistency(state: MCPState) -> MCPState:
    """
    (6-α) 담보/페깅/유동성/PoR간 모순 여부 체크.
    되돌아갈지 여부는 라우터 함수에서 결정.
    """
    collateral = state.get("collateral_monthly", {})
    liquidity = state.get("liquidity_monthly", {})
    peg = state.get("peg_monthly", {})
    por = state.get("por_monthly", {})

    issues = []

    if collateral.get("grade") == "A" and liquidity.get("grade") == "D":
        issues.append("collateral_A_but_liquidity_D")

    if peg.get("grade") == "D" and (
        collateral.get("grade") == "A"
        and liquidity.get("grade") == "A"
    ):
        issues.append("peg_D_but_others_A")

    if por.get("grade") == "D" and all(
        g.get("grade") == "A" for g in [collateral, liquidity, peg]
    ):
        issues.append("por_D_but_risks_A")

    if collateral.get("low_sample"):
        issues.append("collateral_low_sample")

    if not issues:
        status = "ok"
    elif any("liquidity" in x for x in issues):
        status = "recheck_liquidity"
    else:
        status = "recheck_collateral"

    consistency = {
        "status": status,
        "issues": issues,
    }

    logger.info(
        "[cross_check_consistency] status=%s, issues=%s",
        status,
        issues,
    )

    new_state: MCPState = dict(state)
    new_state["consistency"] = consistency
    return new_state


# ─────────────────────────────────────────────
# 7) summarize_conclusion (revise loop 반영)
# ─────────────────────────────────────────────

def summarize_conclusion(state: MCPState) -> MCPState:
    """
    Human feedback + revise loop 제어 + max_revisions까지 완전 반영된 버전
    """

    coll = state.get("collateral_monthly", {})
    peg = state.get("peg_monthly", {})
    disc = state.get("disclosure_monthly", {})
    liq = state.get("liquidity_monthly", {})
    por = state.get("por_monthly", {})
    cons = state.get("consistency", {})

    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 3)
    human_feedback = (state.get("human_feedback") or "").strip()
    human_decision = state.get("human_decision", "pending")

    # 1) revise 한도 초과 → 강제 종료 모드
    if human_decision == "revise" and revision_count >= max_revisions:
        summary = {
            "final_grade": "PENDING",
            "key_points": [
                "자동 재생성(max_revisions) 한도에 도달했습니다.",
                "추가 수정은 사람이 직접 검토해야 합니다.",
            ],
            "human_feedback": human_feedback,
            "revision_status": "limit_reached",
        }

        new_state = dict(state)
        new_state["summary"] = summary
        return new_state

    # 2) 기본 등급 계산
    grade_map = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    reverse_map = {v: k for k, v in grade_map.items()}

    grades = [
        coll.get("grade", "C"),
        peg.get("grade", "C"),
        disc.get("grade", "C"),
        liq.get("grade", "C"),
        por.get("grade", "C"),
    ]

    worst_grade = reverse_map[min(grade_map.get(g, 2) for g in grades)]

    key_points = [
        f"Collateral grade: {coll.get('grade')}",
        f"Peg grade: {peg.get('grade')}",
        f"Disclosure grade: {disc.get('grade')}",
        f"Liquidity grade: {liq.get('grade')}",
        f"PoR grade: {por.get('grade')}",
        f"Consistency status: {cons.get('status', 'unknown')}",
    ]

    if human_feedback:
        key_points.append(f"[Reviewer Feedback] {human_feedback}")

    summary = {
        "final_grade": worst_grade,
        "key_points": key_points,
        "human_feedback": human_feedback,
        "revision_status": (
            "revised" if human_decision == "revise" else "initial"
        ),
    }

    new_state = dict(state)
    new_state["summary"] = summary
    return new_state


def human_review(state: MCPState) -> MCPState:
    """
    human-in-the-loop 자리.

    - interrupt 모드에서는 여기 앞에서 멈추고 Slack → FastAPI → resume 흐름
    - 자동 모드에서는 단순히 '검토 완료' 메타만 남기고 바로 notify로 이동
    """
    review_info = {
        "decision": state.get("human_decision", "pending"),
        "comment": "awaiting-human-review",
    }

    new_state = dict(state)
    new_state["human_review"] = review_info
    return new_state


def generate_report(state: MCPState) -> MCPState:
    period = state.get("period", "2025-10")
    report_rel_path = f"REP-{period}.docx"  # revise 시에도 같은 파일명으로 재생성(덮어쓰기)

    try:
        generated_path = generate_monthly_report(period, state, report_rel_path)
        logger.info("[generate_report] ✓ Report generated: %s", generated_path)

        if os.path.exists(generated_path):
            file_size = os.path.getsize(generated_path)
            logger.info("[generate_report] File size: %d bytes", file_size)
        else:
            logger.warning(
                "[generate_report] ⚠️ File not found after generation: %s",
                generated_path,
            )
    except Exception as e:
        logger.error(
            f"[generate_report] ✗ Failed to generate report: {e}",
            exc_info=True,
        )
        generated_path = report_rel_path

    new_state: MCPState = dict(state)
    new_state["report_path"] = generated_path
    return new_state


def notify_approved_report(state: MCPState) -> MCPState:
    """
    (8) Human Review 승인 후 최종 알림/메일을 보내는 노드.

    → app_mcp/services/notifications.notify_monthly_report() 호출
    """
    period = state.get("period", "2025-10")
    summary = state.get("summary", {})
    report_path = state.get("report_path", "")

    # 상태 값: 사람 승인 완료
    status = "APPROVED"

    try:
        notify_monthly_report(
            period=period,
            status=status,
            summary=summary,
            report_path=report_path,
            error=None,
        )
        logger.info(
            "[notify_approved_report] 📧 Notifications sent "
            "(period=%s, status=%s)", period, status
        )
    except Exception as e:
        logger.exception(
            "[notify_approved_report] ❌ Failed to send notifications: %s", e
        )

    new_state: MCPState = dict(state)
    new_state["human_decision"] = "approve"
    return new_state


def data_quality_fail(state: MCPState) -> MCPState:
    """
    데이터 품질 재시도 한도를 초과했을 때 호출되는 실패 노드.
    """
    dq = state.get("data_quality", {})
    logger.error(
        "[data_quality_fail] Data quality failed after max retries: %s", dq
    )

    summary = {
        "final_grade": "D",
        "error": "DATA_QUALITY_FAILURE",
        "details": "Max retries exceeded during data loading",
    }

    new_state: MCPState = dict(state)
    new_state["summary"] = summary
    new_state.setdefault("report_path", "")
    return new_state


# ─────────────────────────────────────────────
# 3) Conditional Edge 라우터들
# ─────────────────────────────────────────────

def route_after_data_quality(state: MCPState) -> str:
    dq = state.get("data_quality", {})
    if dq.get("max_retry_exceeded"):
        return "fail"
    if dq.get("has_critical_gap"):
        return "retry"
    return "ok"


def route_after_consistency(state: MCPState) -> str:
    cons = state.get("consistency", {})
    status = cons.get("status", "ok")
    if status == "recheck_collateral":
        return "recheck_collateral"
    if status == "recheck_liquidity":
        return "recheck_liquidity"
    return "ok"


def route_after_human_review(state: MCPState) -> str:
    """
    human_review 노드 이후 분기:

    - state["human_decision"] == "approve" → notify_approved_report
    - state["human_decision"] == "revise"  → summarize_conclusion (보수적 재생성)
    """
    decision = state.get("human_decision")
    rev = state.get("revision_count", 0) or 0

    if decision == "approve":
        return "approve"

    if decision == "revise":
        # 🔁 보수적 재생성 한 번 돌 때마다 revision_count 증가
        state["revision_count"] = rev + 1
        return "revise"

    # 값이 없으면 일단 approve 쪽으로 보냄
    return "approve"


# ─────────────────────────────────────────────
# 4) 그래프 빌더
# ─────────────────────────────────────────────

def build_mcp_monthly_graph_base() -> StateGraph:
    """
    기본 StateGraph 구조를 만든다. (compile 전)
    """
    workflow = StateGraph(MCPState)

    # 노드 등록
    workflow.add_node("load_period_data", load_period_data)
    workflow.add_node("data_quality_check", data_quality_check)
    workflow.add_node("eval_collateral_monthly", eval_collateral_monthly)
    workflow.add_node("eval_peg_monthly", eval_peg_monthly)
    workflow.add_node("eval_disclosure_monthly", eval_disclosure_monthly)
    workflow.add_node("eval_liquidity_monthly", eval_liquidity_monthly)
    workflow.add_node("eval_por_monthly", eval_por_monthly)
    workflow.add_node("cross_check_consistency", cross_check_consistency)
    workflow.add_node("summarize_conclusion", summarize_conclusion)
    workflow.add_node("human_review", human_review)
    workflow.add_node("generate_report", generate_report)
    workflow.add_node("notify_approved_report", notify_approved_report)
    workflow.add_node("data_quality_fail", data_quality_fail)

    # 기본 직선 플로우
    workflow.add_edge(START, "load_period_data")
    workflow.add_edge("load_period_data", "data_quality_check")
    workflow.add_edge("eval_collateral_monthly", "eval_peg_monthly")
    workflow.add_edge("eval_peg_monthly", "eval_disclosure_monthly")
    workflow.add_edge("eval_disclosure_monthly", "eval_liquidity_monthly")
    workflow.add_edge("eval_liquidity_monthly", "eval_por_monthly")
    workflow.add_edge("eval_por_monthly", "cross_check_consistency")
    workflow.add_edge("summarize_conclusion", "generate_report")
    workflow.add_edge("generate_report", "human_review")
    workflow.add_edge("notify_approved_report", END)
    workflow.add_edge("data_quality_fail", END)

    # (1-α) 데이터 품질 → 재로딩/실패/진행
    workflow.add_conditional_edges(
        "data_quality_check",
        route_after_data_quality,
        {
            "retry": "load_period_data",
            "ok": "eval_collateral_monthly",
            "fail": "data_quality_fail",
        },
    )

    # (6-α) 모순 체크 → 일부 평가 재실행 루프
    workflow.add_conditional_edges(
        "cross_check_consistency",
        route_after_consistency,
        {
            "ok": "summarize_conclusion",
            "recheck_collateral": "eval_collateral_monthly",
            "recheck_liquidity": "eval_liquidity_monthly",
        },
    )

    return workflow


def compile_mcp_monthly_graph(interrupt_for_human: bool = False):
    """
    StateGraph를 compile 해서 Runnable 그래프로 만든다.

    - interrupt_for_human=True:
      human_review 이전에서 interrupt 걸어놓고 슬랙/대시보드에서 승인/반려→resume
    """
    base = build_mcp_monthly_graph_base()

    if interrupt_for_human:
        # Human-in-the-loop 버전
        base.add_conditional_edges(
            "human_review",
            route_after_human_review,
            {
                "approve": "notify_approved_report",
                "revise": "summarize_conclusion",
            },
        )
        memory = MemorySaver()
        app = base.compile(
            checkpointer=memory,
            interrupt_before=["human_review"],
        )
    else:
        # 자동 버전: human_review 거치고 바로 notify_approved_report로 종료
        base.add_edge("human_review", "notify_approved_report")
        app = base.compile()

    return app


# ─────────────────────────────────────────────
# 5) 실행 함수 / 인스턴스
# ─────────────────────────────────────────────

def run_monthly_mcp_flow(period: str = "2025-10") -> MCPState:
    app = compile_mcp_monthly_graph(interrupt_for_human=False)

    final_state: MCPState = app.invoke(
        {
            "period": period,
            "revision_count": 0,
            "max_revisions": 3,
            "human_decision": "pending",
            "human_feedback": None,
        },
        config={"recursion_limit": 100},
    )
    return final_state


mcp_graph = compile_mcp_monthly_graph(interrupt_for_human=False)
mcp_graph_with_interrupt = compile_mcp_monthly_graph(interrupt_for_human=True)
