#!/usr/bin/env bash
# KMS Admin Status — shows side-by-side prod/test environment status

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PROD_URL="http://localhost:8080/kms/api"
TEST_URL="http://localhost:8081/kms/api"

# ── Fetch summary from an environment ─────────────────────────────────────────
fetch_summary() {
  local url="$1"
  curl -sf --max-time 10 "${url}/health/summary" 2>/dev/null
}

# ── Parse a JSON field ────────────────────────────────────────────────────────
json_field() {
  echo "$1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$2',''))" 2>/dev/null
}

# ── Human-readable time since a file was modified ─────────────────────────────
time_ago() {
  local file="$1"
  if [[ ! -f "$file" ]]; then echo "never"; return; fi
  local now
  now=$(date +%s)
  local mod
  mod=$(stat -c %Y "$file" 2>/dev/null || stat -f %m "$file" 2>/dev/null)
  local diff=$(( now - mod ))
  if   (( diff < 3600 ));   then echo "$(( diff / 60 )) minutes ago"
  elif (( diff < 86400 ));  then echo "$(( diff / 3600 )) hours ago"
  else                           echo "$(( diff / 86400 )) days ago"
  fi
}

# ── Commits behind HEAD ───────────────────────────────────────────────────────
commits_behind() {
  local version="$1"
  local head
  head=$(git rev-parse --short HEAD 2>/dev/null)
  if [[ -z "$version" || "$version" == "unknown" ]]; then echo "?"; return; fi
  if [[ "$version" == "$head" ]]; then echo "0"; return; fi
  # Check if version is in our git history
  if ! git rev-parse "${version}" > /dev/null 2>&1; then echo "?"; return; fi
  git rev-list "${version}..HEAD" --count 2>/dev/null || echo "?"
}

# ── Fetch both environments ───────────────────────────────────────────────────
PROD_JSON=$(fetch_summary "$PROD_URL")
TEST_JSON=$(fetch_summary "$TEST_URL")

# Prod fields
if [[ -n "$PROD_JSON" ]]; then
  PROD_STATUS="● RUNNING"
  PROD_VERSION=$(json_field "$PROD_JSON" "app_version")
  PROD_AI=$(json_field "$PROD_JSON" "ai")
  PROD_DOCS=$(json_field "$PROD_JSON" "doc_count")
  PROD_USERS=$(json_field "$PROD_JSON" "user_count")
  PROD_QUEUE=$(json_field "$PROD_JSON" "review_queue_count")
  PROD_BEHIND=$(commits_behind "$PROD_VERSION")
  if [[ "$PROD_BEHIND" == "0" ]]; then
    PROD_VER_LABEL="v${PROD_VERSION} ✓ current"
  elif [[ "$PROD_BEHIND" == "?" ]]; then
    PROD_VER_LABEL="v${PROD_VERSION} ? unknown"
  else
    PROD_VER_LABEL="v${PROD_VERSION} ⚠ ${PROD_BEHIND} behind"
  fi
else
  PROD_STATUS="○ STOPPED"
  PROD_VER_LABEL="—"
  PROD_AI="—"
  PROD_DOCS="—"
  PROD_USERS="—"
  PROD_QUEUE="—"
fi

# Test fields
if [[ -n "$TEST_JSON" ]]; then
  TEST_STATUS="● RUNNING"
  TEST_VERSION=$(json_field "$TEST_JSON" "app_version")
  TEST_AI=$(json_field "$TEST_JSON" "ai")
  TEST_DOCS=$(json_field "$TEST_JSON" "doc_count")
  TEST_USERS=$(json_field "$TEST_JSON" "user_count")
  TEST_QUEUE=$(json_field "$TEST_JSON" "review_queue_count")
  TEST_BEHIND=$(commits_behind "$TEST_VERSION")
  if [[ "$TEST_BEHIND" == "0" ]]; then
    TEST_VER_LABEL="v${TEST_VERSION} ✓ current"
  elif [[ "$TEST_BEHIND" == "?" ]]; then
    TEST_VER_LABEL="v${TEST_VERSION} ? unknown"
  else
    TEST_VER_LABEL="v${TEST_VERSION} ⚠ ${TEST_BEHIND} behind"
  fi
else
  TEST_STATUS="○ STOPPED"
  TEST_VER_LABEL="—"
  TEST_AI="—"
  TEST_DOCS="—"
  TEST_USERS="—"
  TEST_QUEUE="—"
fi

# ── Backup info ───────────────────────────────────────────────────────────────
LAST_PROD_BACKUP=$(ls -t "${SCRIPT_DIR}/backups"/*-prod.tar.gz 2>/dev/null | head -1)
LAST_TEST_BACKUP=$(ls -t "${SCRIPT_DIR}/backups"/*-test.tar.gz 2>/dev/null | head -1)
PROD_BACKUP_LABEL="${LAST_PROD_BACKUP:+$(basename "$LAST_PROD_BACKUP") ($(time_ago "$LAST_PROD_BACKUP"))}"
TEST_BACKUP_LABEL="${LAST_TEST_BACKUP:+$(basename "$LAST_TEST_BACKUP") ($(time_ago "$LAST_TEST_BACKUP"))}"
PROD_BACKUP_LABEL="${PROD_BACKUP_LABEL:-never}"
TEST_BACKUP_LABEL="${TEST_BACKUP_LABEL:-never}"
BACKUP_COUNT=$(ls "${SCRIPT_DIR}/backups"/*.tar.gz 2>/dev/null | wc -l | tr -d ' ')

# ── Git info ──────────────────────────────────────────────────────────────────
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
GIT_HEAD=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
GIT_MSG=$(git log -1 --pretty="%s" 2>/dev/null || echo "")
GIT_DATE=$(git log -1 --pretty="%ad" --date=short 2>/dev/null || echo "")

# ── Print ─────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                   KMS Admin Status                      ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
printf "  %-18s %-26s %s\n" "" "PROD (8080)" "TEST (8081)"
printf "  %-18s %-26s %s\n" "Status" "$PROD_STATUS" "$TEST_STATUS"
printf "  %-18s %-26s %s\n" "Version" "$PROD_VER_LABEL" "$TEST_VER_LABEL"
printf "  %-18s %-26s %s\n" "AI" "$PROD_AI" "$TEST_AI"
printf "  %-18s %-26s %s\n" "Documents" "$PROD_DOCS" "$TEST_DOCS"
printf "  %-18s %-26s %s\n" "Users" "$PROD_USERS" "$TEST_USERS"
PROD_QUEUE_LABEL=$([[ "$PROD_QUEUE" == "—" ]] && echo "—" || echo "${PROD_QUEUE} pending")
TEST_QUEUE_LABEL=$([[ "$TEST_QUEUE" == "—" ]] && echo "—" || echo "${TEST_QUEUE} pending")
printf "  %-18s %-26s %s\n" "Review Queue" "$PROD_QUEUE_LABEL" "$TEST_QUEUE_LABEL"
echo ""
printf "  %-18s %s\n" "Last Backup"    "prod: $PROD_BACKUP_LABEL"
printf "  %-18s %s\n" ""               "test: $TEST_BACKUP_LABEL"
printf "  %-18s %s\n" "Backups"        "${BACKUP_COUNT} archives"
echo ""
printf "  %-18s %s\n" "Git Branch"     "$GIT_BRANCH"
printf "  %-18s %s  %s  (%s)\n" "Git HEAD" "$GIT_HEAD" "$GIT_MSG" "$GIT_DATE"
echo ""
