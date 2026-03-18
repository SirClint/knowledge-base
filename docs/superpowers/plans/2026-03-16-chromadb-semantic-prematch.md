# ChromaDB Semantic Pre-Matching for Ingestion Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use ChromaDB semantic search to pre-identify the closest existing documents before calling the LLM, so the AI only has to decide among 3 specific candidates rather than scanning an ever-growing list of titles.

**Architecture:** `ingest_message()` calls `search_semantic(message, n_results=3)` before invoking the AI, enriches the hits with titles, and passes them as `semantic_candidates` to `classify_ingestion_intent()`. The prompt presents these candidates prominently so the model treats them as strong update candidates. If `search_semantic` fails (Ollama embedding offline), the service falls back to the existing title-list behavior silently.

**Tech Stack:** ChromaDB (already running), `nomic-embed-text` via Ollama (already used by `search_semantic`), FastAPI, pytest/asyncio.

---

## Chunk 1: Update `classify_ingestion_intent` to accept and surface semantic candidates

### Task 1: Add `semantic_candidates` parameter to the AI prompt

**Files:**
- Modify: `api/ai/service.py` — add `semantic_candidates` param, inject into prompt
- Modify: `api/tests/test_ai.py` — add test verifying candidates appear in prompt

- [ ] **Step 1: Write the failing test**

Add to `api/tests/test_ai.py`:

```python
async def test_classify_ingestion_prompt_includes_semantic_candidates():
    """When semantic_candidates are provided they must appear in the prompt
    so the model treats them as strong update candidates."""
    captured = {}

    async def fake_post(url, json=None, **kwargs):
        captured["payload"] = json
        return AsyncMock(json=lambda: {"response": '{"action": "update", "path": "team/sports/2026-winter-paralympics.md", "title": "Paralympics", "body": "Updated.", "needs_review": false, "reason": "Updated team/sports because semantic match found."}'})

    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = fake_post
        from ai.service import classify_ingestion_intent
        await classify_ingestion_intent(
            "More info about the Winter Paralympics",
            candidate_docs=[{"path": "team/sports/2026-winter-paralympics.md", "title": "2026 Winter Paralympics"}],
            semantic_candidates=[{"path": "team/sports/2026-winter-paralympics.md", "title": "2026 Winter Paralympics", "score": 0.91}],
        )
        prompt = captured["payload"]["prompt"]
        assert "2026 Winter Paralympics" in prompt
        assert "0.91" in prompt
        assert "Semantic" in prompt or "semantic" in prompt
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
docker compose -f docker-compose.test.yml --env-file .env.test exec api \
  pytest tests/test_ai.py::test_classify_ingestion_prompt_includes_semantic_candidates -v
```

Expected: FAIL — `classify_ingestion_intent` does not yet accept `semantic_candidates`.

- [ ] **Step 3: Implement the change in `api/ai/service.py`**

Update `classify_ingestion_intent` signature and prompt construction:

```python
async def classify_ingestion_intent(
    message: str,
    candidate_docs: list[dict],
    known_subfolders: list[str] | None = None,
    semantic_candidates: list[dict] | None = None,
) -> dict:
```

Build a semantic block to inject into the prompt, just before STEP 1:

```python
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
```

Then replace the existing STEP 1 block in the prompt with:

```python
        f"STEP 1 — action field:\n"
        f"{semantic_section}"
        f"  DEFAULT TO UPDATE. If the message is about the same topic as any semantic match above,\n"
        f"  set action='update' and use that document's path.\n"
        f"  If semantic matches are listed above, strongly prefer updating one of them.\n"
        f"  Only set action='create' if the message is about a subject clearly not covered\n"
        f"  by any existing document above.\n"
        f"  If multiple documents could match, pick the most closely related one.\n\n"
```

- [ ] **Step 4: Run the new test and the full ai test suite**

```bash
docker compose -f docker-compose.test.yml --env-file .env.test exec api \
  pytest tests/test_ai.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add api/ai/service.py api/tests/test_ai.py
git commit -m "feat: add semantic_candidates param to classify_ingestion_intent prompt"
```

