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
   | Build Command | `pip install -r requirements.txt && python -m app.build_artifacts` |
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

## If UptimeRobot (or any monitor) shows the site as "Down" with a 405 error (fixed in v3.8.1)
Monitoring tools check with a `HEAD` request instead of the `GET` your browser sends. FastAPI's `@app.get()` doesn't answer `HEAD` automatically, so `/api/health` and `/` returned 405 to monitors even though the site was fully working in a browser -- this is what caused the earlier "HEAD / 405" lines in the Render logs, and it's now fixed for both routes.

## Fast cold starts (v3.8)
Render's free tier sleeps after 15 minutes and runs on a very slow shared CPU. v3.8 makes waking up fast:
- **Models are trained during the build, not at startup.** The build command runs `python -m app.build_artifacts`, which trains the categoriser and the assistant's classifier and runs the benchmarks on Render's fast build machine (about 3 seconds), saving them to `backend/artifacts/`. The server only loads them. Same data and random seeds, so identical accuracy (94.68%, F1 0.948, 87.2% intent, MAPE 3.63%, anomaly 92/92%).
- **Forecasts and ML insights are stored in the database** (`analytics_cache` table), keyed by a fingerprint of each user's transactions. After a restart they're read back instead of recomputed; any change to the data recomputes them automatically.
- **No pandas, scikit-learn, statsmodels or scipy at startup.** The dashboard's totals are plain Python (verified identical to the previous pandas version), and the ML libraries load in the background.
- **The demo login no longer waits for the models**, since the demo account already exists in the database.

If you skip the new build command, everything still works: the server trains at startup like before, just slower.

## If the Metrics page shows "This page hit an error" right after a cold start (fixed in v3.7.5)
The Metrics page used to assume the model-quality data was fully loaded as soon as it got a response, but during the few seconds the background warm-up is still running, that response is empty. From v3.7.5 the page shows a clean "Warming up the models…" message (auto-refreshing) instead, and switches to the normal view the moment it's ready -- no refresh needed.

## If `/api/health` stays `"ready": false` for a long time (improved in v3.7.4)
The AI assistant used to measure its own accuracy by training itself 6 separate times (a 5-fold cross-validation) on every single server start, even though that number never changes. From v3.7.4 it trains once, using a precomputed accuracy figure, cutting a meaningful chunk of the background warm-up time -- especially valuable on Render's slow free CPU. If it's still slow after updating, that's just genuine free-tier CPU speed: the app is fully usable while `"ready": false` (only a few ML-dependent actions like adding a transaction politely ask you to wait a few seconds), and it does finish -- give it a few minutes on the very first request after a cold start.

## If Render shows "unsupported startup parameter in options: statement_timeout" (fixed in v3.7.3)
This was a bug in FinSight's own v3.7.1 database-timeout setting, not something you did wrong: it tried to set a `statement_timeout` connection option that Neon's **pooled** connection endpoint (hostname containing `-pooler`) rejects outright. Removed in v3.7.3. If you still see this on an older version, either update to v3.7.3, or as a workaround use Neon's **unpooled** connection string instead (Neon → Connect → toggle off "Pooled connection").

## Why the free-tier deploy could time out (fixed in v3.7.2)
Several files imported scikit-learn, scipy and statsmodels at the top of the file, and the AI assistant's classifier used to train itself the instant its file was imported — all of this happened automatically the moment the server started, before it could open its port. On Render's free 0.1-vCPU instance, that was slow enough to exceed Render's 5-minute port-scan timeout, and because Python hadn't reached any of FinSight's own code yet, nothing appeared in the logs to explain why. From v3.7.2, every heavy import is deferred to actually being used, and the AI assistant trains itself in the background after the server is already accepting requests — verified to open the port in under 10 seconds even under a simulated 10%-CPU throttle.

## If the Render deploy still fails with "Port scan timeout reached" and shows NO logs at all after "Running uvicorn..."
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
