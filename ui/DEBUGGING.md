# Debugging the chat on Vercel

## Why the chat doesn’t work on Vercel (only UI deployed)

The chat UI calls `/chatkit` (bootstrap, messages, etc.). Next.js rewrites those requests to a **backend URL**. By default that URL is `http://127.0.0.1:8000` (your local Python backend). On Vercel there is no process listening on that address, so every `/chatkit` request fails and the chat never works.

## How to confirm

1. Open your Vercel app URL in the browser.
2. Open **Developer Tools** (F12 or right‑click → Inspect).
3. Go to the **Console** tab: look for errors mentioning `chatkit`, `bootstrap`, or network failures.
4. Go to the **Network** tab, then submit the lead form and try to use the chat. Look for requests to `/chatkit` or `/chatkit/bootstrap`:
   - **Status 502 / 504 / (failed)** → request was proxied to a backend that isn’t there or isn’t reachable.
   - **Status 200** → backend is reachable; if the chat still doesn’t work, the issue is elsewhere (e.g. ChatKit domain key or backend logic).

If you see failed `/chatkit` requests, the fix is to deploy the Python backend and point the UI at it (see below).

## Fix: deploy the backend and set the backend URL

1. Deploy the **Python backend** (FastAPI in `python-backend/`) to a host that gives you a public URL, e.g.:
   - [Railway](https://railway.app)
   - [Render](https://render.com)
   - [Fly.io](https://fly.io)
   - Any VPS or cloud VM where you run `uvicorn main:app --host 0.0.0.0 --port 8000`
2. On that host, set **`OPENAI_API_KEY`** (and any other env vars the backend needs).
3. In **Vercel** (project → Settings → Environment Variables), add:
   - **Name:** `BACKEND_URL`  
   - **Value:** your backend URL, e.g. `https://your-backend.railway.app` (no trailing slash)
4. **Redeploy** the Vercel project (Deployments → Redeploy, or push a new commit).

The Next.js app uses `BACKEND_URL` (or `NEXT_PUBLIC_BACKEND_URL`) in `next.config.mjs` to rewrite `/chat` and `/chatkit` to your deployed backend. Once that’s set and redeployed, the chat should work.

## Optional: ChatKit domain key in production

If you use a production ChatKit domain key, set in Vercel:

- **`NEXT_PUBLIC_CHATKIT_DOMAIN_KEY`** = your production domain key

Otherwise the app falls back to `domain_pk_localhost_dev`, which may only be valid for localhost.
