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

SYSTEM_MERGE = (
    "You are a document editor. You will be given an existing document and new information. "
    "Produce a single, well-structured markdown document that incorporates all content from both. "
    "Preserve existing sections and expand them or add new sections for new topics. "
    "Do not repeat information that already appears in the existing document. "
    "Do not include YAML frontmatter. Return ONLY the markdown body."
)


def _extract_json(text: str) -> str:
    """Extract the first JSON object or array from a model response.

    Handles models that wrap JSON in markdown code fences or add
    explanatory text before/after the JSON.
    """
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner).strip()
    # Find the outermost JSON object or array
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1]
    return text


async def _ollama(prompt: str, system: str) -> str:
    """Call Ollama and return the JSON-extracted response."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": "llama3.2", "prompt": prompt, "system": system, "stream": False},
            )
            return _extract_json(r.json()["response"])
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise RuntimeError(f"AI service is unreachable: {e}") from e


async def _ollama_raw(prompt: str, system: str) -> str:
    """Call Ollama and return the raw text response (no JSON extraction)."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": "llama3.2", "prompt": prompt, "system": system, "stream": False},
            )
            return r.json()["response"].strip()
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise RuntimeError(f"AI service is unreachable: {e}") from e


async def suggest_tags(body: str, existing_tags: list[str]) -> list[str]:
    prompt = f"Existing tags: {existing_tags}\n\nDocument content:\n{body[:2000]}"
    raw = await _ollama(prompt, SYSTEM_TAGS)
    return json.loads(raw)


async def check_staleness(body: str) -> dict:
    raw = await _ollama(body[:3000], SYSTEM_STALE)
    return json.loads(raw)


async def merge_doc_content(existing_body: str, new_message: str) -> str:
    """Merge new information into an existing document body, returning updated markdown."""
    prompt = (
        f"Existing document:\n{existing_body[:3000]}\n\n"
        f"New information to incorporate:\n{new_message[:1000]}"
    )
    return await _ollama_raw(prompt, SYSTEM_MERGE)


KNOWN_FOLDERS = ["personal", "team/processes", "team/systems", "team/projects"]

ROOT_FOLDERS = ["personal", "team"]


async def classify_ingestion_intent(
    message: str,
    candidate_docs: list[dict],
    known_subfolders: list[str] | None = None,
) -> dict:
    # Format as "Title → path" so the AI can match by topic, not just filename slug
    docs_block = "\n".join(
        f"{d.get('title') or d.get('path')} → {d['path']}"
        for d in candidate_docs[:100]
    )
    subfolders_line = (
        f"\nKnown subfolders: {', '.join(known_subfolders)}" if known_subfolders else ""
    )
    prompt = (
        f"Message: {message}\n\n"
        f"Existing documents:\n{docs_block}\n\n"
        f"Root folders (locked): {', '.join(ROOT_FOLDERS)}"
        f"{subfolders_line}"
    )
    system = (
        "Return JSON: {\"action\": \"create\"|\"update\", \"path\": string|null, "
        "\"title\": string, \"body\": string, \"needs_review\": boolean, \"reason\": string}. "
        "IMPORTANT: If ANY existing document covers the same or a closely related topic as the "
        "message, you MUST set action='update' and use that document's path. "
        "Only set action='create' if NO existing document is on the same topic. "
        "If creating, place the document under one of the root folders. "
        "You MAY reuse an existing subfolder if it fits, or invent a new descriptive subfolder "
        "under a root if none of the existing subfolders fit. "
        "Construct a slug filename. "
        "For body: reformat the message content as clean markdown. "
        "Set needs_review=true if you cannot confidently determine whether to update or create. "
        "For reason: write one sentence explaining your decision "
        "(e.g. 'Created new subfolder team/history because this is historical content'). "
        "Return ONLY valid JSON."
    )
    raw = await _ollama(prompt, system)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned invalid JSON: {e}") from e
