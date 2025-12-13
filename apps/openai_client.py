import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from .settings import settings

OPENAI_URL = "https://api.openai.com/v1/responses"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def responses_create(payload: dict) -> dict:
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(OPENAI_URL, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()
