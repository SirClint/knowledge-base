# KMS Development Makefile
#
# ALL targets operate on the TEST environment (port 8081).
# Production is ONLY updated via:  ./deploy.sh  (pulls from main, rebuilds, restarts prod)
#
# NEVER run bare `docker compose build/up` — it targets prod by default.

TEST_COMPOSE = docker compose -f docker-compose.test.yml --env-file .env.test

.PHONY: build build-ui build-api rebuild up down pytest e2e logs-api

build:
	$(TEST_COMPOSE) build

build-ui:
	$(TEST_COMPOSE) build ui

build-api:
	$(TEST_COMPOSE) build api

rebuild:
	$(TEST_COMPOSE) build --no-cache

up:
	$(TEST_COMPOSE) up -d

down:
	$(TEST_COMPOSE) down

pytest:
	$(TEST_COMPOSE) exec api pytest -v

e2e:
	cd e2e && npx playwright test

logs-api:
	$(TEST_COMPOSE) logs api --tail 30

# ── Production guard ──────────────────────────────────────────────────────────
# Any `make prod-*` target fails with an explicit error.
# Production changes must go through: commit → PR → merge to main → ./deploy.sh

prod-%:
	@echo ""
	@echo "  ERROR: Direct prod builds are not allowed."
	@echo ""
	@echo "  The correct workflow is:"
	@echo "    1. Fix and test against the test environment (make build-ui / make e2e)"
	@echo "    2. Commit your changes to a feature branch"
	@echo "    3. Open a PR and merge to main"
	@echo "    4. Run ./deploy.sh to pull main and deploy to prod"
	@echo ""
	@exit 1
