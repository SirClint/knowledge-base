# Ingest Label Rename + About Popup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename misleading "New Document" UI labels to "Ingest New Information" / "+ Ingest", update all E2E test selectors that reference the old label, and add an About popup in the Home page sidebar.

**Architecture:** Two label changes in existing React pages + one new state variable and inline modal JSX in `Home.tsx`. No new files, no backend changes. E2E selectors must be updated in lockstep with the button rename.

**Tech Stack:** React 18, TypeScript, Vite, Playwright (E2E)

---

## File Map

| File | Change |
|------|--------|
| `ui/src/pages/DocPage.tsx` | Line 197: rename `<h2>` text |
| `ui/src/pages/Home.tsx` | Line 88: rename button label; add `showAbout` state, About link in sidebar, About modal |
| `e2e/tests/document-lifecycle.spec.ts` | 8× `text=+ New Doc` → `text=+ Ingest` |
| `e2e/tests/ingestion.spec.ts` | 2× selector update |
| `e2e/tests/documents.spec.ts` | 2× selector update |
| `e2e/tests/ingestion-real.spec.ts` | 1× selector update |
| `e2e/tests/auth.spec.ts` | 1× selector update |
| `e2e/tests/smoke.spec.ts` | 2× selector update + 1× test description rename |
| `e2e/tests/review.spec.ts` | 1× selector update |

---

## Task 1: Rename "New Document" labels in source

**Files:**
- Modify: `ui/src/pages/DocPage.tsx` (line 197)
- Modify: `ui/src/pages/Home.tsx` (line 88)

- [ ] **Step 1: Update the heading in DocPage.tsx**

  In `ui/src/pages/DocPage.tsx` line 197, change:
  ```tsx
  <h2 style={{ marginTop: 0 }}>New Document</h2>
  ```
  to:
  ```tsx
  <h2 style={{ marginTop: 0 }}>Ingest New Information</h2>
  ```

- [ ] **Step 2: Update the button label in Home.tsx**

  In `ui/src/pages/Home.tsx` line 88, change:
  ```tsx
  <button onClick={() => navigate("/doc/new")}>+ New Doc</button>
  ```
  to:
  ```tsx
  <button onClick={() => navigate("/doc/new")}>+ Ingest</button>
  ```

- [ ] **Step 3: Commit the source changes**

  ```bash
  git add ui/src/pages/DocPage.tsx ui/src/pages/Home.tsx
  git commit -m "feat: rename New Document labels to Ingest"
  ```

---

## Task 2: Update E2E selectors to match new button label

