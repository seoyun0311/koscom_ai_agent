# claude_mcp_kwon_reports.py
# 리포트 조회 mcp툴
from typing import Any, Dict, Optional
import httpx
from fastmcp import FastMCP

MCP_NAME = "k-won-compliance-reports"
BACKEND_BASE_URL = "http://127.0.0.1:8000"   # FastAPI 서버 주소 (로컬)

app = FastMCP(MCP_NAME)


# =========================
#  공통 HTTP 헬퍼
# =========================

def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{BACKEND_BASE_URL}{path}"
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


# =========================
#  MCP Tools 정의
# =========================

@app.tool()
def get_latest_report() -> Dict[str, Any]:
    """
    K-WON 스테이블코인의 가장 최근 월간 컴플라이언스 보고서를 조회합니다.
    """
    data = _get("/mcp/report/latest")

    return {
        "period": data.get("period"),
        "final_grade": data.get("final_grade"),
        "report_path": data.get("report_path"),
        "generated_at": data.get("generated_at"),
        "summary": data.get("summary", {}),
    }


@app.tool()
def get_human_review_tasks() -> Dict[str, Any]:
    """
    Human Review가 필요한 대기 작업 목록을 조회합니다.
    """
    data = _get("/mcp/human_review/tasks")

    return {
        "count": data.get("count", 0),
        "pending_tasks": data.get("pending_tasks", []),
    }


@app.tool()
def get_collateral_status(period: Optional[str] = None) -> Dict[str, Any]:
    """
    특정 period(예: '2025-10') 또는 최신 period의 담보 상태를 조회합니다.
    period가 None이면 백엔드에서 최신 period를 사용합니다.
    """
    params = {}
    if period is not None:
        params["period"] = period

    data = _get("/mcp/collateral/status", params=params)

    return data  # 이미 JSON 구조가 Claude가 쓰기 좋은 형태라 그대로 반환


@app.tool()
def get_risk_summary(period: Optional[str] = None) -> Dict[str, Any]:
    """
    특정 period 또는 최신 period의 리스크 요약을 조회합니다.
    """
    params = {}
    if period is not None:
        params["period"] = period

    data = _get("/mcp/risk/summary", params=params)

    return data


@app.tool()
def get_report(period: str) -> Dict[str, Any]:
    """
    특정 period(예: '2025-10')의 월간 보고서 상세 내용을 조회합니다.
    report_text를 포함합니다.
    """
    data = _get(f"/mcp/report/{period}")

    return {
        "period": data.get("period"),
        "final_grade": data.get("final_grade"),
        "report_path": data.get("report_path"),
        "created_at": data.get("created_at"),
        "report_text": data.get("report_text"),
    }


@app.tool()
def get_compliance_alerts(period: Optional[str] = None) -> Dict[str, Any]:
    """
    특정 period 또는 최신 period의 컴플라이언스 경고/위반 내역을 조회합니다.
    """
    params = {}
    if period is not None:
        params["period"] = period

    data = _get("/mcp/alerts", params=params)

    return data

@app.tool()
def rerun_monthly_report(period: Optional[str] = None) -> Dict[str, Any]:
    """
    LangGraph 기반 보고서를 다시 생성합니다.
    FastAPI의 /mcp/run_full 엔드포인트를 1번 호출합니다.
    """
    payload = {}
    if period:
        payload["period"] = period

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(f"{BACKEND_BASE_URL}/mcp/run_full", json=payload)
        resp.raise_for_status()
        return resp.json()
    
if __name__ == "__main__":
    # MCP 서버 시작 (STDIN/STDOUT 기반)
    app.run()


# claude_mcp_kwon_reports.py (기존 코드에 추가)

@app.tool()
def get_review_history(period: str) -> Dict[str, Any]:
    """
    특정 기간(예: '2025-10')의 리뷰 히스토리를 조회합니다.
    
    반환 정보:
    - 누가 언제 승인/재생성/반려했는지
    - 몇 번 재생성되었는지
    - 최종 결정은 무엇인지
    - 각 revision마다의 코멘트
    """
    data = _get(f"/api/review/history/{period}")
    
    return {
        "period": data.get("period"),
        "current_status": data.get("status"),
        "total_revisions": data.get("revision_count", 0),
        "last_decision": data.get("last_decision"),
        "final_reviewer": data.get("reviewer"),
        "final_comment": data.get("final_comment"),
        "decided_at": data.get("decided_at"),
        "created_at": data.get("created_at"),
        "revision_history": data.get("revision_history", []),
        "total_tasks": data.get("total_tasks", 0),
    }


@app.tool()
def get_all_review_tasks(status: Optional[str] = None) -> Dict[str, Any]:
    """
    모든 리뷰 작업 목록을 조회합니다.
    
    Parameters:
    - status: 필터링할 상태 ("pending" | "approved" | "rejected" | "revised" | None)
             None이면 전체 조회
    
    반환 정보:
    - 각 task의 기간, 상태, 재생성 횟수, 리뷰어 등
    """
    params = {}
    if status:
        params["status"] = status
    
    data = _get("/api/review/tasks", params=params)
    
    # data는 List[HumanReviewTaskListItem] 형태
    tasks_info = []
    for task in data:
        tasks_info.append({
            "id": task.get("id"),
            "period": task.get("period"),
            "status": task.get("status"),
            "revision_count": task.get("revision_count", 0),
            "last_decision": task.get("last_decision"),
            "reviewer": task.get("reviewer"),
            "created_at": task.get("created_at"),
            "decided_at": task.get("decided_at"),
            "final_grade": task.get("final_grade"),
        })
    
    return {
        "count": len(tasks_info),
        "tasks": tasks_info,
        "filter_applied": {"status": status} if status else None,
    }


@app.tool()
def get_pending_reviews() -> Dict[str, Any]:
    """
    현재 승인 대기 중인(pending 또는 revised) 리뷰 작업들을 조회합니다.
    """
    # pending과 revised 상태 모두 조회
    pending_data = _get("/api/review/tasks", params={"status": "pending"})
    revised_data = _get("/api/review/tasks", params={"status": "revised"})
    
    all_waiting = []
    
    for task in pending_data:
        all_waiting.append({
            "id": task.get("id"),
            "period": task.get("period"),
            "status": "pending",
            "revision_count": task.get("revision_count", 0),
            "created_at": task.get("created_at"),
        })
    
    for task in revised_data:
        all_waiting.append({
            "id": task.get("id"),
            "period": task.get("period"),
            "status": "revised",
            "revision_count": task.get("revision_count", 0),
            "last_revised_at": task.get("decided_at"),
            "last_revised_by": task.get("reviewer"),
        })
    
    return {
        "waiting_review_count": len(all_waiting),
        "tasks": all_waiting,
    }