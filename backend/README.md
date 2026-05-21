# KYC Automation Backend

FastAPI service for the KYC automation stack. See the [root README](../README.md) for full-stack setup, deployment, and environment configuration.

## Quick start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # set GEMINI_API_KEY
uvicorn app.main:app --reload --port 8000
```

## Layout

| Path | Purpose |
|------|---------|
| `app/main.py` | Application entry, middleware, router registration |
| `app/routes/` | HTTP endpoints (`process`, `history`, `intake`, `narrative`) |
| `app/services/` | Pipeline orchestration, Gemini calls, document handling |
| `app/db/` | SQLAlchemy models and persistence helpers |
| `app/config.py` | Environment resolution, model IDs, limits, CORS |
| `config/kyc_playbook.yaml` | Analyst playbook rules evaluated at runtime |
| `tests/` | Pytest suite |

## API

- `GET /api/health` — liveness probe (includes database status when configured)
- `POST /api/process` — run the KYC pipeline for a company and optional documents
- `GET /api/history` — list saved submissions (requires Postgres)
- Additional routes for intake tokens, reruns, attachments, and compliance narrative

Configuration details: [`app/config.py`](app/config.py) and [`.env.example`](.env.example).

## RAG observability

The validation RAG pipeline records per-question retrieval traces (hybrid dense + lexical + RRF fusion, reranking, validation path) in Postgres as `rag_trace` on each submission.

After a run completes, open **RAG explorer** on the results screen in the frontend. It provides:

- **Overview** — indexing stats, validation path breakdown, RAG config snapshot
- **Embedding map** — 2D PCA projection of chunk vectors from Postgres, color-coded by document
- **Per-question retrieval** — hybrid → filter → rerank funnel with dense/lexical/fused/rerank scores

API: `GET /api/history/{submissionId}/rag-observability`