The existing E2E tests use `text=+ New Doc` as a Playwright selector in 17 places across 7 files. These must all become `text=+ Ingest`. One test description string in `smoke.spec.ts` also needs updating for consistency (it is not a selector — it won't break tests if missed, but update it anyway).

**Files:**
- Modify: `e2e/tests/document-lifecycle.spec.ts` (8 occurrences)
- Modify: `e2e/tests/ingestion.spec.ts` (2 occurrences)
- Modify: `e2e/tests/documents.spec.ts` (2 occurrences)
- Modify: `e2e/tests/ingestion-real.spec.ts` (1 occurrence)
- Modify: `e2e/tests/auth.spec.ts` (1 occurrence)
- Modify: `e2e/tests/smoke.spec.ts` (2 selector occurrences + 1 description string)
- Modify: `e2e/tests/review.spec.ts` (1 occurrence)

- [ ] **Step 1: Do a global find-and-replace of the selector string**

  Run this from the repo root. It updates every selector in one shot:
  ```bash
  sed -i 's/text=+ New Doc/text=+ Ingest/g' \
    e2e/tests/document-lifecycle.spec.ts \
    e2e/tests/ingestion.spec.ts \
    e2e/tests/documents.spec.ts \
    e2e/tests/ingestion-real.spec.ts \
    e2e/tests/auth.spec.ts \
    e2e/tests/smoke.spec.ts \
    e2e/tests/review.spec.ts
  ```

- [ ] **Step 2: Rename the smoke test description string**

  In `e2e/tests/smoke.spec.ts`, find and update:
  ```ts
  // Before:
  test("AI offline warning shown on new doc page when Ollama unreachable", async ({ page }) => {

  // After:
  test("AI offline warning shown on ingest page when Ollama unreachable", async ({ page }) => {
  ```

- [ ] **Step 3: Verify the count — no old selector strings remain**

  ```bash
  grep -r "New Doc" e2e/tests/
  ```
  Expected: no output (zero matches).

- [ ] **Step 4: Commit the E2E selector updates**

  ```bash
  git add e2e/tests/
  git commit -m "test: update E2E selectors for renamed Ingest button"
  ```

---

## Task 3: Add About popup to Home sidebar

**Files:**
- Modify: `ui/src/pages/Home.tsx`

The modal follows the inline-style pattern used throughout the app — no CSS framework or new component file needed.

- [ ] **Step 1: Add the `showAbout` state variable**

  In `ui/src/pages/Home.tsx`, add one state variable alongside the existing ones near the top of the `Home` component (around line 43):
  ```tsx
  const [showAbout, setShowAbout] = useState(false);
  ```

- [ ] **Step 2: Add the About link at the bottom of the sidebar**

  The sidebar `<div>` starts at approximately line 95 and ends after the `Object.keys(folderTree).sort().map(...)` block (around line 133). Append the About link **inside** the sidebar `<div>`, immediately after the closing `})}` of the folder map:

  ```tsx
  <div style={{ marginTop: 16, paddingTop: 12, borderTop: "1px solid #ddd" }}>
    <span
      onClick={() => setShowAbout(true)}
      style={{ fontSize: 12, color: "#888", cursor: "pointer" }}
    >
      About
    </span>
  </div>
  ```

- [ ] **Step 3: Add the About modal**

  Place the modal JSX **inside the outermost `return` div** of `Home`, at the very end just before the closing `</div>` of the component (after the `{/* Main content */}` section, around line 158). The modal renders conditionally:

  ```tsx
  {showAbout && (
    <div
      onClick={() => setShowAbout(false)}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.4)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "white", borderRadius: 6, padding: 24,
          maxWidth: 400, width: "90%", position: "relative",
        }}
      >
        <button
          onClick={() => setShowAbout(false)}
          style={{
            position: "absolute", top: 12, right: 12,
            border: "none", background: "none", cursor: "pointer", fontSize: 16,
          }}
        >
          ✕
        </button>
        <h2 style={{ marginTop: 0, marginBottom: 16 }}>Knowledge Base</h2>
        <p style={{ margin: "0 0 8px" }}><strong>Version:</strong> 0.0.1</p>
        <p style={{ margin: "0 0 8px" }}>
          <strong>GitHub:</strong>{" "}
          <a href="https://github.com/SirClint/knowledge-base" target="_blank" rel="noreferrer">
            github.com/SirClint/knowledge-base
          </a>
        </p>
        <div style={{ marginTop: 12 }}>
          <strong>Tech Stack</strong>
          <ul style={{ margin: "8px 0 0", paddingLeft: 20, fontSize: 13 }}>
            <li><strong>Frontend:</strong> React 18, TypeScript, Vite, CodeMirror 6</li>
            <li><strong>Backend:</strong> FastAPI, Python, SQLite, ChromaDB, Ollama</li>
            <li><strong>Infra:</strong> Docker, Caddy, Nginx</li>
          </ul>
        </div>
      </div>
    </div>
  )}
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add ui/src/pages/Home.tsx
  git commit -m "feat: add About popup in Home sidebar"
  ```

---

## Task 4: Build and verify

- [ ] **Step 1: Rebuild the UI**

  ```bash
  make build-ui
  ```
  Expected: build completes with no TypeScript errors.

- [ ] **Step 2: Verify manually in the browser**

  Open http://localhost:8081/kms and confirm:
  1. Button reads `+ Ingest` (not `+ New Doc`)
  2. Clicking it navigates to `/kms/doc/new` and the heading reads `Ingest New Information`
  3. An `About` link appears at the bottom of the sidebar
  4. Clicking `About` opens the modal with version, GitHub link, and tech stack
  5. Clicking ✕ or the backdrop closes the modal
  6. The GitHub link opens in a new tab

- [ ] **Step 3: Run E2E tests**

  ```bash
  make e2e
  ```
  Expected: all 24 tests pass.

- [ ] **Step 4: Push and open a PR**

  ```bash
  git push -u origin <branch-name>
  gh pr create --title "feat: rename Ingest labels and add About popup" \
    --body "$(cat <<'EOF'
  ## Summary
  - Renames 'New Document' / '+ New Doc' labels to 'Ingest New Information' / '+ Ingest' to accurately reflect that AI ingestion can update existing documents
  - Updates all 17 E2E Playwright selectors that referenced the old button label
  - Adds an About link at the bottom of the Home sidebar that opens a modal with version (0.0.1), GitHub repo link, and tech stack

  ## Test plan
  - [ ] '+ Ingest' button navigates to /kms/doc/new
  - [ ] Heading on that page reads 'Ingest New Information'
  - [ ] About link opens modal; ✕ and backdrop close it
  - [ ] GitHub link opens in new tab
  - [ ] `make e2e` passes (all 24 tests)
  EOF
  )"
  ```
