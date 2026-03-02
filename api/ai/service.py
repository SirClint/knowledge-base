import httpx
import json
from config import settings

SYSTEM_TAGS = (
    "You are a tagging assistant. Given document content and a list of existing tags, "
    "return a JSON array of 3-5 relevant tags chosen from or consistent with the existing tags. "
    "Return ONLY valid JSON."
)

SYSTEM_STALE = (
    "You are a document staleness detector. Given document content, return a JSON object "
    "with 'stale' (boolean) and 'reason' (string). Mark as stale if you detect version numbers, "
    "tool names, or procedures that may be outdated. Return ONLY valid JSON."
)


async def _ollama(prompt: str, system: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{settings.ollama_url}/api/generate",
            json={"model": "llama3.2", "prompt": prompt, "system": system, "stream": False},
        )
        return r.json()["response"]


async def suggest_tags(body: str, existing_tags: list[str]) -> list[str]:
    prompt = f"Existing tags: {existing_tags}\n\nDocument content:\n{body[:2000]}"
    raw = await _ollama(prompt, SYSTEM_TAGS)
    return json.loads(raw)


async def check_staleness(body: str) -> dict:
    raw = await _ollama(body[:3000], SYSTEM_STALE)
    return json.loads(raw)


async def classify_ingestion_intent(message: str, candidate_paths: list[str]) -> dict:
    prompt = f"Message: {message}\n\nExisting doc paths:\n" + "\n".join(candidate_paths[:20])
    system = (
        "Return JSON: {\"action\": \"create\"|\"update\", \"path\": string|null, "
        "\"title\": string, \"body\": string}. If updating, pick the most relevant path. "
        "If unsure, use 'create'."
    )
    raw = await _ollama(prompt, system)
    return json.loads(raw)
