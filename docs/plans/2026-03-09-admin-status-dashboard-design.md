# Admin Status Dashboard Design

**Date:** 2026-03-09

## Overview

A local host-side shell script (`status.sh`) that prints a side-by-side status report for both the prod and test environments, with no authentication required, separate stats per environment, and version tracking showing how far behind each environment is from the current git HEAD.

---

## Output Format

```
╔══════════════════════════════════════════════════╗
║              KMS Admin Status                    ║
╚══════════════════════════════════════════════════╝

                   PROD (8080)            TEST (8081)
  Status           ● RUNNING              ○ STOPPED
  Version          a1b2c3d ✓ current      —
  AI               online                 —
  Documents        47                     —
  Users            3                      —
  Review Queue     2 pending              —

  Last Backup    2026-03-09 07:01 (2 hours ago)   prod
                 2026-03-08 14:22 (18 hours ago)  test
  Git Branch     main
  Git HEAD       2937509  fix: update CLAUDE.md (2026-03-09)
  Backups        3 archives  (12K total)
```

When an environment is running but behind HEAD:
```
  Version          a1b2c3d ✓ current      f9e2a11 ⚠ 3 commits behind
```

---

## Components

### 1. `GET /health/summary` endpoint (public, no auth)

New endpoint in `api/main.py` alongside existing `/health` and `/health/ai`.

Returns:
```json
{
  "app_version": "a1b2c3d",
  "doc_count": 47,
  "user_count": 3,
  "review_queue_count": 2,
  "ai": "online"
}
```

Implementation:
- `app_version` — reads `settings.app_version` (from `APP_VERSION` env var)
- `doc_count` — `SELECT COUNT(*) FROM documents`
- `user_count` — `SELECT COUNT(*) FROM users`
- `review_queue_count` — `SELECT COUNT(*) FROM documents WHERE status IN ('needs_review', 'overdue')`
- `ai` — reuses same Ollama ping logic as `/health/ai`

### 2. `APP_VERSION` injection

In `config.py`: add `app_version: str = "unknown"`

In `docker-compose.yml` and `docker-compose.test.yml`: add to api service:
```yaml
environment:
  - APP_VERSION
```

In `start.sh`, `deploy.sh`, `deploy-test.sh`: add before `docker compose` commands:
```bash
export APP_VERSION=$(git rev-parse --short HEAD)
```

This means each environment reports the git hash that was current when it was last started or deployed.

### 3. `status.sh` script

Host-side bash script. No auth, no dependencies beyond `curl`, `git`, `awk`, `date`.

**Logic:**
1. Curl `http://localhost:8080/kms/api/health/summary` → prod status
2. Curl `http://localhost:8081/kms/api/health/summary` → test status
3. Get `git rev-parse --short HEAD` → current HEAD hash
4. For each running environment, compute `git rev-list {version}..HEAD --count` → commits behind
5. Find latest backup per env in `backups/` directory (`ls -t backups/*-prod.tar.gz | head -1` etc.)
6. Compute human-readable age ("2 hours ago", "3 days ago")
7. Print formatted table

**Version comparison:**
- `✓ current` — version matches HEAD exactly
- `⚠ N commits behind` — version is an ancestor of HEAD
- `? unknown` — version not in local git history (e.g. built from a different clone)

---

## Files

| File | Change |
|---|---|
| `api/main.py` | Add `GET /health/summary` endpoint |
| `api/config.py` | Add `app_version: str = "unknown"` |
| `api/tests/test_summary.py` | Tests for the summary endpoint |
| `docker-compose.yml` | Add `APP_VERSION` env passthrough to api service |
| `docker-compose.test.yml` | Same |
| `start.sh` | Export `APP_VERSION` before docker compose |
| `deploy.sh` | Export `APP_VERSION` before docker compose |
| `deploy-test.sh` | Export `APP_VERSION` before docker compose |
| `status.sh` | New host-side status script |

---

## Implementation Order

1. Add `app_version` to config and summary endpoint (API + tests)
2. Add `APP_VERSION` passthrough to compose files and scripts
3. Write `status.sh` and verify output
