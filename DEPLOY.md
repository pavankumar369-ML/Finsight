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

## If the Render deploy fails with "Port scan timeout reached" and shows NO logs at all after "Running uvicorn..."
As of v3.7.1, the database connection now fails after 10 seconds instead of hanging forever, so this specific silent freeze shouldn't happen again — if the database is unreachable, you'll see a clear error in the logs within about 15 seconds instead of a 5-minute blank timeout. If you hit this:
1. Add `PYTHONUNBUFFERED` = `1` as an environment variable on Render, so log lines appear immediately instead of being buffered.
2. Redeploy and read the log line starting `FinSight startup: connecting to database...`. If it's followed by an error, the message will say why (wrong password, wrong host, connection refused). Copy the exact error and fix `DATABASE_URL` accordingly — usually it means the string was copied with the password hidden (`****`) or with extra spaces.
3. Confirm your Neon connection string still works by pasting it into DB Browser for SQLite... no — Neon isn't SQLite. Instead, go to Neon → your project → **Connect** → copy it fresh (with **Show password** on) and replace `DATABASE_URL` on Render.

## If the Render deploy fails with "Port scan timeout reached" (older versions, before v3.7)
This is fixed from v3.7 onward: the server opens its port immediately and trains the model in the background, so this shouldn't happen anymore. If you're deploying an older version, redeploy from the latest code. You can confirm the fix is active by checking `RENDER_URL/api/health` shortly after a deploy — it should return `"ready": false` for a few seconds, then `true`, rather than the page failing to load at all.

## Troubleshooting
| Symptom | Fix |
|---|---|
| "Can't reach the FinSight server" on first load | Render free services sleep after 15 min idle; the first request takes ~50 s. Retry. |
| Browser console shows a CORS error | `ALLOWED_ORIGINS` must match the Vercel URL exactly (https, no trailing slash). |
| Changed `VITE_API_URL` but nothing happened | Vite bakes env vars in at build time: Vercel → Deployments → **Redeploy**. |
| Refreshing `/budgets` on Vercel shows 404 | `frontend/vercel.json` must be in the repo (it rewrites all routes to `index.html`). |
| Data disappeared after a redeploy | You're on SQLite; set `DATABASE_URL` to a Neon Postgres URL. |
| Build fails on Render with a pandas/numpy error | Make sure `PYTHON_VERSION` is `3.12.8`. |
