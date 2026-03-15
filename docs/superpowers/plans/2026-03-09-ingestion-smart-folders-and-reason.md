# Ingestion Smart Folders and Reason Feedback Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AI ingestion scan the vault for existing subfolders (rather than using a hardcoded list), allow the AI to create new subfolders under locked root folders, and return a human-readable reason for its decision that the UI displays as a dismissible banner.

**Architecture:** `ingestion/service.py` scans the vault for subfolders under root folders (`personal`, `team`) and passes them to `classify_ingestion_intent` as a new `known_subfolders` parameter. `ai/service.py` updates its system prompt to lock roots, suggest known subfolders, and permit new ones, and adds a `reason` field to its JSON output. The UI reads `reason` from the ingest API response and shows a short dismissible banner on the resulting doc page.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript (frontend), React Router v6 location state for passing reason across navigation.

---

## Chunk 1: Backend — AI service + ingestion service

### Task 1: Update `ai/service.py` — new signature, ROOT_FOLDERS, reason field

**Files:**
- Modify: `api/ai/service.py`

- [ ] **Step 1: Add `ROOT_FOLDERS` and update `classify_ingestion_intent` signature**

  In `api/ai/service.py`, add `ROOT_FOLDERS` after `KNOWN_FOLDERS` and update the function:

  ```python
  ROOT_FOLDERS = ["personal", "team"]


  async def classify_ingestion_intent(
      message: str,
      candidate_docs: list[dict],
      known_subfolders: list[str] | None = None,
  ) -> dict:
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
  ```

  Keep `KNOWN_FOLDERS` as-is — it is still imported by `docs_/router.py` for the folders dropdown.

- [ ] **Step 2: Verify the file looks right**

  Run: `grep -n "ROOT_FOLDERS\|known_subfolders\|reason" api/ai/service.py`
  Expected: lines showing `ROOT_FOLDERS`, `known_subfolders` parameter, and `reason` in the system prompt.

---

### Task 2: Update `api/tests/test_ai.py` — fix broken test, add new ones

**Files:**
- Modify: `api/tests/test_ai.py`

- [ ] **Step 1: Write failing test — `known_subfolders` appears in prompt**

  Replace `test_classify_ingestion_includes_known_folders_in_prompt` with a version that passes `known_subfolders` explicitly and checks both roots and subfolders appear:

  ```python
  async def test_classify_ingestion_includes_folder_context_in_prompt():
      captured = {}

      async def fake_post(url, json=None, **kwargs):
          captured["payload"] = json
          return AsyncMock(json=lambda: {"response": '{"action": "create", "path": "team/history/design.md", "title": "Design", "body": "Body.", "needs_review": false, "reason": "Created team/history for historical content."}'})

      with patch("ai.service.httpx.AsyncClient") as mock:
          mock.return_value.__aenter__.return_value.post = fake_post
          from ai.service import classify_ingestion_intent
          await classify_ingestion_intent(
              "architecture doc",
              candidate_docs=[{"path": "personal/existing.md", "title": "Existing Doc"}],
              known_subfolders=["team/processes", "team/systems"],
          )
          prompt = captured["payload"]["prompt"]
          assert "Existing documents:" in prompt
          assert "Root folders" in prompt
          assert "personal" in prompt
          assert "team" in prompt
          assert "team/processes" in prompt
          assert "team/systems" in prompt
  ```

- [ ] **Step 2: Build API and run tests to verify new test passes**

  Task 1 must be committed before this step so the updated `ai/service.py` is compiled into the container.

  Run: `make build-api && make pytest 2>&1 | grep -E "PASSED|FAILED|ERROR|test_classify_ingestion_includes"`
  Expected: `test_classify_ingestion_includes_folder_context_in_prompt` PASSED; the old test name `test_classify_ingestion_includes_known_folders_in_prompt` no longer appears.

- [ ] **Step 3: Write failing test — `reason` field returned**

  Add after the new folder test:

  ```python
  async def test_classify_ingestion_returns_reason():
      with patch("ai.service.httpx.AsyncClient") as mock:
          mock.return_value.__aenter__.return_value.post = AsyncMock(return_value=AsyncMock(
              json=lambda: {"response": '{"action": "create", "path": "team/history/zenobia.md", "title": "Zenobia", "body": "Historical queen.", "needs_review": false, "reason": "Created new subfolder team/history for historical content."}'}
          ))
          from ai.service import classify_ingestion_intent
          result = await classify_ingestion_intent("Zenobia was a queen.", candidate_docs=[])
          assert "reason" in result
          assert isinstance(result["reason"], str)
          assert len(result["reason"]) > 0
  ```

