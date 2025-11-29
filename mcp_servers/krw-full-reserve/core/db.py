# core/db.py
import os
import asyncpg
from typing import Optional

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """
    전역 asyncpg 풀. 처음 호출될 때 자동으로 초기화.
    환경변수:
      PG_DSN   또는 (PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD)
    """
    global _pool
    if _pool is not None:
        return _pool

    dsn = os.getenv("PG_DSN")
    if dsn:
        _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
    else:
        _pool = await asyncpg.create_pool(
            host=os.getenv("PG_HOST", "127.0.0.1"),
            port=int(os.getenv("PG_PORT", "5432")),
            database=os.getenv("PG_DB", "dancom_db"),
            user=os.getenv("PG_USER", "dancom"),
            password=os.getenv("PG_PASSWORD", "1q2w3e4r!"),
            min_size=1,
            max_size=5,
        )

    return _pool
