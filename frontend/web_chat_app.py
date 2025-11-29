"""
K-WON 컴플라이언스 통합 MCP Gateway (완전판)

통합된 MCP 서버:
1. bank_monitoring (5300): 은행 리스크 분석 + Policy Engine
2. krw-full-reserve (5400): KRWS 완전준비금 검증
3. tx_audit (5200): 온체인 감사 및 증빙
4. kwon_reports (5500): K-WON 월간 컴플라이언스 보고서
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
from anthropic import Anthropic
from dotenv import load_dotenv
import os
import json
import requests
import re
import datetime
from typing import List, Dict, Any

# ─────────────────────────────────────────────
# 환경 변수 로드
# ─────────────────────────────────────────────
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT_DIR, ".env")
load_dotenv(dotenv_path=ENV_PATH)

# ─────────────────────────────────────────────
# 서비스 URL 설정
# ─────────────────────────────────────────────
BACKEND_URL = os.getenv("BACKEND_URL", "http://175.45.205.39:4000")
BANK_MONITORING_MCP = os.getenv("BANK_MONITORING_MCP", "http://localhost:5300/mcp")
KRW_RESERVE_MCP = os.getenv("KRW_RESERVE_MCP", "http://localhost:5400/mcp")
tx_AUDIT_MCP = os.getenv("tx_AUDIT_MCP", "http://localhost:5200/mcp")
K_WON_MCP_URL = os.getenv("K_WON_MCP_URL", "http://localhost:5900/mcp")  # 🆕 K-WON Reports



# 증빙팩 ZIP 파일 위치 (프론트에서 /proof_packs로 접근)
PROOF_DIR = os.path.abspath(os.path.join(
    ROOT_DIR,
    "..",          # ← frontend 상위(프로젝트 루트)로 나가기
    "mcp_servers",
    "tx_audit",
    "data",
    "proof_packs",
))

app = Flask(
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/static'
)

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    print("⚠️ 경고: ANTHROPIC_API_KEY가 설정되지 않았습니다.")
client = Anthropic(api_key=api_key) if api_key else None

conversation_history: List[Dict[str, Any]] = []

# ─────────────────────────────────────────────
# Policy 관련 요청 판단
# ─────────────────────────────────────────────
POLICY_KEYWORDS = [
    "한도", "policy", "limit", "리미트", "익스포저",
    "비중", "집중도", "concentration",
    "분산", "위험", "정책위반", "policy breach",
    "exposure", "포트폴리오 리스크",
]

def is_policy_request(text: str) -> bool:
    """사용자 메시지가 '한도/정책/집중도' 관련인지 간단히 판별"""
    lower = text.lower()
    return any(kw.lower() in lower for kw in POLICY_KEYWORDS)

# ─────────────────────────────────────────────
# MCP HTTP Gateway 유틸 함수들
# ─────────────────────────────────────────────

def call_bank_monitoring_mcp(tool: str, params: dict) -> dict:
    """bank_monitoring MCP 서버 호출 (응답 포맷 통일 버전)"""
    try:
        print(f"🏦 bank_monitoring MCP 호출: {tool} with params: {params}")
        resp = requests.post(
            BANK_MONITORING_MCP,
            json={"tool": tool, "params": params},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        
        print(f"✅ bank_monitoring 응답: {json.dumps(data, ensure_ascii=False)[:500]}")

        success = True
        result: Any = None
        error_msg: str | None = None

        if isinstance(data, dict):
            # 게이트웨이가 {success, result, error} 형태로 줄 수도 있고
            # 그냥 tool 결과만 줄 수도 있으니 정규화
            if data.get("success") is False:
                success = False
                error_msg = data.get("error", "Unknown error from bank_monitoring MCP")
                result = data.get("result")
            else:
                if "result" in data:
                    result = data["result"]
                else:
                    result = data
        else:
            result = data

        return {
            "success": success,
            "result": result,
            "error": error_msg,
        }
        
    except requests.exceptions.Timeout:
        print("⏱ bank_monitoring MCP 타임아웃")
        return {
            "success": False,
            "result": None,
            "error": "MCP 서버 타임아웃",
        }
    except Exception as e:
        print(f"❌ bank_monitoring MCP 호출 실패: {e}")
        return {
            "success": False,
            "result": None,
            "error": f"MCP 호출 실패: {str(e)}",
        }


# 🔥 FSS 계산을 MCP에 요청하는 함수 (수정본 로직)
def compute_fss_for_all_banks(bank_list):
    """
    백엔드 은행 리스트 + 최신 FSS를 묶어서 반환
    bank_monitoring MCP의 get_latest_fss 를 호출해서
    각 은행에 fss를 붙여주는 함수.
    """
    enriched = []

    BANK_ID_MAP = {
        "신한은행": "SHINHAN",
        "국민은행": "KB",
        "KDB은행": "KDB",
        "NH투자증권": "NH",
        "KSD(한국예탁결제원)": "KSD",
        "하나은행": "HANA"
    }

    for b in bank_list:
        bank_name = b["name"]
        bank_id = BANK_ID_MAP.get(bank_name, bank_name.upper().replace(" ", "_"))

        # 🔥 최신 FSS 가져오기
        fss_resp = call_bank_monitoring_mcp(
            "get_latest_fss",
            {"bank_id": bank_id}
        )

        fss_score = None
        if isinstance(fss_resp, dict) and fss_resp.get("success"):
            body = fss_resp.get("result") or {}
            fss_score = body.get("fss_score")

        enriched.append({
            **b,
            "fss": fss_score
        })

    return enriched



def call_krw_reserve_mcp(tool: str, params: dict) -> dict:
    """krw-full-reserve MCP 서버 호출"""
    try:
        print(f"💰 krw-reserve MCP 호출: {tool}")
        
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool,
                "arguments": params
            },
            "id": 1
        }
        
        resp = requests.post(
            KRW_RESERVE_MCP,
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        print("✅ krw-reserve 응답 성공")
        
        if "result" in data and "content" in data["result"]:
            content = data["result"]["content"]
            if isinstance(content, list) and len(content) > 0:
                text = content[0].get("text", "{}")
                return json.loads(text)
        
        return data
    except Exception as e:
        print(f"❌ krw-reserve MCP 호출 실패: {e}")
        return {"success": False, "error": f"MCP 호출 실패: {str(e)}"}


def call_tx_audit_mcp(tool: str, params: dict) -> dict:
    """tx_audit HTTP MCP 게이트웨이 호출"""
    try:
        print(f"🔍 tx_audit MCP 호출: {tool} with params: {params}")

        payload = {"tool": tool, "params": params}

        resp = requests.post(
            tx_AUDIT_MCP,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        print(f"✅ tx_audit 응답: {json.dumps(data, ensure_ascii=False)[:500]}")

        if isinstance(data, dict):
            if data.get("success") is False:
                return {
                    "success": False,
                    "error": data.get("error", "tx_audit MCP error")
                }
            if "result" in data:
                return data["result"]

        return data

    except requests.exceptions.Timeout:
        print("⏱ tx_audit MCP 타임아웃")
        return {"success": False, "error": "tx_audit MCP 서버 타임아웃"}
    except Exception as e:
        print(f"❌ tx_audit MCP 호출 실패: {e}")
        return {"success": False, "error": f"tx_audit MCP 호출 실패: {str(e)}"}


def call_k_won_mcp(tool: str, params: dict) -> dict:
    """
    🆕 K-WON Reports MCP 서버 호출
    월간 컴플라이언스 보고서 관련 기능
    """
    try:
        print(f"📊 K-WON Reports MCP 호출: {tool} with params: {params}")
        resp = requests.post(
            K_WON_MCP_URL,
            json={"tool": tool, "params": params},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"✅ K-WON Reports 응답: {json.dumps(data, ensure_ascii=False)[:500]}")

        if isinstance(data, dict):
            if not data.get("success", True):
                error_msg = data.get("error", "Unknown MCP error")
                print(f"❌ MCP 에러: {error_msg}")
                return {"success": False, "error": error_msg}
            if "result" in data:
                return data["result"]

        return data

    except requests.exceptions.Timeout:
        print("⏱ K-WON Reports MCP 타임아웃")
        return {"success": False, "error": "MCP 서버 타임아웃"}
    except Exception as e:
        print(f"❌ K-WON Reports MCP 호출 실패: {e}")
        return {"success": False, "error": f"MCP 호출 실패: {str(e)}"}


def call_mcp_tool(tool: str, params: dict) -> dict:
    """
    간편한 MCP 툴 호출 (policy engine용)
    """
    resp = requests.post(
        BANK_MONITORING_MCP,
        json={"tool": tool, "params": params},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success", False):
        raise RuntimeError(f"MCP tool '{tool}' error: {data.get('error')}")
    return data["result"]


# ─────────────────────────────────────────────
# 백엔드 데이터 조회
# ─────────────────────────────────────────────

def fetch_backend_data() -> dict:
    """Node.js 백엔드에서 실제 데이터 가져오기"""
    try:
        metrics_response = requests.get(f"{BACKEND_URL}/metrics", timeout=5)
        metrics_response.raise_for_status()
        metrics = metrics_response.json()

        banks_response = requests.get(f"{BACKEND_URL}/banks", timeout=5)
        banks_response.raise_for_status()
        banks = banks_response.json()

        status_response = requests.get(f"{BACKEND_URL}/status", timeout=5)
        status_response.raise_for_status()
        status = status_response.json()

        return {
            "metrics": metrics,
            "banks": banks,
            "status": status,
        }
    except Exception as e:
        print(f"❌ 백엔드 API 호출 실패: {e}")
        return None


def get_current_exposures_from_backend() -> dict:
    """백엔드 데이터를 MCP Tool 형식으로 변환"""
    print("📡 백엔드 실시간 데이터 조회 중 (채팅용)...")
    backend_data = fetch_backend_data()
    if not backend_data:
        return None
    
    banks_data = backend_data.get("banks", {}).get("banks", [])
    
    BANK_ID_MAP = {
        "신한은행": "SHINHAN",
        "국민은행": "KB",
        "KDB은행": "KDB",
        "KSD(한국예탁결제원)": "KSD",
        "NH투자증권": "NH",
    }
    
    exposures = []
    for bank in banks_data:
        bank_name = bank.get("name", "")
        balance = bank.get("balance", 0)
        bank_id = BANK_ID_MAP.get(bank_name, bank_name.upper().replace(" ", "_"))
        
        exposures.append({
            "bank_id": bank_id,
            "name": bank_name,
            "group_id": f"{bank_id}_GROUP",
            "region": "KR",
            "exposure": balance,
            "credit_rating": "AA-",
            "maturity_bucket": "ON"
        })
    
    print(f"📊 Exposures 변환 완료: {len(exposures)}개 은행")
    for exp in exposures:
        print(f"   - {exp['name']}: {exp['exposure']:,.0f} 원")
    
    return {
        "exposures": exposures,
        "metrics": backend_data.get("metrics", {}),
    }


# ─────────────────────────────────────────────
# 동적 대시보드용 메타데이터 분석
# ─────────────────────────────────────────────

def analyze_response_for_visualization(
    user_message: str, assistant_response: str, tools_used: list
) -> dict:
    """
    채팅 응답을 분석해서 프론트에서 시각화할 힌트 메타데이터 생성
    """
    msg_lower = user_message.lower()
    response_lower = assistant_response.lower()
    
    metadata = {
        "intent": [],
        "visualization_hints": [],
        "data_extracted": {},
        "tools_used": tools_used
    }
    
    # 의도 분석
    if any(kw in msg_lower for kw in ['은행', '익스포저', 'exposure', 'balance', '분산', '예치']):
        metadata["intent"].append("bank_exposure")
        metadata["visualization_hints"].append({
            "type": "bar_chart",
            "title": "은행별 익스포저 분포",
            "description": "각 은행의 예치금 분포를 시각화합니다"
        })
    
    if any(kw in msg_lower for kw in ['정책', 'policy', '한도', 'limit', '위반', 'breach']):
        metadata["intent"].append("policy_check")
        metadata["visualization_hints"].append({
            "type": "status_card",
            "title": "정책 준수 현황",
            "description": "한도 위반 여부와 이슈 개수를 표시합니다"
        })
    
    if any(kw in msg_lower for kw in ['담보', 'coverage', '준비금', 'reserve', '비율', '담보율']):
        metadata["intent"].append("coverage")
        metadata["visualization_hints"].append({
            "type": "gauge",
            "title": "담보 커버리지",
            "description": "현재 담보율을 시각화합니다"
        })
    
    if any(kw in msg_lower for kw in ['리스크', 'risk', '스트레스', 'stress', '위험']):
        metadata["intent"].append("risk_analysis")
        metadata["visualization_hints"].append({
            "type": "risk_card",
            "title": "리스크 평가",
            "description": "종합 리스크 레벨을 표시합니다"
        })
    
    if any(kw in msg_lower for kw in ['보고서', 'report', '월간', 'monthly', '컴플라이언스']):
        metadata["intent"].append("compliance_report")
        metadata["visualization_hints"].append({
            "type": "report_card",
            "title": "컴플라이언스 보고서",
            "description": "월간 보고서 등급과 요약을 표시합니다"
        })
    
    # 숫자 데이터 추출
    bank_pattern = r'([가-힣A-Za-z]+은행|[가-힣A-Za-z]+증권|KSD|KDB)[\s:：]+([0-9,]+)'
    banks = re.findall(bank_pattern, assistant_response)
    if banks:
        metadata["data_extracted"]["banks"] = [
            {"name": name, "value": int(value.replace(',', ''))}
            for name, value in banks
        ]
    
    # 비율 추출
    ratio_pattern = r'(\d+\.?\d*)%'
    ratios = re.findall(ratio_pattern, assistant_response)
    if ratios:
        metadata["data_extracted"]["ratios"] = [float(r) for r in ratios]
    
    return metadata


# ─────────────────────────────────────────────
# Claude Tool 정의 (전체 통합)
# ─────────────────────────────────────────────

CLAUDE_TOOLS = [
    # ════════════════════════════════════════════
    # 📊 K-WON Reports Tools (NEW!)
    # ════════════════════════════════════════════
    {
        "name": "get_latest_report",
        "description": "K-WON의 가장 최근 월간 컴플라이언스 보고서를 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_human_review_tasks",
        "description": "Human Review가 필요한 대기 작업 목록을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_collateral_status",
        "description": "특정 기간 또는 최신 기간의 담보 상태를 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "보고 기간 (예: '2025-10'), 생략 시 최신",
                }
            },
        },
    },
    {
        "name": "get_risk_summary",
        "description": "특정 기간 또는 최신 기간의 리스크 요약을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "보고 기간 (예: '2025-10'), 생략 시 최신",
                }
            },
        },
    },
    {
        "name": "get_report",
        "description": "이미 생성된 월간 보고서의 상세 내용을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "보고 기간 (예: '2025-10')",
                }
            },
            "required": ["period"],
        },
    },
    {
        "name": "get_compliance_alerts",
        "description": "특정 기간 또는 최신 기간의 컴플라이언스 경고/위반 내역을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "보고 기간 (예: '2025-10'), 생략 시 최신",
                }
            },
        },
    },
    {
        "name": "rerun_monthly_report",
        "description": "지정한 월(또는 기본값)에 대해 K-WON 월간 컴플라이언스 보고서를 다시 생성합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "보고 기간 (예: '2025-10'), 생략 시 백엔드 기본값 사용",
                }
            },
        },
    },
    
    # ════════════════════════════════════════════
    # 🔍 KOSCOM Audit Tools
    # ════════════════════════════════════════════
    {
        "name": "events_recent",
        "description": (
            "최근 USDT(또는 로컬 토큰) 전송 이벤트를 N건 조회합니다. "
            "사용자가 '최근 거래', '최신 트랜잭션' 등을 물어보면 사용하세요."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "가져올 이벤트 개수", "default": 10},
                "tz": {"type": "string", "description": "시간대", "default": "UTC"},
                "include_raw": {"type": "boolean", "default": False}
            }
        }
    },
    {
        "name": "sync_state",
        "description": "온체인 감사 데이터의 동기화 상태를 조회합니다.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "event_detail",
        "description": "특정 이벤트(TX 해시 기준)에 대한 상세 정보를 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tx_hash": {"type": "string", "description": "이벤트 ID (TX 해시)"},
                "tz": {"type": "string", "default": "UTC"},
                "include_raw": {"type": "boolean", "default": True}
            },
            "required": ["tx_hash"]
        }
    },
    {
        "name": "event_proof",
        "description": "특정 이벤트(TX 해시)에 대한 머클 증명과 배치 메타데이터를 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tx_hash": {"type": "string"},
                "tz": {"type": "string", "default": "UTC"}
            },
            "required": ["tx_hash"]
        }
    },
    {
        "name": "proof_pack",
        "description": "단일 이벤트에 대한 자기완결적 증명 패키지를 생성합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tx_hash": {"type": "string"},
                "include_raw": {"type": "boolean", "default": True},
                "tz": {"type": "string", "default": "UTC"},
                "as_zip": {"type": "boolean", "default": True}
            },
            "required": ["tx_hash"]
        }
    },
    {
        "name": "proof_pack_batch",
        "description": (
            "여러 거래(기간/주소/금액/블록/해시 필터)를 한꺼번에 증빙팩 ZIP으로 만듭니다. "
            "이벤트 목록과 선택적 proof/anchor 정보를 포함해 파일 경로/해시를 반환합니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "from/to 주소 필터"},
                "role": {"type": "string", "enum": ["any", "from", "to"], "default": "any"},
                "tx_hash": {"type": "string", "description": "TX 해시(접두어 가능)"},
                "tx_prefix_ok": {"type": "boolean", "default": True},
                "min_amount": {"type": "number"},
                "max_amount": {"type": "number"},
                "block_min": {"type": "integer"},
                "block_max": {"type": "integer"},
                "start_iso": {"type": "string", "description": "ISO8601 시작 시각"},
                "end_iso": {"type": "string", "description": "ISO8601 종료 시각"},
                "limit": {"type": "integer", "default": 200},
                "tz": {"type": "string", "default": "UTC"},
                "include_raw": {"type": "boolean", "default": False},
                "include_proof": {"type": "boolean", "default": True},
                "include_anchor": {"type": "boolean", "default": True},
                "as_zip": {"type": "boolean", "default": True}
            }
        }
    },
    {
        "name": "batches_recent",
        "description": "최근 생성된 머클 배치 목록을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 10}}
        }
    },
    {
        "name": "batch_events",
        "description": "특정 배치에 포함된 이벤트들을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
                "tz": {"type": "string", "default": "UTC"}
            },
            "required": ["batch_id"]
        }
    },
    {
        "name": "events_search",
        "description": "주소, TX 해시, 금액 범위, 블록 범위 등으로 이벤트를 검색합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string"},
                "role": {"type": "string", "enum": ["any", "from", "to"], "default": "any"},
                "tx_hash": {"type": "string"},
                "min_amount": {"type": "number"},
                "max_amount": {"type": "number"},
                "block_min": {"type": "integer"},
                "block_max": {"type": "integer"},
                "limit": {"type": "integer", "default": 50},
                "tz": {"type": "string", "default": "UTC"}
            }
        }
    },
    {
        "name": "make_batch",
        "description": "아직 배치에 포함되지 않은 이벤트들로 머클 배치를 생성합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 1000},
                "mode": {"type": "string", "enum": ["oldest", "latest"], "default": "oldest"}
            }
        }
    },
    {
        "name": "anchor_batch",
        "description": "특정 머클 배치를 체인에 앵커링합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "string"},
                "chain": {"type": "string", "default": "mock"}
            },
            "required": ["batch_id"]
        }
    },
    
    # ════════════════════════════════════════════
    # 🏦 Bank Monitoring Tools - Policy Engine
    # ════════════════════════════════════════════
    {
        "name": "check_policy_compliance",
        "description": (
            "🎯 Policy Engine! 은행별 익스포저/신용등급/만기 구조를 기반으로 "
            "정책 한도 위반 여부를 자동으로 계산합니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "exposures": {"type": "object", "description": "exposures 객체"}
            },
            "required": ["exposures"]
        }
    },
    {
        "name": "get_rebalancing_suggestions",
        "description": "Policy 위반 리스트를 기반으로 구체적인 재예치/만기조정 제안을 생성합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "violations": {"type": "array", "description": "위반 항목 리스트"}
            },
            "required": ["violations"]
        }
    },
    
    # Bank Monitoring - DART 공시 분석
    {
        "name": "bank_financials_by_name",
        "description": (
            "🎯 은행 이름만으로 재무제표를 자동으로 조회합니다. "
            "자산총계, 부채총계, 자본총계, 부채비율, 유동비율 등을 한 번에 제공합니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "bank_name": {"type": "string"},
                "bsns_year": {"type": "string"},
                "reprt_code": {"type": "string", "default": "11011"}
            },
            "required": ["bank_name"]
        },
    },
    {
        "name": "calc_bank_ratios",
        "description": "corp_code 기반으로 은행 신용지표를 계산합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "corp_code": {"type": "string"},
                "bsns_year": {"type": "string"},
                "reprt_code": {"type": "string", "default": "11011"}
            },
            "required": ["corp_code", "bsns_year"]
        },
    },
    {
        "name": "resolve_corp_code",
        "description": "은행/기업 이름으로 DART corp_code를 찾습니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string"},
                "limit": {"type": "integer", "default": 5}
            },
            "required": ["keyword"]
        },
    },
    
    # Bank Monitoring - 리스크 분석
    {
        "name": "get_bank_risk_score",
        "description": "단일 은행의 리스크 점수를 계산합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "exposure": {
                    "type": "object",
                    "properties": {
                        "bank_id": {"type": "string"},
                        "name": {"type": "string"},
                        "group_id": {"type": "string"},
                        "exposure": {"type": "number"},
                        "credit_rating": {"type": "string", "default": "NR"}
                    },
                    "required": ["bank_id", "name", "group_id", "exposure"]
                }
            },
            "required": ["exposure"]
        },
    },
    {
        "name": "run_bank_stress_test",
        "description": "여러 은행에 대한 스트레스 테스트를 수행합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "exposures": {"type": "array"},
                "scenario": {"type": "object"}
            },
            "required": ["exposures"]
        },
    },
    {
        "name": "suggest_bank_rebalance",
        "description": "현재 익스포저 분포를 분석하여 재예치 제안을 합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "exposures": {"type": "array"}
            },
            "required": ["exposures"]
        },
    },
    
    # ════════════════════════════════════════════
    # 💰 KRW Full Reserve Tools
    # ════════════════════════════════════════════
    {
        "name": "get_onchain_state",
        "description": "원화 스테이블코인 운영 센터에서 K-WON 온체인 상태를 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "refresh": {"type": "boolean", "default": True},
                "scenario": {"type": "string", "enum": ["normal", "warning", "critical"], "default": "normal"}
            }
        }
    },
    {
        "name": "get_offchain_reserves",
        "description": "오프체인 준비금 현황을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "refresh": {"type": "boolean", "default": True},
                "scenario": {"type": "string", "enum": ["normal", "warning", "critical"], "default": "normal"}
            }
        }
    },
    {
        "name": "check_coverage",
        "description": "담보율을 계산합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "enum": ["normal", "warning", "critical"], "default": "normal"}
            }
        }
    },
    {
        "name": "get_risk_report",
        "description": "종합 리스크 리포트를 생성합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "enum": ["normal", "warning", "critical"], "default": "normal"},
                "format": {"type": "string", "enum": ["summary", "detailed"], "default": "detailed"}
            }
        }
    },
        {
        "name": "get_full_reserve_history",
        "description": "K-WON 온체인 가격, 오프체인 발행량, 담보율의 히스토리 타임시리즈를 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "description": "\"all\", \"coverage\", \"onchain\", \"offchain\" 중 하나",
                    "enum": ["all", "coverage", "onchain", "offchain"],
                    "default": "all"
                },
                "from_ts": {
                    "type": "string",
                    "description": "조회 시작 시각 (ISO8601, 예: \"2025-11-26T00:00:00+09:00\")"
                },
                "to_ts": {
                    "type": "string",
                    "description": "조회 종료 시각 (ISO8601, 예: \"2025-11-27T00:00:00+09:00\")"
                },
                "limit": {
                    "type": "integer",
                    "description": "최대 데이터 포인트 수",
                    "default": 1000
                }
            }
        }
    },
]


def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """Tool 실행 - 적절한 MCP 서버로 라우팅"""
    print(f"\n🔧 Tool 실행: {tool_name}")
    
    # K-WON Reports Tools
    if tool_name in {
        "get_latest_report",
        "get_human_review_tasks",
        "get_collateral_status",
        "get_risk_summary",
        "get_report",
        "get_compliance_alerts",
        "rerun_monthly_report",
    }:
        return call_k_won_mcp(tool_name, tool_input)
    
    # bank_monitoring Tools
    elif tool_name in {
        "get_bank_risk_score",
        "run_bank_stress_test",
        "suggest_bank_rebalance",
        "bank_financials_by_name",
        "calc_bank_ratios",
        "resolve_corp_code",
        "check_policy_compliance",
        "get_rebalancing_suggestions",
    }:
        return call_bank_monitoring_mcp(tool_name, tool_input)
    
    # tx_audit Tools
    elif tool_name in {
        "events_recent",
        "sync_state",
        "event_detail",
        "event_proof",
        "proof_pack",
        "proof_pack_batch",
        "batches_recent",
        "batch_events",
        "events_search",
        "make_batch",
        "anchor_batch",
    }:
        return call_tx_audit_mcp(tool_name, tool_input)

    # krw-full-reserve Tools
    elif tool_name in {
        "get_onchain_state",
        "get_offchain_reserves",
        "check_coverage",
        "get_risk_report",
        "get_full_reserve_history", 
    }:
        return call_krw_reserve_mcp(tool_name, tool_input)
    
    return {"error": f"알 수 없는 tool: {tool_name}"}

@app.route("/api/full-reserves")
def api_full_reserves():
    backend_data = fetch_backend_data()
    if backend_data is None:
        return jsonify([])

    banks = backend_data["banks"]["banks"]

    # STEP 1: 역할 매핑 (bank_monitoring 엔진과 일치시킴)
    ROLE_MAP = {
        "신한은행": "commercial_bank",
        "국민은행": "commercial_bank",
        "하나은행": "secondary_custodian",   # ✅ 하나은행 추가 (dual custodian 역할)
        "KDB은행": "policy_bank",            # 정책은행 맞음
        "NH투자증권": "broker",
        "KSD(한국예탁결제원)": "custody_agent",  # 예탁결제원은 custody agent
    }


    # STEP 2: FSS DB 최신값 가져오기 (수정본 로직)
    enriched = compute_fss_for_all_banks(banks)

    # STEP 3: 응답 구성
    response = []
    for b in enriched:
        role = ROLE_MAP.get(b["name"], "other")

        response.append({
            "bank_id": b["name"].upper().replace(" ", "_"),
            "name": b["name"],
            "role": role,
            "exposure": b["balance"],
            "fss": b["fss"],   # ← 실시간 FSS 표시
        })

    return jsonify(response)




@app.route("/api/mcp", methods=["POST"])
def api_mcp_generic():
    """
    index.html JS에서 호출: { tool, arguments }
    자동으로 bank_monitoring MCP로 라우팅.
    역할 기반 배분(role_based_allocation, role_based_rebalance)도 여기서 처리됨.
    """
    body = request.json
    tool = body.get("function") or body.get("tool")
    params = body.get("arguments") or body.get("params") or {}

    print(f"🛠 Generic MCP 호출: {tool}")

    # --------------------------------------------
    # 🔥 role_based_allocation: FSS 최신값 DB에서 주입 (수정본 로직)
    # --------------------------------------------
    if tool == "role_based_allocation":
        institutions = params.get("institutions", [])

        for inst in institutions:
            bank_id = inst.get("bank_id")
            if not bank_id:
                continue

            print(f"📡 최신 FSS 조회: {bank_id}")
            fss_resp = call_bank_monitoring_mcp("get_latest_fss", {"bank_id": bank_id})

            if isinstance(fss_resp, dict) and fss_resp.get("success"):
                result = fss_resp.get("result") or {}
                latest_fss = result.get("fss_score")
                inst["fss"] = latest_fss
                print(f"   → FSS 주입: {latest_fss}")

        params["institutions"] = institutions

    # --------------------------------------------
    # 🔥 role_based_rebalance도 동일하게 적용 (수정본 로직)
    # --------------------------------------------
    if tool == "role_based_rebalance":
        institutions = params.get("institutions", [])
        for inst in institutions:
            bank_id = inst.get("bank_id")

            fss_resp = call_bank_monitoring_mcp("get_latest_fss", {"bank_id": bank_id})
            if fss_resp.get("success"):
                inst["fss"] = fss_resp["result"].get("fss_score")

        params["institutions"] = institutions

    # --------------------------------------------
    # 정상 MCP 호출
    # --------------------------------------------
    raw = call_bank_monitoring_mcp(tool, params)

    # normalize
    if isinstance(raw, dict) and "result" in raw:
        return jsonify({"success": True, "result": raw["result"]})

    return jsonify(raw)



# ─────────────────────────────────────────────
# Flask 라우트
# ─────────────────────────────────────────────

@app.route("/")
def index():
    """메인 페이지"""
    return render_template("index.html")


@app.route("/api/health")
def health_check():
    """헬스 체크"""
    try:
        resp = requests.get(f"{BACKEND_URL}/status", timeout=3)
        resp.raise_for_status()
        return jsonify({"status": "healthy", "backend": "connected"})
    except:
        return jsonify({"status": "unhealthy", "backend": "disconnected"}), 503


@app.route("/api/full-verification")
def full_verification():
    """대시보드용 전체 검증 API"""
    try:
        backend_data = fetch_backend_data()
        if backend_data is None:
            return jsonify({"success": False, "error": "백엔드 연결 실패"}), 503

        metrics = backend_data["metrics"]
        banks = backend_data["banks"]["banks"]

        custodians = []
        total_reserves = 0
        for bank in banks:
            custodians.append({"name": bank["name"], "amount": bank["balance"]})
            total_reserves += bank["balance"]

        total_supply = metrics["supplyKRW"]
        coverage_ratio = metrics["coverageRatio"] * 100

        if coverage_ratio >= 105:
            status_text = "HEALTHY"
            risk_level = "LOW"
        elif coverage_ratio >= 100:
            status_text = "WARNING"
            risk_level = "MODERATE"
        else:
            status_text = "DEFICIT"
            risk_level = "HIGH"

        max_concentration = 0
        if total_reserves > 0:
            max_concentration = max(
                bank["balance"] / total_reserves * 100 for bank in banks
            )

        current_time = datetime.datetime.now().isoformat()

        response_data = {
            "success": True,
            "data": {
                "onchain": {
                    "total_supply": int(total_supply),
                    "net_circulation": int(total_supply),
                    "burned": 0,
                    "timestamp": current_time,
                },
                "offchain": {
                    "total_reserves": int(total_reserves),
                    "custodians": custodians,
                    "timestamp": current_time,
                },
                "coverage": {
                    "coverage_ratio": round(coverage_ratio, 2),
                    "excess_collateral": int(total_reserves - total_supply),
                    "status": status_text,
                    "timestamp": current_time,
                },
                "risk": {
                    "overall_status": status_text,
                    "concentration_risk": risk_level,
                    "max_custodian_concentration": round(max_concentration, 2),
                    "timestamp": current_time,
                },
            },
        }

        return jsonify(response_data)
    except Exception as e:
        import traceback
        print(f"❌ /api/full-verification 에러: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
def chat():
    """웹 채팅 → Claude → MCP Tools → 최종 답변"""
    global conversation_history  # 🔥 history 재할당 위해 추가

    try:
        if client is None:
            return jsonify({"error": "API Key 미설정"}), 500

        user_message = request.json.get("message", "").strip()
        print(f"\n{'='*70}")
        print(f"📨 사용자 메시지: {user_message}")
        print(f"{'='*70}")

        if not user_message:
            return jsonify({"error": "메시지가 비어있습니다"}), 400

        # 1) 백엔드 데이터
        exposure_data = get_current_exposures_from_backend()
        if not exposure_data:
            return jsonify({"error": "백엔드 데이터를 가져올 수 없습니다"}), 503

        exposures = exposure_data["exposures"]
        metrics = exposure_data["metrics"]

        # 2) Policy Engine 사전 실행 (필요시)
        policy_result = None
        policy_suggestions = None

        if is_policy_request(user_message):
            print("🔎 Policy 관련 요청 감지 → check_policy_compliance 사전 실행")

            policy_input = {"exposures": {"exposures": exposures}}
            policy_result = call_mcp_tool("check_policy_compliance", policy_input)

            violations = policy_result.get("violations") or []
            if violations:
                print(f"⚠️ Policy 위반 {len(violations)}건 감지 → 재밸런싱 제안 호출")
                policy_suggestions = call_mcp_tool(
                    "get_rebalancing_suggestions",
                    {"violations": violations},
                )

        # Policy 결과를 system_prompt에 주입
        if policy_result:
            policy_block = (
                "\n\n# 🔎 Policy Engine 사전 분석 결과\n"
                + json.dumps(policy_result, ensure_ascii=False, indent=2)
            )
            if policy_suggestions:
                policy_block += (
                    "\n\n# 🔁 Policy 기반 재밸런싱 제안\n"
                    + json.dumps(policy_suggestions, ensure_ascii=False, indent=2)
                )
        else:
            policy_block = ""

        # 3) 시스템 프롬프트
        system_prompt = f"""당신은 K-WON 원화 스테이블코인 컴플라이언스/리스크 분석 AI 에이전트입니다.