- [ ] **Step 4: Run tests to confirm both new tests pass**

  Run: `make pytest 2>&1 | grep -E "PASSED|FAILED|ERROR"`
  Expected: all tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add api/ai/service.py api/tests/test_ai.py
  git commit -m "feat: dynamic vault subfolders and reason field in classify_ingestion_intent"
  ```

---

### Task 3: Update `ingestion/service.py` — vault scan, pass subfolders, return reason

**Files:**
- Modify: `api/ingestion/service.py`

- [ ] **Step 1: Add `_scan_vault_subfolders` helper**

  After the imports at the top of `api/ingestion/service.py`, add:

  ```python
  from ai.service import classify_ingestion_intent, merge_doc_content, ROOT_FOLDERS
  ```

  (Replace the existing `from ai.service import classify_ingestion_intent, merge_doc_content` line.)

  Then add this function before `ingest_message`:

  ```python
  def _scan_vault_subfolders() -> list[str]:
      """Scan vault for existing subfolders under each root folder."""
      vault = Path(settings.vault_path)
      subfolders = []
      for root in ROOT_FOLDERS:
          root_path = vault / root
          if root_path.is_dir():
              for child in sorted(root_path.iterdir()):
                  if child.is_dir():
                      subfolders.append(f"{root}/{child.name}")
      return subfolders
  ```

- [ ] **Step 2: Update `ingest_message` to use vault scan and return reason**

  In `ingest_message`, replace:
  ```python
  intent = await classify_ingestion_intent(message, candidate_docs)
  ```
  with:
  ```python
  known_subfolders = _scan_vault_subfolders()
  intent = await classify_ingestion_intent(message, candidate_docs, known_subfolders=known_subfolders)
  ```

  Then add after the `needs_review` line:
  ```python
  reason = intent.get("reason", "")
  ```

  Then update both `return` statements to include `reason`:
  - The `update` return:
    ```python
    return {"action": "update", "path": path, "needs_review": needs_review, "reason": reason, "message": f"Updated doc: {title}."}
    ```
  - The final return:
    ```python
    return {"action": action, "path": path, "needs_review": needs_review, "reason": reason, "message": f"{'Updated' if action == 'update' else 'Created'} doc: {title}."}
    ```

- [ ] **Step 3: Run tests to ensure nothing broke**

  Run: `make pytest 2>&1 | grep -E "PASSED|FAILED|ERROR"`
  Expected: all tests PASS (existing ingestion tests use `AsyncMock` patches that don't care about the new parameter).

---

### Task 4: Update `api/tests/test_ingestion.py` — add new tests, fix fake_classify signatures

**Files:**
- Modify: `api/tests/test_ingestion.py`

- [ ] **Step 1: Patch `_scan_vault_subfolders` in all existing tests**

  After Task 3, `ingest_message` calls `_scan_vault_subfolders()` before `classify_ingestion_intent`. Add `patch("ingestion.service._scan_vault_subfolders", return_value=[])` to every existing test that calls `ingest_message` — that is all 7 existing tests. Nest it inside the existing `with patch(...)` blocks.

  For example, `test_ingest_creates_new_doc` becomes:

  ```python
  async def test_ingest_creates_new_doc():
      with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
          "action": "create",
          "path": "team/processes/new-process.md",
          "title": "New Process",
          "body": "Steps for the new process.",
      })):
          with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
              with patch("ingestion.service.create_doc", new=AsyncMock(return_value=None)):
                  from ingestion.service import ingest_message
                  result = await ingest_message("We have a new onboarding process: ...", session=_mock_session())
                  assert result["action"] == "create"
                  assert "new-process" in result["path"]
  ```

  Apply the same `patch("ingestion.service._scan_vault_subfolders", return_value=[])` pattern to all remaining existing tests. This keeps tests fully mocked and immune to vault filesystem state in the container.

- [ ] **Step 2: Update `fake_classify` in `test_ingest_passes_titles_to_ai_for_topic_matching`**

  The existing `fake_classify` has signature `(message, candidate_docs)`. Update it to accept the new parameter:

  ```python
  async def fake_classify(message, candidate_docs, known_subfolders=None):
      captured["candidate_docs"] = candidate_docs
      return {"action": "update", "path": "personal/pi.md", "title": "Pi", "body": "More info."}
  ```

- [ ] **Step 3: Write new test — vault subfolders passed to AI**

  Add:

  ```python
  async def test_ingest_passes_vault_subfolders_to_ai():
      """ingest_message must scan vault subfolders and pass them to classify_ingestion_intent."""
      captured = {}

      async def fake_classify(message, candidate_docs, known_subfolders=None):
          captured["known_subfolders"] = known_subfolders
          return {"action": "create", "path": "personal/test.md", "title": "Test", "body": "Body."}

      with patch("ingestion.service.classify_ingestion_intent", new=fake_classify):
          with patch("ingestion.service._scan_vault_subfolders", return_value=["team/processes", "team/history"]):
              with patch("ingestion.service.create_doc", new=AsyncMock(return_value=MagicMock())):
                  from ingestion.service import ingest_message
                  await ingest_message("test message", session=_mock_session())

      assert captured["known_subfolders"] == ["team/processes", "team/history"]
  ```

- [ ] **Step 4: Write new test — reason returned in response**

  Add:

  ```python
  async def test_ingest_returns_reason_from_ai():
      """ingest_message must include the AI reason in its return value."""
      with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
          "action": "create",
          "path": "team/history/zenobia.md",
          "title": "Zenobia",
          "body": "Historical queen of Palmyra.",
          "reason": "Created new subfolder team/history for historical content.",
      })):
          with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
              with patch("ingestion.service.create_doc", new=AsyncMock(return_value=MagicMock())):
                  from ingestion.service import ingest_message
                  result = await ingest_message("Zenobia was queen of Palmyra.", session=_mock_session())

      assert result["reason"] == "Created new subfolder team/history for historical content."
  ```

- [ ] **Step 5: Run all tests and confirm they pass**

  Run: `make pytest 2>&1 | grep -E "PASSED|FAILED|ERROR|passed|failed"`
  Expected: all tests PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add api/ingestion/service.py api/tests/test_ingestion.py
  git commit -m "feat: scan vault subfolders for ingestion context, return reason in response"
  ```

