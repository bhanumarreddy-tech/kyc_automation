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

See `.env.example`. Recognised variables:

| Variable                         | Default                                         | Notes |
|----------------------------------|-------------------------------------------------|-------|
| `GEMINI_API_KEY`                 | _(required)_                                    | Google AI Studio API key |
| `GOOGLE_API_KEY`                 | —                                               | Alias for `GEMINI_API_KEY` |
| `GEMINI_MODEL`                   | `gemini-3.1-flash-preview`                      | Override model ID |
| `MAX_FILE_MB`                    | `20`                                            | Per-file upload limit |
| `GEMINI_OVERLOAD_EXTRA_ATTEMPTS` | `3`                                             | Extra full retries after backoff on transient errors |
| `GEMINI_OVERLOAD_BASE_DELAY_SECONDS` | `10`                                        | Base delay (seconds) for overload backoff |
| `CORS_ORIGINS`                   | `http://localhost:8080,http://localhost:5173,…` | Comma-separated allow-list |
