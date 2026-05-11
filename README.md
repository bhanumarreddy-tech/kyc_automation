# Welcome to your Lovable project

## Project info

**URL**: https://lovable.dev/projects/8453216d-da85-44c2-a13b-70a4e59a0c31

## How can I edit this code?

There are several ways of editing your application.

**Use Lovable**

Simply visit the [Lovable Project](https://lovable.dev/projects/8453216d-da85-44c2-a13b-70a4e59a0c31) and start prompting.

Changes made via Lovable will be committed automatically to this repo.

**Use your preferred IDE**

If you want to work locally using your own IDE, you can clone this repo and push changes. Pushed changes will also be reflected in Lovable.

The only requirement is having Node.js & npm installed - [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating)

Follow these steps:

```sh
# Step 1: Clone the repository using the project's Git URL.
git clone <YOUR_GIT_URL>

# Step 2: Navigate to the project directory.
cd <YOUR_PROJECT_NAME>

# Step 3: Install the necessary dependencies.
npm i

# Step 4: Start the development server with auto-reloading and an instant preview.
npm run dev
```

**Edit a file directly in GitHub**

- Navigate to the desired file(s).
- Click the "Edit" button (pencil icon) at the top right of the file view.
- Make your changes and commit the changes.

**Use GitHub Codespaces**

- Navigate to the main page of your repository.
- Click on the "Code" button (green button) near the top right.
- Select the "Codespaces" tab.
- Click on "New codespace" to launch a new Codespace environment.
- Edit files directly within the Codespace and commit and push your changes once you're done.

## What technologies are used for this project?

This project is built with:

- Vite
- TypeScript
- React
- shadcn-ui
- Tailwind CSS

## How can I deploy this project?

Simply open [Lovable](https://lovable.dev/projects/8453216d-da85-44c2-a13b-70a4e59a0c31) and click on Share -> Publish.

### Deploying the frontend to Cloudflare Workers

The repo includes a `wrangler.jsonc` that publishes the built SPA in `dist/`
via Workers Static Assets.

1. Host the FastAPI backend (in `backend/`) somewhere that runs Python —
   Render, Railway, Fly.io, Cloud Run, etc. FastAPI **cannot** run on
   Cloudflare Workers (no native Python deps like `pillow`/`pypdf`).
2. On the backend, set `CORS_ORIGINS` to include your Workers domain,
   e.g. `https://kyc-automation.<account>.workers.dev`.
3. Edit `src/lib/api.ts` and replace the `PROD_BACKEND_URL` constant
   with the deployed backend origin (no trailing slash). The URL is
   hardcoded in source on purpose — no Cloudflare env var needed.
4. Use these commands in the Cloudflare "Create a Worker" form:
   - **Build command:** `npm run build`
   - **Deploy command:** `npx wrangler deploy`

   (We use npm + `package-lock.json` for Cloudflare. `bun.lockb` was
   removed because Cloudflare's Bun 1.2.x cannot read the old binary
   lockfile format under `--frozen-lockfile`.)

Local dev keeps using Vite's `/api` proxy to `http://localhost:8000`
automatically; the hardcoded URL is only used in production builds.

## Can I connect a custom domain to my Lovable project?

Yes, you can!

To connect a domain, navigate to Project > Settings > Domains and click Connect Domain.

Read more here: [Setting up a custom domain](https://docs.lovable.dev/features/custom-domain#custom-domain)
