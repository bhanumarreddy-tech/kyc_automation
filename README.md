# KYC Automation

Prototype stack for **Tiger Analytics KYC automation**: upload company documents and get a populated KYC questionnaire. The **FastAPI** backend runs per-section **[Google Gemini](https://ai.google.dev/)** calls—one pass for answers (with Google Search grounding) and one for document validation—against PDFs, Word files, and images extracted in-process.

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
copy .env.example .env   # or: cp .env.example .env — then edit and set GEMINI_API_KEY
```

Start the API (CORS defaults allow `http://localhost:8080` and `:5173`):

```sh
uvicorn app.main:app --reload --port 8000
```

Health check: `GET http://localhost:8000/api/health`

Environment variables are documented in `backend/.env.example`. **`GEMINI_API_KEY`** (or **`GOOGLE_API_KEY`**) is required. Tune `ANSWER_CONCURRENCY` and `ANSWER_INTER_CALL_DELAY_SECONDS` for your Gemini API quota.

### 2. Frontend

From the repository root:

```sh
npm install
npm run dev
```

Vite serves the app on **port 8080** and proxies `/api/*` to `http://localhost:8000`, so the SPA talks to your local FastAPI instance without changing code.

In **production builds**, API calls use **`VITE_API_BASE_URL`** when set; otherwise they stay **same-origin** (`/api/...`), which matches the Docker Compose setup below (nginx proxies `/api` to FastAPI).

## Tech stack

**Frontend:** Vite, React, TypeScript, shadcn-ui, Tailwind CSS, TanStack Query, React Router  

**Backend:** FastAPI, Uvicorn, Google Gemini (`google-genai`), PyPDF, python-docx, Pillow, Pydantic

## Deploy and test (Docker Compose)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose).

1. Put **`GEMINI_API_KEY`** (and any other vars) in **`backend/.env`**.
2. From the **repository root**:

```sh
docker compose build
docker compose up -d
```

3. Open **`http://localhost:8080`** (UI) — **`http://localhost:8080/api/health`** should return `{"status":"ok"}` via nginx → backend.

4. Logs: `docker compose logs -f`. Stop: `docker compose down`.

For **split deployments** (static UI on one host, API on another), build the frontend with  
`VITE_API_BASE_URL=https://your-api-host` and set **`CORS_ORIGINS`** on the backend to your UI origin.

## Other deployment notes

- **Frontend (Cloudflare Workers):** The repo includes `wrangler.jsonc`. Typical commands: `npm run build`, then `npx wrangler deploy`. Set **`VITE_API_BASE_URL`** to your public API URL before building.
- **Backend:** Host `backend/` on a Python-friendly platform (Railway, Render, Fly.io, Cloud Run, etc.). Set **`CORS_ORIGINS`** when the browser talks to the API on a different origin than the SPA.

## License / project origin

UI scaffolding may reference [Lovable](https://lovable.dev) tooling; day-to-day development is standard git + local IDE as above.
