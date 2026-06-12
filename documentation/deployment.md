# Deployment & Setup Guide

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11 | Homebrew: `brew install python@3.11` |
| AWS Account | — | Bedrock access in `eu-central-1` |
| Docker Desktop | — | For Grafana LGTM + PostgreSQL |
| AWS CLI v2 | 2.x | `brew install awscli` |

---

## 1. Initial Setup (one-time)

```bash
# Clone and enter project
cd /path/to/cloudway-asp-guardrails

# Create virtual environment (Python 3.11 required)
/opt/homebrew/bin/python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env — set AWS_DEFAULT_REGION and Bedrock model IDs
# DO NOT put AWS credentials in .env — use ~/.aws/credentials
```

---

## 2. AWS Credentials

This system uses **AWS IAM Identity Center (SSO)** temporary credentials.
Credentials expire every ~1 hour and must be refreshed.

**Credential flow:**
```
AWS SSO Portal → ~/.aws/credentials [default] → boto3 (via credentials_profile_name="default")
```

**Never put credentials in `.env`** — temporary STS tokens (`ASIA...`) in `.env`
override `~/.aws/credentials` and cause `ExpiredTokenException` errors.

### Refreshing credentials

1. Go to your AWS SSO portal URL
2. Select account `156041425100` → role `AdministratorAccess`
3. Click **"Access keys"** → **Option 2** (credentials file)
4. Copy `aws_access_key_id`, `aws_secret_access_key`, `aws_session_token`
5. Update `~/.aws/credentials [default]`

**Verify:**
```bash
aws sts get-caller-identity --profile default
```

### Available Bedrock models (eu-central-1)

| Model | Profile ID | Notes |
|---|---|---|
| Claude Sonnet 4.6 | `eu.anthropic.claude-sonnet-4-6` | Used for RAG + fact extraction |
| Claude Haiku 4.5 | `eu.anthropic.claude-haiku-4-5-20251001-v1:0` | Cheaper, faster alternative |
| Titan Embed v2 | `amazon.titan-embed-text-v2:0` | 1024-dim embeddings |

---

## 3. One-Time Policy Ingestion

Run once to build the ChromaDB vector store from the policy PDF:

```bash
source .venv/bin/activate
python scripts/ingest_policy.py
```

Expected output:
```
[ingestor] Extracted 8 pages with content.
[ingestor] Created 27 chunks (size=900, overlap=175).
[ingestor] Done. 27 chunks stored in 'holiday_policy'.
Ingested 27 chunks in 8.1s.
```

The vector store is saved to `data/chroma/holiday_policy/`.

---

## 4. Running the System

### 4.1 Start observability stack (optional but recommended)

```bash
# If grafana/otel-lgtm container is not running:
docker run -p 3000:3000 -p 4317:4317 -p 4318:4318 --rm -it grafana/otel-lgtm

# Open Grafana: http://localhost:3000 (admin/admin)
# Go to Explore → Tempo → search service "cloudway"
```

### 4.2 Interactive CLI

```bash
source .venv/bin/activate
python -m src.main
```

Commands:
- Type a question → pipeline processes it
- `reset` → start a new session
- `quit` → exit

### 4.3 Run evaluation

```bash
# All 3 baselines (~10-15 minutes, requires valid AWS credentials)
python scripts/benchmark_baselines.py --baseline all

# Single baseline
python scripts/benchmark_baselines.py --baseline C

# Generate comparison report
python scripts/analyze_results.py

# View audit log
python scripts/view_audit_log.py --stats
python scripts/view_audit_log.py --thread session-001
```

---

## 5. Docker Compose (PostgreSQL + Grafana)

For production-grade persistence:

```bash
docker-compose up -d

# Initialize PostgreSQL schema
python scripts/init_db.py
```

Set in `.env`:
```
DATABASE_URL=postgresql://cloudway:cloudway@localhost:5432/guardrails
USE_POSTGRES_CHECKPOINTER=true
```

---

## 6. Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `AWS_DEFAULT_REGION` | ✅ | `eu-central-1` | AWS region for Bedrock |
| `AWS_PROFILE` | — | `default` | `~/.aws/credentials` profile |
| `BEDROCK_LLM` | — | `eu.anthropic.claude-sonnet-4-6` | LLM model ID |
| `BEDROCK_EMBEDDINGS` | — | `amazon.titan-embed-text-v2:0` | Embedding model ID |
| `EMBEDDING_BACKEND` | — | `huggingface` | `bedrock` or `huggingface` |
| `CHROMA_PERSIST_DIR` | — | `./data/chroma` | ChromaDB directory |
| `DATABASE_URL` | prod only | — | PostgreSQL connection string |
| `USE_POSTGRES_CHECKPOINTER` | — | `false` | Enable PostgreSQL for state |
| `AUDIT_LOG_PATH` | — | `logs/audit.jsonl` | JSONL fallback log path |
| `OTLP_ENDPOINT` | — | `http://localhost:4317` | Grafana LGTM gRPC endpoint |
| `LOG_LEVEL` | — | `INFO` | Python logging level |

---

## 7. Credential Expiry — Root Cause & Fix

**Problem:** `load_dotenv()` in agent modules re-loads expired credentials from `.env`
into `os.environ` after you try to clear them.

**Why it happens:**
1. `load_dotenv()` sets `AWS_ACCESS_KEY_ID` etc. from `.env`
2. You pop them from `os.environ`
3. Agent module import triggers another `load_dotenv()` → re-sets them from `.env`
4. boto3 sees the old values (highest priority) → `ExpiredTokenException`

**Fix used in `benchmark_baselines.py`:**
```python
# After ALL imports, pop stale credentials
for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
    os.environ.pop(k, None)

# Reset agent LLM singletons
import src.agents.rag_agent as _ra
_ra._llm = None
_ra._retriever = None
```

**Permanent fix:** Keep `.env` with empty credential lines:
```
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_SESSION_TOKEN=
```
This way `load_dotenv()` sets empty strings which boto3 ignores, falling through
to `~/.aws/credentials`.