---

## Chunk 2: Pre-match in `ingest_message` using `search_semantic`

### Task 2: Call `search_semantic` in `ingest_message` and pass candidates to AI

**Files:**
- Modify: `api/ingestion/service.py` — import `search_semantic`, build candidates, pass to AI
- Modify: `api/tests/test_ingestion.py` — add two new tests; update existing fake_classify signatures

- [ ] **Step 1: Write two failing tests**

Add to `api/tests/test_ingestion.py`:

```python
async def test_ingest_passes_semantic_candidates_to_ai():
    """ingest_message must call search_semantic and pass enriched results to
    classify_ingestion_intent as semantic_candidates."""
    captured = {}

    async def fake_classify(message, candidate_docs, known_subfolders=None, semantic_candidates=None):
        captured["semantic_candidates"] = semantic_candidates
        return {"action": "update", "path": "team/sports/2026-winter-paralympics.md",
                "title": "2026 Winter Paralympics", "body": "Updated."}

    with patch("ingestion.service.classify_ingestion_intent", new=fake_classify):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.search_semantic", new=AsyncMock(return_value=[
                {"path": "team/sports/2026-winter-paralympics.md", "score": 0.91},
            ])):
                with patch("ingestion.service.update_doc", new=AsyncMock(return_value=MagicMock())):
                    from ingestion.service import ingest_message
                    session = _mock_session(existing_docs=[
                        ("team/sports/2026-winter-paralympics.md", "2026 Winter Paralympics")
                    ])
                    await ingest_message("More info about the Winter Paralympics", session=session)

    assert captured["semantic_candidates"] is not None
    assert len(captured["semantic_candidates"]) == 1
    assert captured["semantic_candidates"][0]["path"] == "team/sports/2026-winter-paralympics.md"
    assert captured["semantic_candidates"][0]["title"] == "2026 Winter Paralympics"
    assert captured["semantic_candidates"][0]["score"] == pytest.approx(0.91)


async def test_ingest_falls_back_gracefully_when_search_semantic_fails():
    """If search_semantic raises (e.g. embedding model offline), ingest_message
    must still call classify_ingestion_intent — with semantic_candidates=None."""
    captured = {}

    async def fake_classify(message, candidate_docs, known_subfolders=None, semantic_candidates=None):
        captured["semantic_candidates"] = semantic_candidates
        return {"action": "create", "path": "personal/test.md", "title": "Test", "body": "Body."}

    with patch("ingestion.service.classify_ingestion_intent", new=fake_classify):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.search_semantic",
                       new=AsyncMock(side_effect=Exception("embedding model offline"))):
                with patch("ingestion.service.create_doc", new=AsyncMock(return_value=MagicMock())):
                    from ingestion.service import ingest_message
                    await ingest_message("test message", session=_mock_session())

    # Must have been called — fallback means semantic_candidates is None, not an exception
    assert "semantic_candidates" in captured
    assert captured["semantic_candidates"] is None
```

- [ ] **Step 2: Run both tests to confirm they fail**

```bash
docker compose -f docker-compose.test.yml --env-file .env.test exec api \
  pytest tests/test_ingestion.py::test_ingest_passes_semantic_candidates_to_ai \
         tests/test_ingestion.py::test_ingest_falls_back_gracefully_when_search_semantic_fails -v
```

Expected: FAIL — `search_semantic` not yet imported or called in `ingest_message`.

- [ ] **Step 3: Implement the change in `api/ingestion/service.py`**

Add import at the top:

```python
from search.service import search_semantic
```

In `ingest_message()`, after building `candidate_docs` and before calling `_scan_vault_subfolders`, add:

```python
    # Pre-identify closest matches via ChromaDB semantic search.
    # Gives the LLM specific candidates to evaluate rather than scanning all titles.
    semantic_candidates = None
    if candidate_docs:
        try:
            title_by_path = {d["path"]: d["title"] for d in candidate_docs}
            hits = await search_semantic(message, n_results=3)
            enriched = [
                {"path": h["path"], "title": title_by_path[h["path"]], "score": h["score"]}
                for h in hits
                if h["path"] in title_by_path
            ]
            if enriched:
                semantic_candidates = enriched
        except Exception:
            pass  # Embedding unavailable — fall back to AI title-matching only
```

Then pass `semantic_candidates` to `classify_ingestion_intent`:

```python
    intent = await classify_ingestion_intent(
        message, candidate_docs,
        known_subfolders=known_subfolders,
        semantic_candidates=semantic_candidates,
    )
```

- [ ] **Step 4: Update existing tests that will now call `search_semantic`**

Two existing tests use a `fake_classify` function and do not patch `search_semantic`. After this change, the real `search_semantic` will be called inside `ingest_message`, hitting Ollama/ChromaDB. Even though the exception is caught silently, these tests are no longer isolated. Patch `search_semantic` to return an empty list in both, and update `fake_classify` signatures:

In `test_ingest_passes_titles_to_ai_for_topic_matching`, wrap with an additional patch and update signature:
```python
    async def fake_classify(message, candidate_docs, known_subfolders=None, semantic_candidates=None):
        captured["candidate_docs"] = candidate_docs
        return {"action": "update", "path": "personal/pi.md", "title": "Pi", "body": "More info."}

    with patch("ingestion.service.classify_ingestion_intent", new=fake_classify):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.search_semantic", new=AsyncMock(return_value=[])):
                with patch("ingestion.service.update_doc", new=AsyncMock(return_value=MagicMock())):
                    ...
```

In `test_ingest_passes_vault_subfolders_to_ai`, same treatment:
```python
    async def fake_classify(message, candidate_docs, known_subfolders=None, semantic_candidates=None):
        captured["known_subfolders"] = known_subfolders
        return {"action": "create", "path": "personal/test.md", "title": "Test", "body": "Body."}

    with patch("ingestion.service.classify_ingestion_intent", new=fake_classify):
        with patch("ingestion.service._scan_vault_subfolders", return_value=["team/processes", "team/history"]):
            with patch("ingestion.service.search_semantic", new=AsyncMock(return_value=[])):
                with patch("ingestion.service.create_doc", new=AsyncMock(return_value=MagicMock())):
                    ...
```

- [ ] **Step 5: Run the full ingestion test suite**

```bash
docker compose -f docker-compose.test.yml --env-file .env.test exec api \
  pytest tests/test_ingestion.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Run the full test suite**

```bash
docker compose -f docker-compose.test.yml --env-file .env.test exec api \
  pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add api/ingestion/service.py api/tests/test_ingestion.py
git commit -m "feat: pre-match ingestion candidates via ChromaDB semantic search"
```

---

## Chunk 3: Build and verify

- [ ] **Step 1: Rebuild API image**

```bash
make build-api
```

- [ ] **Step 2: Restart containers**

```bash
make up
```

- [ ] **Step 3: Manual smoke test**

1. Open http://localhost:8081/kms
2. Navigate to New Doc → AI Ingestion
3. Submit text about a topic that matches an existing document (e.g. "more facts about the 2026 Winter Paralympics")
4. Verify the AI updates the existing doc rather than creating a new one
5. Check the blue banner — it should mention the folder and reason

- [ ] **Step 4: Commit if any prompt tweaks were needed, then push branch and open PR**

```bash
git push -u origin HEAD
gh pr create --title "feat: use ChromaDB semantic pre-matching for ingestion" \
  --body "$(cat <<'EOF'
## Summary
- Pre-identifies top 3 semantically similar docs via ChromaDB before calling the LLM
- LLM now decides among specific candidates rather than scanning all titles
- Gracefully falls back to existing title-list behavior if embedding model is offline

## Test plan
- [ ] `make pytest` passes
- [ ] Manual smoke: ingesting related content updates existing doc, not create new
- [ ] Manual smoke: blue banner shows correct folder/reason
- [ ] Ingesting a completely new topic still creates a new document

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