---

## Chunk 2: Frontend — ingest reason banner on DocPage

### Task 5: Update `ui/src/pages/DocPage.tsx` — pass and display ingest reason

**Files:**
- Modify: `ui/src/pages/DocPage.tsx`

- [ ] **Step 1: Add `useLocation` import**

  At the top of `DocPage.tsx`, `useLocation` is likely not imported. Find the react-router-dom import line and add it:

  ```typescript
  import { useNavigate, useParams, useLocation, Link } from "react-router-dom";
  ```

- [ ] **Step 2: Read location state and add dismiss state**

  Near the top of the `DocPage` component function, after existing `useState` declarations, add:

  ```typescript
  const location = useLocation();
  const [ingestReason, setIngestReason] = useState<string>(
    (location.state as any)?.ingestReason ?? ""
  );
  ```

- [ ] **Step 3: Update `ingest()` to pass reason via navigate state**

  Find the `navigate(\`/doc/${result.path}\`)` line inside `ingest()` and replace with:

  ```typescript
  navigate(`/doc/${result.path}`, { state: { ingestReason: result.reason ?? "" } });
  ```

- [ ] **Step 4: Add the dismissible banner to the JSX**

  Find the outermost returned JSX element in `DocPage` (the wrapping `<div>` or fragment). Add the banner as the first child, before the doc content:

  ```tsx
  {ingestReason && (
    <div style={{
      background: "#e8f4fd",
      border: "1px solid #b3d9f7",
      borderRadius: 4,
      padding: "10px 14px",
      marginBottom: 16,
      display: "flex",
      justifyContent: "space-between",
      alignItems: "flex-start",
      fontSize: 14,
    }}>
      <span>🤖 {ingestReason}</span>
      <button
        onClick={() => setIngestReason("")}
        style={{ background: "none", border: "none", cursor: "pointer", marginLeft: 12, fontSize: 16, lineHeight: 1 }}
        aria-label="Dismiss"
      >
        ×
      </button>
    </div>
  )}
  ```

- [ ] **Step 5: Build UI and verify**

  Run: `make build-ui`
  Expected: build succeeds with no TypeScript errors.

- [ ] **Step 6: Manual smoke test**

  1. Open `http://localhost:8081/kms`
  2. Navigate to "New Document" → AI tab
  3. Paste: `Zenobia was the Queen of Palmyra who defied Rome in the 3rd century.`
  4. Click "Process with AI"
  5. Verify: you land on the new doc page AND see a blue banner like "Created new subfolder team/history because this is historical content not related to existing subfolders."
  6. Click × — banner dismisses.

- [ ] **Step 7: Commit**

  ```bash
  git add ui/src/pages/DocPage.tsx
  git commit -m "feat: show AI ingestion reason as dismissible banner on doc page"
  ```

---

## Final Step: Push and open PR

- [ ] **Push branch and create PR**

  ```bash
  git push -u origin HEAD
  gh pr create --title "feat: smart ingestion folders with vault scanning and reason feedback" \
    --body "$(cat <<'EOF'
  ## Summary
  - AI ingestion now scans the vault for existing subfolders under locked root folders (`personal`, `team`), so it can reuse them or create new ones rather than being constrained to a hardcoded list
  - Added `reason` field to the AI JSON response explaining the placement decision
  - UI shows a dismissible info banner on the resulting doc page with the AI's reason

  ## Test plan
  - [ ] `make pytest` — all backend tests pass
  - [ ] Manual: ingest a clearly off-topic doc (e.g. historical figure) and verify it lands in a sensible new subfolder, not `team/processes`
  - [ ] Manual: verify banner appears and dismisses on click
  EOF
  )"
  ```
