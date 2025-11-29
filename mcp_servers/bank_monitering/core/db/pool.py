# core/db/pool.py

import os
import ssl
from typing import Optional

import asyncpg

# 내부에서 재사용할 풀
_PG_POOL: Optional[asyncpg.Pool] = None


def _load_pg_config():
    """
    환경변수에서 Postgres 접속 정보를 읽는다.
    값이 없으면 개발용 기본값을 쓴다.
    """
    host = os.getenv("PG_HOST", "127.0.0.1")
    port = int(os.getenv("PG_PORT", "5432"))
    user = os.getenv("PG_USER", "dancom")
    password = os.getenv("PG_PASSWORD", "1q2w3e4r!")
    database = os.getenv("PG_DATABASE", "dancom_db")
    ssl_mode = os.getenv("PG_SSL_MODE", "disable").lower()

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
        "ssl_mode": ssl_mode,
    }


def _build_ssl_context(ssl_mode: str):
    """
    Cloud DB(PostgreSQL)가 SSL을 요구할 수 있기 때문에
    ssl_mode=require 인 경우 TLS 컨텍스트를 만든다.
    """
    if ssl_mode in ("disable", "off", "false", "0"):
        return None

    # 간단히: 기본 컨텍스트 사용
    ctx = ssl.create_default_context()

    # 개발용: 인증서 검증은 끈다 (내부망 / 테스팅 목적)
    # 운영에서 제대로 쓰려면 CA 인증서 붙이고 검증 켜는 게 맞음.
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def get_pool() -> asyncpg.Pool:
    """
    전역 asyncpg 풀 생성/반환.
    """
    global _PG_POOL
    if _PG_POOL is not None:
        return _PG_POOL

    cfg = _load_pg_config()
    ssl_ctx = _build_ssl_context(cfg["ssl_mode"])

    print(
        f"📡 PostgreSQL connect: host={cfg['host']} port={cfg['port']} "
        f"user={cfg['user']} db={cfg['database']} ssl_mode={cfg['ssl_mode']}"
    )

    _PG_POOL = await asyncpg.create_pool(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        min_size=1,
        max_size=5,
        ssl=ssl_ctx,
    )
    return _PG_POOL


async def init_schema():
    pool = await get_pool()
    async with pool.acquire() as conn:

        # 스키마는 이미 존재한다고 했으니 생성은 optional
        await conn.execute("""
            CREATE SCHEMA IF NOT EXISTS stablecoin;
        """)

        # ★ 핵심 — search_path 강제 변경
        await conn.execute("""
            SET search_path TO stablecoin;
        """)

        # 여기부터는 stablecoin 스키마 안에서 테이블 생성됨

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bank_master (
                bank_id TEXT PRIMARY KEY,
                name TEXT,
                group_id TEXT,
                region TEXT
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS fss_snapshots (
                id SERIAL PRIMARY KEY,
                bank_id TEXT,
                fss_score NUMERIC,
                raw_json JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS risk_runs (
                id SERIAL PRIMARY KEY,
                total_exposure NUMERIC,
                hhi NUMERIC,
                top3_share NUMERIC,
                top3_breach BOOLEAN,
                raw_exposures JSONB,
                bank_details JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
