from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict
import uuid, json, os

from app_mcp.core.db import get_db
from app_mcp.core.config import get_settings
from app_mcp.models import (
    ReservesPayload, BanksPayload, AuditPayload,
    ComplianceFinding, ComplianceReportOut,
    ReportLog, Artifact, RawSource
)
from app_mcp.utils.http import slack_notify
from app_mcp.tools.reserves import fetch_reserves
from app_mcp.tools.banks import fetch_banks
from app_mcp.tools.disclosures import fetch_audit

# reports pipeline
from app_mcp.reports.evaluator import evaluate_rules
from app_mcp.reports.generator import build_narrative
from app_mcp.reports.renderer import render_artifacts

router = APIRouter(prefix="/reports", tags=["reports"])

async def gather_inputs(period: str) -> Dict[str, object]:
    reserves: ReservesPayload = await fetch_reserves(period)
    banks: BanksPayload = await fetch_banks(period)
    audit: AuditPayload = await fetch_audit(period)
    return {"reserves": reserves, "banks": banks, "audit": audit}

@router.post("/generate", response_model=ComplianceReportOut)
async def generate_report(period: str, db: AsyncSession = Depends(get_db)):
    s = get_settings()
    try:
        inputs = await gather_inputs(period)

        # 1) 소스 저장 (재현성)
        rid = f"REP-{period}-{uuid.uuid4().hex[:8]}"
        for k, v in inputs.items():
            raw = RawSource(report_id=rid, source=k, payload=json.loads(v.model_dump_json()))
            db.add(raw)

        # 2) 룰 평가
        findings: list[ComplianceFinding] = evaluate_rules(
            inputs["reserves"], inputs["banks"], inputs["audit"]
        )

        # 3) 결론
        conclusion = "compliant"
        if any(f.status == "non-compliant" for f in findings):
            conclusion = "non-compliant"
        elif any(f.status == "conditional" for f in findings):
            conclusion = "conditional"

        # 4) 내러티브(LLM 없이도 동작하는 템플릿 요약)
        narrative = build_narrative(period, conclusion, findings)

        # 5) 산출물 생성 (HTML/PDF/JSON 저장)
        arts = await render_artifacts(rid, period, narrative, findings, inputs, s.artifact_dir)
        # 퍼블릭 URL 구성 (정적 마운트 기준)
        html_url = f"{s.public_base_url}/artifacts/{rid}.html"
        json_url = f"{s.public_base_url}/artifacts/{rid}.json"

        # (기존) await slack_notify(f"[MCP] 준수 보고서 생성 완료: {rid} (결론: {conclusion})")
        #  (신규) 상태별 카드 + 링크
        from app_mcp.utils.http import slack_notify_report
        await slack_notify_report(conclusion, rid, period, html_url, json_url)
        # 6) DB 로그
        log = ReportLog(
            report_id=rid,
            period=period,
            status="generated",
            conclusion=conclusion,
            findings_json=json.loads(json.dumps([f.model_dump() for f in findings]))
        )
        db.add(log)
        await db.flush()  # log.id 확보

        for k, path in arts.items():
            db.add(Artifact(report_id_fk=log.id, kind=k, path=path))

        await db.commit()

        # 7) Slack 알림
        await slack_notify(f"[MCP] 준수 보고서 생성 완료: {rid} (결론: {conclusion})")

        return ComplianceReportOut(
            report_id=rid,
            period=period,
            conclusion=conclusion,
            findings=findings,
            artifacts=arts
        )

    except Exception as e:
        await db.rollback()
        await slack_notify(f"[MCP][ERROR] 보고서 생성 실패({period}): {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{report_id}")
async def get_report(report_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    res = await db.execute(select(ReportLog).where(ReportLog.report_id == report_id))
    log = res.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="report not found")
    arts = {a.kind: a.path for a in log.artifacts}
    return {
        "report_id": log.report_id,
        "period": log.period,
        "status": log.status,
        "conclusion": log.conclusion,
        "artifacts": arts,
        "findings": log.findings_json
    }
@router.get("/generate")  # 편의용 GET -> 내부에서 POST 로직 재사용
async def generate_report_via_get(period: str, db: AsyncSession = Depends(get_db)):
    return await generate_report(period=period, db=db)  # 위의 POST 핸들러 호출
