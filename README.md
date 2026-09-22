# FinSight — AI-powered Personal Finance Management System

**Version 3 (final).** React + FastAPI + scikit-learn. AI assistant, ML insights, CSV / Excel / PDF statement import, live user metrics. Deployable to Vercel + Render (see [DEPLOY.md](DEPLOY.md)). Imports bank statements, auto-categorises UPI/POS/NEFT transactions, forecasts next month's spending, flags unusual spends and scores financial health. A live **Metrics** page measures the running system against the targets in the project document.

## Run it locally

You need **Python 3.10+** and **Node.js 18+**.

**1. Backend** (terminal 1)
```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
First start takes a few seconds: it trains the categoriser, runs the benchmarks and creates the demo account. API docs: http://localhost:8000/docs

**2. Frontend** (terminal 2)
```bash
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173** and click **Explore with 6 months of demo data**, or sign in with `demo@finsight.app` / `demo1234`.

**3. No API keys needed**
Everything, including the AI assistant, runs locally with scikit-learn. No data is sent to any outside service.

**4. Tests**
```bash
cd backend
pytest -q
```

## Features in v1

| Area | What it does |
|---|---|
| Auth | Register / sign in with bcrypt-hashed passwords and JWT sessions; change password (key icon next to your name); one-click demo account |
| Overview | Pace meter (budget used vs month elapsed, projected month-end), spend curve vs last month, health score, cash flow, category split, recent activity, unusual spends |
| Transactions | Search and filters, live category suggestion with top-3 probabilities while typing, one-click category correction, edit/delete with undo, pagination |
| CSV import | Drag-and-drop; handles Debit/Credit columns, signed Amount, Type column, Indian date formats, duplicate detection, row errors, 5 MB limit |
| Budgets | Per-category limits, inline editing, projection that blends pace with the forecast (fixed bills handled separately), daily allowance |
| Insights | Holt-Winters forecast per category with backtest error, trend chart, 50/30/20 check, generated tips, anomaly list with reasons |
| Metrics | Document targets vs live values, request latency p50/p95/p99, throughput, status codes, per-endpoint table, in-browser load test, model accuracy/F1, confusion matrix, per-class F1, confidence histogram, retrain with user corrections, forecaster and anomaly benchmarks |
| **AI assistant (v3.2)** | Local NLP engine, no external API. A TF-IDF + Logistic Regression intent classifier (21 intents, 87.2% ± 4.5 accuracy on unseen phrasings, 5-fold cross-validation) plus entity extraction for time periods ("last month", "in August", "last 3 months"), categories, merchants and goals. Answers from the user's own data in a few milliseconds, suggests follow-up questions, and declines off-topic questions |
| **Savings goals (v2)** | Goals with emoji, target, deadline; quick add/withdraw; finish-date projection from your average monthly savings; required monthly amount for deadlines |
| **Recurring bills (v2)** | Detects subscriptions and bills (3+ months, ~monthly gap, stable amount, not everyday merchants); next due date and monthly total |
| **Notifications (v2)** | Bell with unread count: budget overruns, bills due within 7 days, unusual spends, goal milestones |
| **ML insights (v3)** | K-Means spending segments (k chosen by silhouette score) with scatter plot; trend detection by linear regression with p-values; variance decomposition of what makes months differ; weekday rhythm; interactive what-if simulator that recalculates savings and goal finish dates |
| **Smart import (v3)** | CSV, XLSX and XLS. Finds the table below bank preamble rows, maps headers like "Withdrawal Amt." or "Transaction Remarks", reads amounts like "₹1,250.00 Dr", "(500)", "Nil" and amounts in words ("two thousand five hundred", "Rs. Three lakh only"), Excel serial dates, Dr/Cr columns, and skips opening/closing balance rows. Shows which columns were detected |
| **PDF import (v3.1)** | Text-based bank e-statements across many pages; ruled tables or plain text lines; password-protected PDFs (the dialog asks for the password); clear message for scanned PDFs |
| **User metrics (v3.1)** | Metrics page shows registered, activated (imported or added data) and returning users, active now (last 5 min), active today / 7 days, sign-ins, and a 14-day chart. Aggregate counts only |
| **Production (v3)** | Postgres via `DATABASE_URL`, CORS from env, sign-in rate limiting (10 attempts / 5 min), security headers, Render blueprint, Vercel config |
| **Import management (v3.6)** | Every import is a batch: undo a wrong file in one click (right after importing, or later from **Import history**). Importing overlapping files merges them and skips duplicates. Select several rows to delete at once, or delete all transactions (type DELETE to confirm) |
| **Export (v2)** | Download the filtered transaction list as CSV |
| UI | Dark and light themes, responsive down to phones, keyboard shortcut **N** to add a transaction, reduced-motion support |

