"""
MCP 서버 설정
4개 Tool 등록 및 요청 핸들러
"""

import json
from mcp.server import Server
from mcp.types import Tool, TextContent
from pydantic import AnyUrl

from app_mcp.tools import (
    get_onchain_state,
    get_offchain_reserves,
    check_coverage,
    get_risk_report
)


# MCP 서버 인스턴스
server = Server("krws-reserve-verification")


# ============================================================================
# Tool 정의
# ============================================================================

TOOLS = [
    Tool(
        name="get_onchain_state",
        description=(
            "블록체인에서 KRWS 스테이블코인의 온체인 상태를 조회합니다. "
            "총 발행량, 유통량, 최근 발행/소각 내역을 실시간으로 확인할 수 있습니다."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "refresh": {
                    "type": "boolean",
                    "description": "true일 경우 캐시를 무시하고 최신 데이터를 가져옵니다",
                    "default": False
                },
                "scenario": {
                    "type": "string",
                    "enum": ["normal", "warning", "critical"],
                    "description": "테스트 시나리오 선택 (normal: 105%, warning: 99%, critical: 97%)",
                    "default": "normal"
                }
            }
        }
    ),
    Tool(
        name="get_offchain_reserves",
        description=(
            "오프체인 금융기관들의 담보 자산 현황을 조회합니다. "
            "주수탁은행(신한·KB), 보조수탁(KDB), 운용기관(NH투자증권), "
            "보관기관(KSD)의 실시간 잔액과 자산 현황을 확인할 수 있습니다."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "refresh": {
                    "type": "boolean",
                    "description": "true일 경우 캐시를 무시하고 최신 데이터를 가져옵니다",
                    "default": False
                },
                "scenario": {
                    "type": "string",
                    "enum": ["normal", "warning", "critical"],
                    "description": "테스트 시나리오 선택",
                    "default": "normal"
                }
            }
        }
    ),
    Tool(
        name="check_coverage",
        description=(
            "온체인 발행량과 오프체인 준비금을 비교하여 담보율을 계산합니다. "
            "1:1 완전 담보 여부를 실시간으로 검증하고, 기관별 담보 비중을 분석합니다. "
            "이 Tool은 자동으로 온체인/오프체인 데이터를 조회합니다."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "scenario": {
                    "type": "string",
                    "enum": ["normal", "warning", "critical"],
                    "description": "테스트 시나리오 선택",
                    "default": "normal"
                }
            }
        }
    ),
    Tool(
        name="get_risk_report",
        description=(
            "종합적인 리스크 분석 리포트를 생성합니다. "
            "담보 상태, 리스크 요인, 규제 준수 여부, 개선 권고사항을 포함한 "
            "감사 및 컴플라이언스용 상세 보고서를 제공합니다."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "scenario": {
                    "type": "string",
                    "enum": ["normal", "warning", "critical"],
                    "description": "테스트 시나리오 선택",
                    "default": "normal"
                },
                "format": {
                    "type": "string",
                    "enum": ["summary", "detailed"],
                    "description": "summary: 요약본, detailed: 상세 리포트",
                    "default": "detailed"
                }
            }
        }
    )
]


# ============================================================================
# Tool 핸들러
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """사용 가능한 Tool 목록 반환"""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Tool 실행"""
    
    try:
        if name == "get_onchain_state":
            refresh = arguments.get("refresh", False)
            scenario = arguments.get("scenario", "normal")
            
            result = get_onchain_state(refresh=refresh, scenario=scenario)
            
            return [
                TextContent(
                    type="text",
                    text=json.dumps(result.model_dump(), indent=2, ensure_ascii=False, default=str)
                )
            ]
        
        elif name == "get_offchain_reserves":
            refresh = arguments.get("refresh", False)
            scenario = arguments.get("scenario", "normal")
            
            result = get_offchain_reserves(refresh=refresh, scenario=scenario)
            
            return [
                TextContent(
                    type="text",
                    text=json.dumps(result.model_dump(), indent=2, ensure_ascii=False, default=str)
                )
            ]
        
        elif name == "check_coverage":
            scenario = arguments.get("scenario", "normal")
            
            result = check_coverage(scenario=scenario)
            
            return [
                TextContent(
                    type="text",
                    text=json.dumps(result.model_dump(), indent=2, ensure_ascii=False, default=str)
                )
            ]
        
        elif name == "get_risk_report":
            scenario = arguments.get("scenario", "normal")
            format_type = arguments.get("format", "detailed")
            
            result = get_risk_report(scenario=scenario, format_type=format_type)
            
            # summary 모드인 경우 일부만 반환
            if format_type == "summary":
                summary_data = {
                    "report_id": result.report_id,
                    "generated_at": str(result.generated_at),
                    "summary": result.summary.model_dump(),
                    "risk_factors": [rf.model_dump() for rf in result.risk_factors],
                    "recommendations": result.recommendations
                }
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(summary_data, indent=2, ensure_ascii=False, default=str)
                    )
                ]
            
            return [
                TextContent(
                    type="text",
                    text=json.dumps(result.model_dump(), indent=2, ensure_ascii=False, default=str)
                )
            ]
        
        else:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
                )
            ]
    
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=json.dumps({"error": str(e)}, ensure_ascii=False)
            )
        ]