# 📊 현재 실시간 데이터
{json.dumps(exposures, ensure_ascii=False, indent=2)}

# 📈 현재 집계 메트릭
{json.dumps(metrics, ensure_ascii=False, indent=2)}

{policy_block}

# 📋 K-WON 월간 컴플라이언스 보고서 (NEW!)

- **get_latest_report**: 가장 최근 월간 보고서 요약/등급 조회
- **get_human_review_tasks**: Human Review 대기 작업 목록
- **get_collateral_status(period?)**: 담보율, 준비금, 자산 구성 조회
- **get_risk_summary(period?)**: 담보/페깅/유동성/공시/PoR 리스크 요약
- **get_report(period)**: 특정 월 보고서 상세 내용
- **get_compliance_alerts(period?)**: 경고/위반 내역
- **rerun_monthly_report(period?)**: 월간 보고서 재생성

# 🎯 Policy Engine

- **check_policy_compliance**: 익스포저 한도 위반 자동 체크
- **get_rebalancing_suggestions**: 재예치 제안 생성

# 🧾 온체인 감사 / 증빙(tx_audit)

- 사용자가 "이 거래 증명해줘", "증빙", "머클 증명", "증빙팩", "proof pack" 등을 요청하면:
  1) 해당 거래의 tx_hash를 파악합니다 (이미 최근 거래를 보여줬다면 그 중 하나를 선택 가능)
  2) 우선 event_proof 툴로 머클 증명과 배치 메타데이터를 조회합니다.
  3) 단일 거래 증빙팩이 필요하면 proof_pack 툴을 호출해 ZIP 경로(path), sha256, 파일 크기(bytes)를 제공합니다.
  4) 여러 거래를 묶어달라고 하면 proof_pack_batch 툴을 한 번만 호출해 결과의 path/sha256/bytes/count를 그대로 전달하세요.
