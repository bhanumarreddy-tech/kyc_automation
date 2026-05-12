# KYC Automation

Prototype stack for **Tiger Analytics KYC automation**: upload company documents and get a populated KYC questionnaire. The **FastAPI** backend runs per-section [Anthropic Claude](https://www.anthropic.com/) calls—one pass for answers (with optional web search) and one for document validation—against PDFs, Word files, and images extracted in-process.

## Repository layout

| Path | Role |
|------|------|
| `src/` | React + TypeScript SPA (Vite, shadcn-ui, Tailwind) |
| `backend/` | FastAPI service (`app/main.py`, routes under `app/routes/`) |

## Prerequisites

- **Node.js** 18+ and npm (for the frontend)
- **Python** 3.11+ (for the backend)

## Local development

### 1. Backend

```sh
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # or: cp .env.example .env — then edit and set ANTHROPIC_API_KEY
```

Start the API (CORS defaults allow `http://localhost:8080` and `:5173`):

```sh
uvicorn app.main:app --reload --port 8000
```

Health check: `GET http://localhost:8000/api/health`

Environment variables are documented in `backend/.env.example`. **`ANTHROPIC_API_KEY`** is required. Tune `MAX_WEB_SEARCHES`, `ANSWER_CONCURRENCY`, and `ANSWER_INTER_CALL_DELAY_SECONDS` for your Anthropic usage tier.

### 2. Frontend

From the repository root:

```sh
npm install
npm run dev
```

Vite serves the app on **port 8080** and proxies `/api/*` to `http://localhost:8000`, so the SPA talks to your local FastAPI instance without changing code.

In **production builds**, the client uses the hardcoded backend origin in `src/lib/api.ts` (`PROD_BACKEND_URL`). Change that constant when you deploy the API to a new host.

## Tech stack

**Frontend:** Vite, React, TypeScript, shadcn-ui, Tailwind CSS, TanStack Query, React Router  

**Backend:** FastAPI, Uvicorn, Anthropic SDK, PyPDF, python-docx, Pillow, Pydantic

## Deployment notes

- **Frontend (Cloudflare Workers):** The repo includes `wrangler.jsonc` for deploying the built SPA (`dist/`). Typical commands: `npm run build`, then `npx wrangler deploy`.
- **Backend:** FastAPI cannot run on Cloudflare Workers with the current native dependencies (e.g. Pillow, PyPDF). Host `backend/` on a Python-friendly platform (Railway, Render, Fly.io, Cloud Run, etc.).
- Set **`CORS_ORIGINS`** on the backend to include your production frontend origin (comma-separated).
- After deploying the API, update **`PROD_BACKEND_URL`** in `src/lib/api.ts` so production builds target the correct origin (no trailing slash).

## License / project origin

UI scaffolding may reference [Lovable](https://lovable.dev) tooling; day-to-day development is standard git + local IDE as above.
