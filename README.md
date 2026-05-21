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

Secrets are listed in `backend/.env.example` (copy to `backend/.env`). **`GEMINI_API_KEY`** (or **`GOOGLE_API_KEY`**) is required. Models, concurrency caps, validation limits, overload backoff, and CORS defaults are set in **`backend/app/config.py`**. On Railway, set **`APP_ENV=staging`** or **`APP_ENV=production`** so CORS matches the paired Cloudflare Workers URL.

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

1. Put **`GEMINI_API_KEY`** and any S3/Postgres secrets (see `backend/.env.example`) in **`backend/.env`**.
2. From the **repository root**:

```sh
docker compose build
docker compose up -d
```

3. Open **`http://localhost:8080`** (UI) — **`http://localhost:8080/api/health`** should return `{"status":"ok"}` via nginx → backend.

4. Logs: `docker compose logs -f`. Stop: `docker compose down`.

For **split deployments** (static UI on one host, API on another), build the frontend with the matching env file and set **`APP_ENV`** on the Railway backend service:

| Environment | Frontend build | Cloudflare Workers | Backend (Railway) |
|-------------|------------------|--------------------|-------------------|
| **Staging** | `npm run build:staging` | `npm run deploy:staging` → `https://kyc-automation-staging.bhanu-marreddy.workers.dev` | `APP_ENV=staging` on the staging service |
| **Production** | `npm run build:production` | `npm run deploy:production` → `https://kycautomation.bhanu-marreddy.workers.dev` | `APP_ENV=production` on the production service |

Each build bakes in the correct **`VITE_API_BASE_URL`** (`.env.staging` or `.env.production`). The backend only accepts browser requests from its paired Workers origin (plus local dev ports).

Verify after deploy: `npm run smoke:staging` or `npm run smoke:production`.

## Other deployment notes

- **Frontend (Cloudflare Workers):** Two Workers apps — production (`kyc-automation`) and staging (`kyc-automation-staging`). Use `npm run deploy:staging` or `npm run deploy:production`; do not mix builds across environments.
- **Backend (Railway):** Two services — staging and production — each with its own secrets, Postgres, and S3 bucket. Set **`APP_ENV`** to `staging` or `production` on the matching service so CORS aligns with the Workers URL. Override with **`CORS_ALLOWED_ORIGINS`** if you add custom domains.
- **Custom domains (Cloudflare):** In the Cloudflare dashboard, attach a domain to each Worker separately (e.g. `staging.example.com` → staging Worker, `app.example.com` → production Worker). Then add those origins to **`CORS_ALLOWED_ORIGINS`** on the matching Railway service.

## License / project origin

UI scaffolding may reference [Lovable](https://lovable.dev) tooling; day-to-day development is standard git + local IDE as above.
