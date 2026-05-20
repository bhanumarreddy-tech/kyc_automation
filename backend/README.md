# KYC Automation Backend

FastAPI service that powers the Tiger Analytics KYC automation prototype. It accepts a company name and optional documents (PDF, DOCX, images) and returns a populated 64-question KYC questionnaire driven by per-section **Google Gemini** calls.

For each of the 8 sections the backend makes two LLM calls:

1. **Answer call** — Gemini with **Google Search** grounding answers the section's questions using public web information and returns the URLs it used.
2. **Validation call** — Gemini receives the proposed answers plus the uploaded documents and returns, per question, whether the documents support the answer (`Yes`/`No`) and, when `Yes`, the document source (filename, page, excerpt).

The 8 answer calls run concurrently via `asyncio.gather`, and the 8 validation calls run concurrently afterwards.

## Prerequisites

- Python 3.10+
- A **Gemini API key** from [Google AI Studio](https://aistudio.google.com/) (set `GEMINI_API_KEY`, or `GOOGLE_API_KEY`)

## Quick start

```powershell
# from the repo root
cd backend

# Create and activate a virtualenv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# then edit .env and set GEMINI_API_KEY

# Run the API server
uvicorn app.main:app --reload --port 8000
```

The frontend (`npm run dev` at the repo root, default port 8080) proxies all `/api/*` requests to `http://localhost:8000` via the dev-server config in `vite.config.ts`.

## Endpoints

- `GET /api/health` — simple liveness probe.
- `POST /api/process` — multipart/form-data request:
  - `company_name`: string (required)
  - `files`: zero or more uploaded documents (PDF, DOCX, PNG, JPG)
  - Response: `{ "rows": KYCRow[] }` with exactly 64 entries, one per question, with `answer`, `sources`, `validation`, `validationSources`, and `analystComments` fields.

## Configuration

Non-secret tuning (Gemini answer/validation model IDs, validation limits,
concurrency, overload backoff, CORS allow-list, and similar) lives in the
constants at the top of [`app/config.py`](app/config.py).

Secrets in `.env` (see [.env.example](.env.example)):

| Variable | Notes |
|----------|-------|
| `GEMINI_API_KEY` | _(required)_ Google AI Studio API key (`GOOGLE_API_KEY` alias) |
| `DATABASE_URL` or `DATABASE_PASSWORD` + `PG*` | Postgres (AWS RDS defaults in `config.py`) |
| `BLOB_READ_WRITE_TOKEN`, optional `BLOB_STORE_ID` | Required when uploads use Vercel Blob |
