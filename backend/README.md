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

The validation RAG pipeline uses **state-of-the-art retrieval techniques** and records traces in Postgres (`rag_trace`).

After a run, open **RAG explorer** on the results screen. Tabs include:

- **Overview** — stats, failure case gallery, latency flame chart
- **Pipeline** — interactive threshold sandbox, pipeline flow, score waterfall, similarity heatmap
- **Embeddings** — PCA map + chunk boundary viewer (overlap, page markers, split diagnostics)
- **Retrieval** — side-by-side strategy compare (dense vs hybrid vs hybrid+rerank), per-question traces
- **Learn** — active technique guide

API endpoints:

- `GET /api/history/{submissionId}/rag-observability`
- `GET /api/history/{submissionId}/rag-filter-sandbox?serialNo=1&minDense=0.42`
- `GET /api/history/{submissionId}/rag-compare?serialNo=1`
- `GET /api/history/{submissionId}/chunk-boundaries`
