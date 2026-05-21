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

### MLflow UI on Railway (recommended for staging/production)

Deploy a **second Railway service** that only serves the MLflow UI, using the same Postgres tracking store as the API.

1. In your Railway project, **New → GitHub Repo** (same repository) or **Duplicate Service**.
2. Service settings:
   - **Root directory:** `backend`
   - **Dockerfile path:** `Dockerfile.mlflow`
3. **Variables** (link the Postgres plugin, same as the API):
   - **Link Postgres** — the UI prefers `DATABASE_URL` / `DATABASE_PUBLIC_URL` over `MLFLOW_TRACKING_URI`, so a shared `MLFLOW_TRACKING_URI=file:./mlruns` from the API will not break the UI service.
   - Optional override: `MLFLOW_TRACKING_URI=postgresql://…` (explicit Postgres URL)
   - Optional: `MLFLOW_UI_WORKERS=1` (default) — increase only with ≥1 GB RAM
   - Optional: `MLFLOW_SERVE_ARTIFACTS=true` to proxy artifact downloads (off by default to save memory)
   - Optional: `GIT_PYTHON_REFRESH=quiet` (silences Git warnings in the container)
4. **Resources:** allocate at least **1 GB RAM** for the MLflow UI service (512 MB often OOM-restarts on Railway).
5. **Health check** (Settings → Deploy → Health Check Path): set **`/health`**.
6. **Target port** (Settings → Networking → Public networking): must match **`$PORT`** (Railway usually sets this to **8080**). If target port is **5000** while the app listens on **8080**, you will get **502 Bad Gateway**.
7. **Networking → Generate domain** (e.g. `https://kyc-mlflow-staging.up.railway.app`).
8. Open the domain in a browser → **Experiments → kyc-rag-validation**.

Local Docker equivalent:

```powershell
docker compose --profile observability up -d mlflow
# http://localhost:5000  (uses backend/.env; for file storage set MLFLOW_TRACKING_URI=file:/app/mlruns)
```

**Security:** MLflow UI has no built-in authentication. Restrict the Railway URL (team-only, VPN, or auth proxy) before sharing it widely.