# 🏦 DART 재무 데이터

- **bank_financials_by_name**: 재무제표 조회 (최우선!)
- calc_bank_ratios, resolve_corp_code

# 📊 리스크 분석

- get_bank_risk_score, run_bank_stress_test, suggest_bank_rebalance

# 💰 KRWS 검증

- get_onchain_state, get_offchain_reserves, check_coverage, get_risk_report

# 📈 KRWS 히스토리 분석 가이드

- get_full_reserve_history를 호출한 뒤, **그대로 숫자만 나열하지 말고** 다음을 분석해서 요약한다:
  1) 기간 내 최소/최대/평균 값
  2) 최근 값이 과거 평균 대비 얼마나 높은지/낮은지 (%, 배수 등)
  3) 급격한 변화가 있었던 시점 (예: 하루에 3%p 이상 담보율 변동, 가격 급락/급등)
  4) 담보율 100% 이하 구간, 105% 이상 과잉담보 구간이 있었다면 그 시점과 원인 추정
- 온체인 가격 vs 이론가 차이(디스카운트/프리미엄)도 함께 설명한다.
- 사용자가 "차트로 보고 싶다"라고 하면, 어떤 값을 x축/y축에 쓰면 좋을지
  (예: x=날짜, y=담보율 또는 온체인 가격) 자연어로 설명해준다.