## ML components

- **Categoriser:** TF-IDF character n-grams (2–4) + Logistic Regression, trained on 4,697 labelled Indian statement descriptions across 11 categories, with 6% realistic label noise. User corrections are stored and weighted into training when you click **Retrain now**.
- **Forecaster:** Holt-Winters exponential smoothing per category on completed months, used only when a category has at least 6 months of data and isn't mostly empty. Otherwise, or if the optimiser fails to converge, a recency-weighted mean of the last 3 months is used; constant series (like fixed rent) are returned as-is. Anomalies are excluded.
- **Anomaly detector:** Isolation Forest on log amount, category, weekday and amount relative to the category median; only flags spends at least 2.5× typical, so alerts stay trustworthy.
- **Health score (0–100):** savings rate (40) + budgets on track (30) + spending stability (30).

## Measured results (v1)

| Parameter | Target | Measured |
|---|---|---|
| Categorisation accuracy (940 test samples) | ≥ 90% | 94.68% |
| Macro F1 | ≥ 0.85 | 0.948 |
| Inference per transaction | < 50 ms | ~1 ms |
| Forecast MAPE (4 held-out months) | ≤ 20% | 3.63% |
| Anomaly precision / recall | ≥ 80% / ≥ 75% | 92% / 92% |
| CSV import + categorise, 500 rows | < 3 s | ~20–60 ms |
| Dashboard API response (60-request load test) | < 500 ms | ~114 ms avg |
| AI assistant response | < 5 s | ~2–8 ms (local NLP engine) |

Exact values vary slightly by machine; the Metrics page shows the live numbers.

## Project structure
```
backend/
  app/
    main.py              app setup, timing middleware, startup training
    db.py  auth.py  schemas.py  seed.py  services.py  metrics_store.py
    ml/                  dataset, categorizer, analytics (forecast, anomalies, health), benchmarks
    routers/             auth, transactions (+CSV), analytics (dashboard, budgets, insights), metrics
    assistant_engine.py  NLP assistant: intent classifier, entity extraction, 21 answer handlers
    manage.py            admin commands: stats, reset database, reset chats
    statement_parser.py  CSV/Excel reader: header detection, column mapping, amounts in words
    ml/ml_insights.py    K-Means segments, regression trends, variance drivers, what-if base
  tests/test_api.py      41 API tests, run with and without pre-built artifacts and on PostgreSQL (incl. Metrics page readiness guard, background startup readiness, import undo and bulk delete, password change, forecast method selection, admin access control, data-poisoning guard, rate limiting, assistant intent understanding, Excel and PDF import, password PDFs, ML insights, user metrics, rate limit)
frontend/
  src/
    pages/               Login, Dashboard, Transactions, Assistant, Budgets, Goals, Insights, Metrics
    components/          UI kit, Layout, modals, toasts, CSV import, category picker
    lib/                 api client, hooks, formatting, category colours/icons
```

## Phase 1 test log

| Found in testing | Fix |
|---|---|
| Dashboard API averaged 553 ms under load (target < 500 ms); every request re-fitted ~15 Holt-Winters models | Per-user result cache invalidated on any write → 114 ms under load, 15 ms warm |
| Rent flagged "may go over" because a straight-line projection doubled a once-a-month payment | Separate projection for fixed bills (Rent, Bills, Education) |
| Forecasts inflated by one-off purchases (₹24,999 Croma) | Anomalies excluded from forecasting |
| Charts froze at a stale width on first load | `ChartBox` waits for the container size to settle before rendering |
| Stat tiles showed ₹0 until scrolled into view | Count-up animation no longer waits for visibility |
| Axis labels read "May 2026" instead of "May" | Tick formatter ignored the index argument |
| No edit/delete on mobile | Rows open the edit sheet; delete added inside it |
| Toasts rendered behind modal backdrop | Toasts moved to a portal above modals |

## Phase 2 test log

