# KOSCOM/apps/api/verify_etherscan_v2.py
import requests
import json
from core.config.settings import settings
from core.db.database import get_session, AuditEvent
from core.logging.logger import get_logger

logger = get_logger(__name__)

def fetch_usdt_transactions_for_address(address: str):
    """특정 주소 기준으로 Etherscan V2에서 USDT 트랜잭션 조회"""
    url = (
        "https://api.etherscan.io/v2/api"
        f"?chainid=1"
        f"&module=account"
        f"&action=tokentx"
        f"&address={address}"
        f"&contractaddress={settings.USDT_CONTRACT}"
        f"&page=1&offset=100"
        f"&sort=desc"
        f"&apikey={settings.ETHERSCAN_API_KEY}"
    )
    res = requests.get(url)
    data = res.json()

    if data.get("status") != "1":
        logger.debug(f"{address} 조회 실패: {data.get('message')}")
        return []
    return data["result"]

def verify_usdt_transactions():
    logger.info("=== USDT 감사 검증 (주소별 V2) 시작 ===")
    session = get_session()
    db_events = session.query(AuditEvent).all()
    logger.info(f"📦 DB에서 {len(db_events)}개의 AuditEvent 로드 완료")

    # 모든 관련 주소 수집 (중복 제거)
    addresses = set()
    for e in db_events:
        if e.from_address:
            addresses.add(e.from_address.lower())
        if e.to_address:
            addresses.add(e.to_address.lower())

    logger.info(f"🔍 총 {len(addresses)}개 주소에 대해 검증 진행")

    etherscan_map = {}
    for addr in addresses:
        txs = fetch_usdt_transactions_for_address(addr)
        for tx in txs:
            etherscan_map[tx["hash"].lower()] = tx

    logger.info(f"🌐 Etherscan에서 총 {len(etherscan_map)}개 트랜잭션 수집 완료")

    matches, missing, mismatches = [], [], []

    for e in db_events:
        tx = etherscan_map.get(e.event_id.lower())
        if not tx:
            missing.append(e.event_id)
            continue

        same_from = tx["from"].lower() == (e.from_address or "").lower()
        same_to = tx["to"].lower() == (e.to_address or "").lower()
        same_amt = abs(float(tx["value"]) / (10 ** int(tx["tokenDecimal"])) - float(e.amount)) < 1e-6

        if same_from and same_to and same_amt:
            matches.append(e.event_id)
        else:
            mismatches.append({
                "event_id": e.event_id,
                "db_from": e.from_address,
                "api_from": tx["from"],
                "db_to": e.to_address,
                "api_to": tx["to"],
                "db_amt": e.amount,
                "api_amt": float(tx["value"]) / (10 ** int(tx["tokenDecimal"]))
            })

    logger.info(f"✅ 일치한 트랜잭션: {len(matches)}건")
    logger.info(f"⚠️ 누락된 트랜잭션: {len(missing)}건")
    logger.info(f"❌ 불일치한 트랜잭션: {len(mismatches)}건")

    if missing:
        logger.warning("=== 누락된 Tx ===")
        for txid in missing[:10]:
            logger.warning(f"  - {txid}")

    if mismatches:
        logger.warning("=== 불일치 Tx 예시 ===")
        for m in mismatches[:3]:
            logger.warning(json.dumps(m, indent=2))

    session.close()
    logger.info("=== 검증 완료 ===")

if __name__ == "__main__":
    verify_usdt_transactions()

