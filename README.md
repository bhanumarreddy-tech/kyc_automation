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

Secrets are listed in `backend/.env.example` (copy to `backend/.env`). **`GEMINI_API_KEY`** (or **`GOOGLE_API_KEY`**) is required. Models, concurrency caps, validation limits, overload backoff, and **`CORS_ALLOWED_ORIGINS`** are set in **`backend/app/config.py`** (not environment variables).

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

1. Put **`GEMINI_API_KEY`** and any Blob/Postgres secrets (see `backend/.env.example`) in **`backend/.env`**.
2. From the **repository root**:

```sh
docker compose build
docker compose up -d
```

3. Open **`http://localhost:8080`** (UI) — **`http://localhost:8080/api/health`** should return `{"status":"ok"}` via nginx → backend.

4. Logs: `docker compose logs -f`. Stop: `docker compose down`.

For **split deployments** (static UI on one host, API on another), build the frontend with  
`VITE_API_BASE_URL=https://your-api-host` and add your UI origin to **`CORS_ALLOWED_ORIGINS`** in **`backend/app/config.py`**.

## Other deployment notes

- **Frontend (Cloudflare Workers):** The repo includes `wrangler.jsonc`. Typical commands: `npm run build`, then `npx wrangler deploy`. Set **`VITE_API_BASE_URL`** to your public API URL before building.
- **Backend:** Host `backend/` on a Python-friendly platform (Railway, Render, Fly.io, Cloud Run, etc.). Update **`CORS_ALLOWED_ORIGINS`** in **`app/config.py`** when the browser hits the API on a different origin than the SPA.

## License / project origin

UI scaffolding may reference [Lovable](https://lovable.dev) tooling; day-to-day development is standard git + local IDE as above.
