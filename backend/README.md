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

## RAG observability (MLflow)

The validation RAG pipeline can emit **MLflow GenAI traces** for indexing, embedding, hybrid retrieval (dense + lexical + RRF), reranking, and per-question Gemini validation.

1. Enable in `.env`:

   ```env
   MLFLOW_TRACING_ENABLED=true
   MLFLOW_TRACKING_URI=file:./mlruns
   MLFLOW_EXPERIMENT_NAME=kyc-rag-validation
   ```

2. Run the backend and process a submission as usual.

3. Open the MLflow UI (from the `backend` directory):

   ```powershell
   mlflow ui --port 5000
   ```

4. Browse **Experiments → kyc-rag-validation**. Each pipeline run is one MLflow run; expand traces to see:
   - **RETRIEVER** spans — query text, hybrid candidate scores, filtered/reranked top-15 hits
   - **RERANKER** spans — token-overlap rerank ordering
   - **EMBEDDING** spans — document/query embedding batches
   - **CHAIN** / **CHAT_MODEL** spans — per-question validation outcomes

Traces are logged asynchronously (`mlflow.config.enable_async_logging()`) to keep pipeline latency low. Point `MLFLOW_TRACKING_URI` at a remote MLflow tracking server for shared team visibility.
