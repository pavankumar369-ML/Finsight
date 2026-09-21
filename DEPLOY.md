# Deploying FinSight: Render (backend) + Vercel (frontend)

Order matters: deploy the **backend first**, because the frontend needs its URL.

## 0. Push the latest code to GitHub
```bash
git add .
git commit -m "FinSight v3"
git push
```

## 1. Free Postgres database on Neon (needed so users keep their data)
Render's free plan has no persistent disk, so SQLite **loses all data on every redeploy or restart** (Render also restarts sleeping free services). Neon's free Postgres keeps every user's data permanently, and FinSight needs no code changes for it:
1. Sign up at https://neon.tech → **Create project** (region: Singapore / closest to you).
2. Copy the **connection string** (starts with `postgresql://...`). You'll paste it as `DATABASE_URL` in step 2.

Skip this only if you want a throwaway demo; the demo account is recreated on each start, but real users' data would vanish.

Why not Firebase? FinSight's backend uses SQL through SQLAlchemy. Firebase is a NoSQL store and would need every query rewritten. Postgres gives the same result (permanent, per-user data) with one environment variable.

## 2. Backend on Render
1. https://render.com → sign in with GitHub → **New +** → **Web Service** → pick the `Finsight` repo.
2. Settings:
   | Field | Value |
   |---|---|
   | Root Directory | `backend` |
   | Runtime | Python 3 |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
   | Instance type | Free |
3. **Environment variables** (Advanced → Add Environment Variable):
   | Key | Value |
   |---|---|
   | `PYTHON_VERSION` | `3.12.8` |
   | `FINSIGHT_SECRET` | any long random string (e.g. from https://generate-secret.vercel.app/64) |
   | `ALLOWED_ORIGINS` | your Vercel URL, filled in after step 3 (e.g. `https://finsight-pavan.vercel.app`) |
   | `ALLOWED_ORIGIN_REGEX` | `https://.*\.vercel\.app` |
   | `ADMIN_EMAILS` | your email, e.g. `pppk132006@gmail.com` (gives you the admin view of Metrics) |
   | `DATABASE_URL` | Neon connection string (optional, see step 1) |
4. **Create Web Service**. First build takes ~5 minutes. When it's live, open `https://<your-service>.onrender.com/api/health`; you should see `{"ok": true, ...}`.

Alternative: **New + → Blueprint** uses `render.yaml` from the repo and pre-fills all of the above.

## 3. Frontend on Vercel
1. https://vercel.com → sign in with GitHub → **Add New… → Project** → import `Finsight`.
2. **Root Directory**: click Edit → choose `frontend`. Framework preset: **Vite** (auto-detected).
3. **Environment Variables**: `VITE_API_URL` = `https://<your-service>.onrender.com` (no trailing slash, no `/api`).
4. **Deploy**. You get a URL like `https://finsight-pavan.vercel.app`.

## 4. Connect them
1. Back in Render → your service → **Environment** → set `ALLOWED_ORIGINS` to the exact Vercel URL → **Save** (it redeploys).
2. Open the Vercel URL → **Explore with 6 months of demo data**.

## Clearing all data on the live site
From your laptop, point the reset command at the Neon database once (PowerShell):
`$env:DATABASE_URL="<your Neon connection string>"; python -m app.manage reset --yes`
Or in Neon's dashboard: **Branches → Reset from parent**, or run `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` in the SQL Editor, then restart the Render service.

## Troubleshooting
| Symptom | Fix |
|---|---|
| "Can't reach the FinSight server" on first load | Render free services sleep after 15 min idle; the first request takes ~50 s. Retry. |
| Browser console shows a CORS error | `ALLOWED_ORIGINS` must match the Vercel URL exactly (https, no trailing slash). |
| Changed `VITE_API_URL` but nothing happened | Vite bakes env vars in at build time: Vercel → Deployments → **Redeploy**. |
| Refreshing `/budgets` on Vercel shows 404 | `frontend/vercel.json` must be in the repo (it rewrites all routes to `index.html`). |
| Data disappeared after a redeploy | You're on SQLite; set `DATABASE_URL` to a Neon Postgres URL. |
| Build fails on Render with a pandas/numpy error | Make sure `PYTHON_VERSION` is `3.12.8`. |
