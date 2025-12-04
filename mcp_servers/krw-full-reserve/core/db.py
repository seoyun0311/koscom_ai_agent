import os
import asyncpg
from typing import Optional

# 전역 커넥션 풀 (한 번만 만들고 재사용)
_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """
    전역 asyncpg 풀. 처음 호출될 때 자동으로 초기화.

    환경변수 우선순위:
      1) PG_DSN이 설정되어 있으면 그걸 그대로 사용
      2) 아니면 PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD 사용
    """
    global _pool

    # 이미 풀 생성됨
    if _pool is not None:
        return _pool

    dsn = os.getenv("PG_DSN")
    if dsn:
        # DSN 문자열 전체 사용하는 경우
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=5,
        )
    else:
        # 개별 값 사용
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
