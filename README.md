# FinSight — AI-powered Personal Finance Management System

**Version 2 (Phase 2).** React + FastAPI + scikit-learn, with an AI finance assistant. Imports bank statements, auto-categorises UPI/POS/NEFT transactions, forecasts next month's spending, flags unusual spends and scores financial health. A live **Metrics** page measures the running system against the targets in the project document.

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

**3. Optional: connect a real LLM to the assistant**
The assistant works out of the box in offline mode (answers computed from your data). For open-ended conversation, copy `backend/.env.example` to `backend/.env`, paste a free API key (Groq or Gemini), and restart the backend. The Assistant page then shows the model name, and the Metrics page measures real LLM response time.

**4. Tests**
```bash
cd backend
pytest -q
```

## Features in v1

| Area | What it does |
|---|---|
| Auth | Register / sign in with bcrypt-hashed passwords and JWT sessions; one-click demo account |
| Overview | Pace meter (budget used vs month elapsed, projected month-end), spend curve vs last month, health score, cash flow, category split, recent activity, unusual spends |
| Transactions | Search and filters, live category suggestion with top-3 probabilities while typing, one-click category correction, edit/delete with undo, pagination |
| CSV import | Drag-and-drop; handles Debit/Credit columns, signed Amount, Type column, Indian date formats, duplicate detection, row errors, 5 MB limit |
| Budgets | Per-category limits, inline editing, projection that blends pace with the forecast (fixed bills handled separately), daily allowance |
| Insights | Holt-Winters forecast per category with backtest error, trend chart, 50/30/20 check, generated tips, anomaly list with reasons |
| Metrics | Document targets vs live values, request latency p50/p95/p99, throughput, status codes, per-endpoint table, in-browser load test, model accuracy/F1, confusion matrix, per-class F1, confidence histogram, retrain with user corrections, forecaster and anomaly benchmarks |
| **AI assistant (v2)** | Chat grounded in your own data (months, categories, budgets, goals, forecast, bills, anomalies). Uses any OpenAI-compatible LLM (Groq, Gemini, OpenAI); falls back to a built-in offline engine if no key is set or the API fails. Every reply is timed |
| **Savings goals (v2)** | Goals with emoji, target, deadline; quick add/withdraw; finish-date projection from your average monthly savings; required monthly amount for deadlines |
| **Recurring bills (v2)** | Detects subscriptions and bills (3+ months, ~monthly gap, stable amount, not everyday merchants); next due date and monthly total |
| **Notifications (v2)** | Bell with unread count: budget overruns, bills due within 7 days, unusual spends, goal milestones |
| **Export (v2)** | Download the filtered transaction list as CSV |
| UI | Dark and light themes, responsive down to phones, keyboard shortcut **N** to add a transaction, reduced-motion support |

## ML components

- **Categoriser:** TF-IDF character n-grams (2–4) + Logistic Regression, trained on 4,697 labelled Indian statement descriptions across 11 categories, with 6% realistic label noise. User corrections are stored and weighted into training when you click **Retrain now**.
- **Forecaster:** Holt-Winters exponential smoothing per category on completed months; anomalies excluded; mean fallback for short histories.
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
| AI assistant response | < 5 s | Offline engine < 1 ms; LLM mode measured live on the Metrics page |

Exact values vary slightly by machine; the Metrics page shows the live numbers.

## Project structure
```
backend/
  app/
    main.py              app setup, timing middleware, startup training
    db.py  auth.py  schemas.py  seed.py  services.py  metrics_store.py
    ml/                  dataset, categorizer, analytics (forecast, anomalies, health), benchmarks
    routers/             auth, transactions (+CSV), analytics (dashboard, budgets, insights), metrics
    assistant.py         LLM client, data context builder, offline answer engine
  tests/test_api.py      21 API tests (incl. mocked LLM and LLM-failure fallback)
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

## Roadmap
- ✅ **Phase 2 (v2):** AI assistant, savings goals, recurring bills, notifications, CSV export.
- **Next:** deployment, auth hardening (refresh tokens, rate limiting), Postgres option, performance and accessibility audit, mobile polish.