사용자 질문에 따라 적절한 Tool을 사용하여 실제 수치/등급/상태를 기반으로 답변하세요.
설명은 한국어로, 비전공자도 이해할 수 있을 정도로 쉽게 작성하세요.

"""

        # 4) 히스토리 + 유저 메시지
        messages = conversation_history.copy()
        messages.append({"role": "user", "content": user_message})

        print(f"\n📋 등록된 Tool: {len(CLAUDE_TOOLS)}개")

        final_answer = ""
        tools_used = []
        max_tool_rounds = 5

        # 5) Multi-step Tool 실행 루프
        for round_idx in range(max_tool_rounds):
            print(f"\n🤖 Claude 호출 (round {round_idx+1})...")

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                system=system_prompt,
                messages=messages,
                tools=CLAUDE_TOOLS,
                tool_choice={"type": "auto"},
                max_tokens=2000,
            )

            print(f"🎯 Stop reason: {response.stop_reason}")
            assistant_content = response.content
            print(f"📦 Content blocks: {len(assistant_content)}")

            tool_use_blocks = [
                b for b in assistant_content if getattr(b, "type", None) == "tool_use"
            ]
            print(f"🔧 Tool use blocks: {len(tool_use_blocks)}개")

            messages.append({"role": "assistant", "content": assistant_content})

            if not tool_use_blocks:
                final_answer = "".join(
                    getattr(b, "text", "")
                    for b in assistant_content
                    if getattr(b, "type", None) == "text"
                )
                break

            print(f"🛠 MCP Tool 실행 (round {round_idx+1})")
            tool_results_message = {"role": "user", "content": []}

            for tb in tool_use_blocks:
                print(f"   - {tb.name} with input: {tb.input}")
                tools_used.append(tb.name)

                # 🔥 Tool 실행 예외 방어
                try:
                    result = execute_tool(tb.name, tb.input)
                except Exception as e:
                    print(f"   ❌ Tool 실행 에러: {e}")
                    result = {"success": False, "error": str(e)}

                tool_results_message["content"].append({
                    "type": "tool_result",
                    "tool_use_id": tb.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

            messages.append(tool_results_message)

        if not final_answer:
            final_answer = "죄송합니다. 요청하신 정보를 찾는 데 문제가 발생했습니다."

        print(f"✔ 최종 답변: {len(final_answer)} 글자")
        print(f"{'='*70}\n")

        # 🔥 대화 히스토리 저장 + 길이 제한
        conversation_history.extend([
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": final_answer},
        ])
        conversation_history = conversation_history[-20:]  # 최근 20개만 유지

        # 6) 메타데이터 생성
        metadata = analyze_response_for_visualization(user_message, final_answer, tools_used)

        return jsonify({
            "response": final_answer,
            "metadata": metadata
        })

    except Exception as e:
        import traceback
        print(f"\n❌ /api/chat 에러: {e}")
        traceback.print_exc()
        return jsonify({"error": "AI 처리 중 오류"}), 500



@app.route("/api/reset", methods=["POST"])
def reset_conversation():
    """대화 히스토리 초기화"""
    global conversation_history
    conversation_history = []
    print("🔄 대화 초기화")
    return jsonify({"status": "success"})

# ─────────────────────────────────────────────
# 증빙팩 파일 관련 엔드포인트
# 프론트의 openProofPackModal() 이 여기 사용
# ─────────────────────────────────────────────

@app.route("/proof_packs")
def list_proof_packs():
    """
    증빙팩 ZIP 파일 목록 조회
    응답 형식: {"files": ["file1.zip", "file2.zip", ...]}
    """
    try:
        if not os.path.isdir(PROOF_DIR):
            return jsonify({"files": []})
        files = [
            f for f in os.listdir(PROOF_DIR)
            if f.lower().endswith(".zip")
        ]
        return jsonify({"files": files})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/proof_packs/<path:filename>")
def download_proof_pack(filename):
    """
    개별 증빙팩 ZIP 다운로드
    """
    try:
        return send_from_directory(PROOF_DIR, filename, as_attachment=True)
    except Exception:
        return jsonify({"error": "파일을 찾을 수 없습니다."}), 404

# ─────────────────────────────────────────────
# 서버 실행
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("🚀 K-WON 컴플라이언스 통합 MCP Gateway (완전판)")
    print("=" * 70)
    print("📊 대시보드: http://localhost:5100")
    print("💬 채팅 API: POST http://localhost:5100/api/chat")
    print("=" * 70)
    print(f"🔗 백엔드: {BACKEND_URL}")
    print(f"🏦 bank_monitoring: {BANK_MONITORING_MCP}")
    print(f"💰 krw-reserve: {KRW_RESERVE_MCP}")
    print(f"🔍 tx_audit: {tx_AUDIT_MCP}")
    print(f"📊 kwon_reports: {K_WON_MCP_URL}")
    print("=" * 70)
    print("\n✨ 통합 기능:")
    print("   • Policy Engine: 익스포저 한도 자동 체크 & 재밸런싱 제안")
    print("   • K-WON Reports: 월간 컴플라이언스 보고서 & Human Review")
    print("   • KOSCOM Audit: 온체인 거래 증명 & 머클 배치")
    print("   • DART 재무제표: 은행 재무 상태 분석")
    print("   • KRWS 검증: 담보율 실시간 모니터링")
    print("=" * 70)
    print("📂 PROOF_DIR =", PROOF_DIR)

    app.run(debug=True, port=5100, host="0.0.0.0")