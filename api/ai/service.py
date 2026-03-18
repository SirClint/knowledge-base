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
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": "qwen2.5:7b", "prompt": prompt, "system": system, "stream": False},
            )
            return _extract_json(r.json()["response"])
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise RuntimeError(f"AI service is unreachable: {e}") from e


async def _ollama_raw(prompt: str, system: str) -> str:
    """Call Ollama and return the raw text response (no JSON extraction)."""
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": "qwen2.5:7b", "prompt": prompt, "system": system, "stream": False},
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
    semantic_candidates: list[dict] | None = None,
) -> dict:
    # Format as "Title → path" so the AI can match by topic, not just filename slug
    docs_block = "\n".join(
        f"{d.get('title') or d.get('path')} → {d['path']}"
        for d in candidate_docs[:100]
    )
    # Always show at least some folder examples so the model has concrete patterns to follow
    SEED_FOLDERS = ["personal/notes", "personal/history", "team/projects", "team/finance"]
    display_folders = known_subfolders if known_subfolders else SEED_FOLDERS
    folders_block = "\n".join(f"  - {f}" for f in display_folders)
    if semantic_candidates:
        sem_lines = "\n".join(
            f"  - {c['title']} → {c['path']} (similarity: {c['score']:.2f})"
            for c in semantic_candidates
        )
        semantic_section = (
            f"Semantic search found these as the closest existing documents:\n{sem_lines}\n\n"
        )
    else:
        semantic_section = ""

    prompt = (
        f"Message to file:\n{message}\n\n"
        f"Existing documents (title → path):\n{docs_block if docs_block else '(none yet)'}\n\n"
        f"--- INSTRUCTIONS ---\n\n"
        f"STEP 1 — action field:\n"
        f"{semantic_section}"
        f"  DEFAULT TO UPDATE. If the message is about the same topic as any semantic match above,\n"
        f"  set action='update' and use that document's path.\n"
        f"  If semantic matches are listed above, strongly prefer updating one of them.\n"
        f"  Only set action='create' if the message is about a subject clearly not covered\n"
        f"  by any existing document above.\n"
        f"  If multiple documents could match, pick the most closely related one.\n\n"
        f"STEP 2 — path field (required format: folder/filename.md):\n"
        f"  Known folders:\n{folders_block}\n"
        f"  Rules:\n"
        f"  - Pick the most relevant folder from the list above.\n"
        f"  - If nothing fits, invent a new folder using one of the roots 'personal' or 'team' plus a\n"
        f"    short descriptive topic word (e.g. personal/cooking, team/deployment).\n"
        f"  - The topic word MUST describe the content. NEVER use generic words: subfolder, misc, new, docs, files.\n"
        f"  - filename must be lowercase, hyphenated, no spaces or uppercase.\n"
        f"  CORRECT: personal/history/roman-empire-notes.md\n"
        f"  CORRECT: team/deployment/rollback-procedure.md\n"
        f"  CORRECT: personal/cooking/carbonara-recipe.md\n"
        f"  WRONG:   personal/subfolder/notes.md  ← 'subfolder' is not descriptive\n"
        f"  WRONG:   team/misc/doc.md             ← 'misc' is not descriptive\n\n"
        f"STEP 3 — other fields:\n"
        f"  title: clear descriptive title for the document.\n"
        f"  body: reformat the message as markdown — use ## headings for each section, blank lines between\n"
        f"    sections, **bold** key terms. Do not produce a wall of plain text.\n"
        f"  needs_review: true if you are uncertain about the action or folder choice.\n"
        f"  reason: one sentence that names the action taken, the exact folder chosen, and why that folder\n"
        f"    fits the content. Example: \"Created personal/cooking because the message is a recipe.\""
    )
    system = (
        "You are a document filing assistant. "
        "Return ONLY a valid JSON object with exactly these fields: "
        "{\"action\": \"create\" or \"update\", \"path\": string, \"title\": string, "
        "\"body\": string, \"needs_review\": boolean, \"reason\": string}. "
        "No markdown fences. No explanation. ONLY the JSON object."
    )
    for attempt in range(2):
        raw = await _ollama(prompt, system)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            if attempt == 0:
                continue  # model may have been loading — retry once
            raise ValueError(f"AI returned invalid JSON after retry: {raw[:200]}")
