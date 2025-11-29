# app_mcp/services/human_review_service.py

from typing import Optional, Dict, Any, Literal
import logging

from app_mcp.graph.mcp_flow import mcp_graph_with_interrupt

logger = logging.getLogger(__name__)

DecisionType = Literal["approve", "revise"]


async def resume_human_review_flow(
    *,
    thread_id: str,
    decision: DecisionType,
    comment: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Human Review 이후 LangGraph를 같은 thread_id로 재개.
    
    ✅ 올바른 LangGraph Checkpointer API 사용
    """
    
    config = {"configurable": {"thread_id": thread_id}}
    
    # ✅ 1. 올바른 API: aget_tuple 사용
    checkpoint_tuple = await mcp_graph_with_interrupt.checkpointer.aget_tuple(config)
    
    if not checkpoint_tuple:
        raise RuntimeError(f"No checkpoint found for thread_id={thread_id}")
    
    # ✅ 2. State 추출 (올바른 구조)
    state = dict(checkpoint_tuple.checkpoint["channel_values"])
    
    # 기본값 방어
    revision_count = int(state.get("revision_count", 0) or 0)
    max_revisions = int(state.get("max_revisions", 3) or 3)
    
    # ✅ 3. State 업데이트 준비
    updates = {"human_decision": decision}
    
    if comment:
        updates["human_feedback"] = comment
    
    # revise일 때만 revision_count 증가
    if decision == "revise":
        revision_count += 1
        updates["revision_count"] = revision_count
    
    # 한도 초과 체크
    if revision_count >= max_revisions:
        prev_fb = state.get("human_feedback") or ""
        notice = "\n[자동 재생성 한도 도달: 수동 검토 필요]"
        updates["human_feedback"] = (prev_fb + notice).strip()
        updates["revision_limit_reached"] = True
    else:
        updates["revision_limit_reached"] = False
    
    logger.info(
        "[resume_human_review_flow] thread_id=%s, decision=%s, revision=%d/%d",
        thread_id,
        decision,
        revision_count,
        max_revisions,
    )
    
    # ✅ 4. aupdate_state로 state 업데이트
    await mcp_graph_with_interrupt.aupdate_state(config=config, values=updates)
    
    # ✅ 5. None 전달로 그래프 재개
    final_state = await mcp_graph_with_interrupt.ainvoke(None, config=config)
    
    # dict 형태로 반환
    if isinstance(final_state, dict):
        return final_state
    return {"state": str(final_state)}