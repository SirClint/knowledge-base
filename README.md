# Knowledge Management System (KMS)

A self-hosted knowledge base with AI-powered semantic search, automatic staleness detection, and a review queue to keep documentation current.

## Tech Stack

- **Frontend:** React 18, Vite, CodeMirror 6 (markdown editor), Marked (rendering)
- **Backend:** Python 3.12, FastAPI, SQLAlchemy (SQLite)
- **AI:** Ollama (local LLM) with Llama 3.2 (text) and nomic-embed-text (embeddings)
- **Vector DB:** ChromaDB
- **Reverse Proxy:** Caddy
- **Containerization:** Docker Compose

## Quick Start

### Prerequisites

- Docker and Docker Compose
- [Ollama](https://ollama.ai) (optional — needed for AI features, not required to run the app)

### Start the Stack

```bash
docker compose up -d
```

This starts four services:

| Service    | Description                        | Internal Port |
|------------|------------------------------------|---------------|
| `caddy`    | Reverse proxy                      | 8080          |
| `ui`       | React frontend (served via Nginx)  | 80            |
| `api`      | FastAPI backend                    | 8000          |
| `chromadb` | Vector database                    | 8000          |

Access the app at **http://localhost:8080/kms**

### Stop the Stack

```bash
docker compose down
```

To also remove persistent data (database, vector store, Caddy state):

```bash
docker compose down -v
```

### Rebuild After Code Changes

```bash
docker compose build api ui && docker compose up -d
```

Only use `--no-cache` if you changed `package.json` or `requirements.txt` (dependencies). For source code changes, a regular build is faster because it caches the dependency install layers.

### Enable AI Features (Optional)

The app works without Ollama — you get keyword search, document management, and the review queue. To enable semantic search, staleness detection, auto-tagging, and AI ingestion, start Ollama on the host:

```bash
# Start Ollama
ollama serve

# Pull the required models (one-time)
ollama pull llama3.2
ollama pull nomic-embed-text

# Restart the API to index documents with embeddings
docker compose restart api
```

## User Accounts

### Register

1. Go to http://localhost:8080/kms/register
2. Enter an email and password
3. Select a role (reader, editor, or admin)
4. You'll be redirected to the login page

Or via API:

```bash
curl -X POST http://localhost:8080/kms/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'
```

### Roles

Users select a role during registration (defaults to **editor**). There are three roles:

| Role     | Permissions                                |
|----------|--------------------------------------------|
| `reader` | Search, view documents, view review queue  |
| `editor` | All reader permissions + create/edit docs  |
| `admin`  | All editor permissions + delete docs       |

To create a user with a specific role (API only):

```bash
curl -X POST http://localhost:8080/kms/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "yourpassword", "role": "admin"}'
```

> **Note:** Role assignment during registration is currently unrestricted. Any user can self-register as admin.

### Login

Go to http://localhost:8080/kms/login and enter your credentials. Sessions last 1 hour (JWT-based, no refresh tokens).

## Adding Documents

There are three ways to add documents.

### 1. Via the Web UI

1. Log in with an **editor** or **admin** account
2. Click **"+ New Doc"** on the home page
3. Fill in:
   - **Title** — document title
   - **Category** — select from dropdown (Processes, Architecture, Projects, Personal)
   - **Body** — markdown content
4. Click **Save**

The filename is auto-generated from the title (e.g. "Deploy Process" → `team/processes/deploy-process.md`).

### 2. Via the Vault Directory

Drop `.md` files directly into the `vault/` directory on the host machine. Files are indexed automatically on API startup.

Documents should use YAML frontmatter:

```markdown
---
title: Deployment Process
tags: [deploy, kubernetes, ci-cd]
created: 2026-03-01
last_reviewed: 2026-03-01
review_interval: 30d
owner: alice
status: current
---

# Deployment Process

Your markdown content here...
```

**Frontmatter fields:**

| Field             | Required | Default     | Description                          |
|-------------------|----------|-------------|--------------------------------------|
| `title`           | No       | `""`        | Document title                       |
| `tags`            | No       | `[]`        | List of tags for categorization      |
| `created`         | No       | null        | ISO date created                     |
| `last_reviewed`   | No       | null        | ISO date of last review              |
| `review_interval` | No       | `"90d"`     | How often to flag for review         |
| `owner`           | No       | `""`        | Person or team responsible           |
| `status`          | No       | `"current"` | `current` or `needs_review`          |

**Vault directory structure:**

```
vault/
├── personal/          # Personal notes
└── team/
    ├── architecture/  # System design docs
    ├── processes/     # How-to guides, runbooks
    └── projects/      # Project-specific docs
```

### 3. Via the Ingestion API

Send unstructured text and let AI decide whether to create a new document or update an existing one:

```bash
curl -X POST http://localhost:8080/kms/api/ingest \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"message": "Our new deploy process is: pull latest, build image, push to registry, apply k8s manifests"}'
```

The AI (Llama 3.2) analyzes the message and either creates a new document at an appropriate path or updates an existing matching document.

## Search

The home page provides a search bar with three modes:

- **Keyword** — matches against title, tags, and body text (SQL LIKE)
- **Semantic** — embeds your query with `nomic-embed-text` and finds similar documents via ChromaDB vector similarity
- **Both** — combines keyword and semantic results, deduplicated

The default is **keyword** search, which works without Ollama. Semantic and both modes require Ollama to be running.

## AI Features

All AI features run locally via Ollama. No data leaves your machine.

### Semantic Search

Documents are embedded using the `nomic-embed-text` model and stored in ChromaDB. Search queries are embedded the same way, and results are ranked by vector similarity.

### Staleness Detection

A nightly job (2:00 AM) checks for documents that are overdue for review based on their `review_interval`:

1. Finds documents where `today - last_reviewed >= review_interval`
2. Sends each overdue document's body to Llama 3.2 for analysis
3. The AI checks for outdated version numbers, deprecated tools, stale procedures, etc.
4. Documents flagged as stale get their status set to `needs_review`

### Auto-tagging

The AI can suggest 3-5 tags for a document based on its content, using the existing tag vocabulary for consistency.

### Ingestion Intent Classification

When text is submitted to the `/ingest` endpoint, the AI determines whether to create a new document or update an existing one, and extracts a title and structured body.

## Review Queue

Visit http://localhost:8080/kms/review to see documents flagged for review.

For each document you can:
- Click through to read and update the content
- Click **"Mark reviewed"** to set `last_reviewed` to today and clear the `needs_review` status

## Configuration

Configuration is via environment variables in `.env` (see `.env.example`):

| Variable        | Default                          | Description                    |
|-----------------|----------------------------------|--------------------------------|
| `SECRET_KEY`    | `changeme`                       | JWT signing key                |
| `VAULT_PATH`    | `/vault`                         | Path to markdown files         |
| `OLLAMA_URL`    | `http://host.docker.internal:11434` | Ollama API endpoint         |
| `DATABASE_URL`  | `sqlite+aiosqlite:////data/kb.db`| SQLite database path           |
| `CHROMADB_PATH` | `/data/chroma`                   | ChromaDB storage path          |

## API Endpoints

| Method | Endpoint                          | Auth     | Description                   |
|--------|-----------------------------------|----------|-------------------------------|
| POST   | `/auth/register`                  | Public   | Register a new user           |
| POST   | `/auth/jwt/login`                 | Public   | Login, returns JWT            |
| GET    | `/docs/{path}`                    | Reader+  | Read a document               |
| POST   | `/docs`                           | Editor+  | Create a document             |
| PUT    | `/docs/{path}`                    | Editor+  | Update a document             |
| DELETE | `/docs/{path}`                    | Admin    | Delete a document             |
| GET    | `/search?q=...&mode=both`         | Reader+  | Search documents              |
| GET    | `/review/queue`                   | Reader+  | List documents needing review |
| POST   | `/review/{id}/mark-reviewed`      | Reader+  | Mark document as reviewed     |
| POST   | `/ingest`                         | Reader+  | AI-powered doc ingestion      |
| GET    | `/health`                         | Public   | Health check                  |

All API endpoints are prefixed with `/kms/api` when accessed through Caddy.
