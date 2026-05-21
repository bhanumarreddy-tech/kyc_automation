# KYC Automation

Production-oriented prototype for **Tiger Analytics KYC automation**: upload company documents and get a populated 64-question KYC questionnaire. The **FastAPI** backend runs per-section **[Google Gemini](https://ai.google.dev/)** calls—one pass for answers (with Google Search grounding) and one for document validation.

## Repository structure

```
kyc_automation/
├── src/                      # React SPA (Vite + TypeScript)
│   ├── pages/                # Route-level screens
│   ├── components/kyc/       # Domain UI (results table, processing, export)
│   ├── components/ui/        # Shared shadcn primitives (only what the app uses)
│   ├── lib/                  # API clients and analyst helpers
│   ├── data/                 # Questionnaire schema (mirrors backend)
│   └── types/                # Shared TypeScript types
├── backend/                  # FastAPI service
│   ├── app/
│   │   ├── routes/           # HTTP layer
│   │   ├── services/         # Pipeline, Gemini, documents, storage
│   │   ├── db/               # Postgres models and queries
│   │   └── config.py         # Environment and tuning
│   ├── config/               # kyc_playbook.yaml
│   └── tests/                # Pytest suite
├── scripts/                  # Deployment smoke tests
├── nginx/                    # Docker frontend reverse proxy
├── docs/                     # Design specs and analyst SOPs
├── docker-compose.yml        # Local full-stack (nginx + API)
└── .github/workflows/ci.yml  # Lint, build, and backend tests
```

| Path | Role |
|------|------|
| `src/` | React + TypeScript SPA (Vite, shadcn-ui, Tailwind) |
| `backend/` | FastAPI service — see [backend/README.md](backend/README.md) |
| `docs/` | Internal design docs and analyst SOPs (not runtime) |

## Prerequisites

- **Node.js** 20+ and npm
- **Python** 3.11+ (backend; Docker uses 3.12)

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
copy .env.example .env   # or: cp .env.example .env — then set GEMINI_API_KEY
```

Start the API (CORS defaults allow `http://localhost:8080` and `:5173`):

```sh
uvicorn app.main:app --reload --port 8000
```

Health check: `GET http://localhost:8000/api/health`

Secrets are listed in `backend/.env.example`. **`GEMINI_API_KEY`** (or **`GOOGLE_API_KEY`**) is required. Models, concurrency caps, validation limits, and CORS defaults live in **`backend/app/config.py`**.

### 2. Frontend

From the repository root:

```sh
npm install
npm run dev
```

Vite serves the app on **port 8080** and proxies `/api/*` to `http://localhost:8000`.

For remote API builds, copy `.env.example` to `.env.staging` or `.env.production` and set **`VITE_API_BASE_URL`**. These env files are gitignored; never commit deployment URLs.

## Tech stack

**Frontend:** Vite, React, TypeScript, shadcn-ui, Tailwind CSS, TanStack Query, React Router

**Backend:** FastAPI, Uvicorn, Google Gemini (`google-genai`), PyPDF, python-docx, Pillow, Pydantic, SQLAlchemy, boto3

## Quality checks

```sh
npm run lint          # frontend ESLint
npm run build         # production frontend build
cd backend && pytest  # backend unit tests
```

CI runs these on every push and pull request (`.github/workflows/ci.yml`).

## Deploy and test (Docker Compose)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose).

1. Put **`GEMINI_API_KEY`** and any S3/Postgres secrets (see `backend/.env.example`) in **`backend/.env`**.
2. From the **repository root**:

```sh
docker compose build
docker compose up -d
```

3. Open **`http://localhost:8080`** — **`http://localhost:8080/api/health`** should return `{"status":"ok"}` via nginx → backend.

For **split deployments** (static UI on Cloudflare Workers, API on Railway), build the frontend with the matching env file and set **`APP_ENV`** on the Railway backend service:

| Environment | Frontend build | Cloudflare Workers | Backend (Railway) |
|-------------|----------------|--------------------|-------------------|
| **Staging** | `npm run build:staging` | `npm run deploy:staging` | `APP_ENV=staging` |
| **Production** | `npm run build:production` | `npm run deploy:production` | `APP_ENV=production` |

Verify after deploy: `npm run smoke:staging` or `npm run smoke:production`.

## Other deployment notes

- **Frontend (Cloudflare Workers):** Use `npm run deploy:staging` or `npm run deploy:production`; do not mix builds across environments.
- **Backend (Railway):** Set **`APP_ENV`** to match the paired Workers URL. Override with **`CORS_ALLOWED_ORIGINS`** for custom domains.
- **Custom domains:** Add origins to **`CORS_ALLOWED_ORIGINS`** on the matching Railway service.

## License / project origin

UI scaffolding may reference [Lovable](https://lovable.dev) tooling; day-to-day development is standard git + local IDE as above.
