# Plan: Playwright E2E Tests for KMS

## Context
We've been fixing bugs across the stack (auth, doc creation, search, routing) and each fix required manual verification. E2E tests will catch regressions as we add features.

## Approach
Add Playwright tests at the project root (not inside `ui/`) so they test the full stack through the running Docker Compose services.

## Setup
- Install Playwright in a new `e2e/` directory at project root
- Configure to run against `http://localhost:8080/kms` (the Caddy proxy)
- Tests assume the stack is already running via `docker compose up -d`

## Files to Create

```
e2e/
├── package.json              # Playwright dependency
├── playwright.config.ts      # Base URL, browser config
├── tests/
│   ├── auth.spec.ts          # Register, login, logout
│   ├── documents.spec.ts     # Create, view, edit, search
│   └── review.spec.ts        # Review queue, mark reviewed
```

## Test Scenarios

### auth.spec.ts
1. Register a new account (with role selector)
2. Login with valid credentials
3. Login with invalid credentials shows error
4. Logout clears session and redirects to login
5. Unauthenticated users redirected to login

### documents.spec.ts
1. Create a new document (title, category dropdown, body)
2. Search for the created document by keyword
3. Click search result and verify doc content loads
4. Edit an existing document and save
5. Verify doc content updated after edit

### review.spec.ts
1. Navigate to review queue page
2. Verify review queue loads without error

## Running
```bash
cd e2e && npx playwright test
# or with UI mode:
cd e2e && npx playwright test --ui
```

## Key Details
- Each test file registers a unique user (timestamped email) to avoid conflicts
- Tests use `page.goto()`, `page.fill()`, `page.click()`, and assertions from `@playwright/test`
- Base URL: `http://localhost:8080/kms`
- Auth helper function shared across tests to register + login before each test
- Tests run against Chromium only (can expand later)

## Verification
1. `cd e2e && npm install`
2. `npx playwright install chromium`
3. Ensure stack is running: `docker compose up -d`
4. `npx playwright test --reporter=list`
5. All tests should pass green
