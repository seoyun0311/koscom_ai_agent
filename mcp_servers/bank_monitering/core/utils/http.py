import httpx

DEFAULT_TIMEOUT = 20.0

async def get(url: str, params: dict = None, timeout: float = DEFAULT_TIMEOUT) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()

async def get_bytes(url: str, params: dict = None, timeout: float = DEFAULT_TIMEOUT) -> bytes:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.content