| Found in testing | Fix |
|---|---|
| Budgets, Insights and Metrics went blank when opened by clicking in the sidebar (worked after refresh; then Overview/Transactions went blank). The page transition waited for the old page's exit animation, which could stall in dev mode | Enter-only page transition plus an error boundary per page, so a page can never render blank silently. Verified by clicking through all pages 11 times on a demo and a brand-new account |
| Assistant showed ISO dates ("2026-10-05") | Friendly dates ("5 Oct") |
| Double focus ring on the chat input | Removed the inner outline |

## Phase 3 test log

| Found in testing | Fix |
|---|---|
| Bank CSVs with preamble rows lost every transaction (pandas dropped rows wider than the first line) | Rows read with `csv.reader` and padded to the widest row |
| "Value Dt" column was treated as the amount, so a "Nil" row imported as ₹4 | Amount column ignored whenever Debit/Credit columns exist; "value" removed from amount synonyms |
| "Rs. Three lakh…" not recognised (the full stop after "Rs") | Punctuation stripped before word-to-number parsing |
| ML insights crashed with "NaN is not JSON compliant" for flat category histories | Regression output sanitised; NaN/inf become null |
| Three clusters with medians ₹249/₹270/₹310 were named small/mid/large | Names now come from the feature that separates them (size, weekend share, time of month) |
| Import dialog still rejected .xlsx files | File check accepts .csv, .xlsx, .xls, .xlsm; verified by uploading an ICICI-style Excel file in the browser |
| Verified deployed topology locally: frontend built with `VITE_API_URL` on a different origin, backend CORS limited to that origin | All pages, import and API calls work cross-origin with no console errors |

## Admin access
Metrics are public in read-only form (model accuracy, benchmarks, latency, document targets), so recruiters and reviewers can see them. Controls and operational data are **admin-only**, enforced by the backend (403 for everyone else):

| Admin-only | Why |
|---|---|
| Retrain model | Prevents data poisoning and CPU abuse. Training also ignores the shared demo account and caps each user at 50 corrections |
| Run load test | Stops anyone flooding the server (all API calls are also rate-limited: 300/min per IP) |
| Users section | Operational usage data |
| Endpoint table | Internal route map |

Set admins with `ADMIN_EMAILS` (comma-separated) in `backend/.env` locally, or in Render's environment. Sign up or sign in with that email and the Metrics page shows an **Admin** badge. Check with `python -m app.manage admins`.

## Admin commands (run inside `backend`, with the server stopped)
| Command | What it does |
|---|---|
| `python -m app.manage stats` | Row count for every table |
| `python -m app.manage reset --yes` | Deletes **all** data (SQLite or Postgres) and recreates empty tables. The demo account returns on next start |
| `python -m app.manage reset-chats --yes` | Deletes only assistant chat history |
| `python -m app.manage reset-demo --yes` | Restores the shared demo account (if visitors changed or deleted its data) |
| `python -m app.manage admins` | Shows which emails have admin access |
| `python -m app.manage set-password EMAIL` | Sets a new password for an account (for forgotten passwords). Asks twice, hidden as you type |

## Build step: pre-trained models
Run `python -m app.build_artifacts` (Render does this in its build command) to train the models once and save them to `backend/artifacts/` (git-ignored, because they must be built with the same scikit-learn version that runs them). Without it, the server trains at startup instead, with identical results.

## Fast startup on slow free-tier CPUs
Training the ML model, seeding the demo account and warming caches all happen in a background task after the server has already opened its port, not before. This matters on Render's free plan (0.1 vCPU): without it, the whole sequence can take longer than Render's 5-minute port-scan timeout and the deploy fails. `GET /api/health` returns `"ready": false` for the few seconds this takes; the few endpoints that need the trained model (creating or importing a transaction, category suggestions, opening the demo account) return a friendly `503` with `Retry-After` during that window instead of erroring.

## Database upgrades are automatic
New columns (for example the user-activity fields in v3.1) are added to an existing `finsight.db` or Postgres database on startup, so existing data is kept. There's no need to delete the database when updating.

## Roadmap
- ✅ **Phase 2 (v2):** AI assistant, savings goals, recurring bills, notifications, CSV export.
- ✅ **Phase 3 (v3):** ML insights, Excel and messy-statement import, production hardening, Vercel + Render deployment.
- **Ideas beyond v3:** refresh tokens, PDF statement parsing (OCR), multi-currency, shared household budgets.
