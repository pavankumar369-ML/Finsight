# FinSight — AI-powered Personal Finance Management System

> Know where your money went, and where it's heading.

**Live demo:** [finsight-sigma-three.vercel.app](https://finsight-sigma-three.vercel.app/login)
&nbsp;·&nbsp;
**GitHub:** [github.com/pavankumar369-ML/Finsight](https://github.com/pavankumar369-ML/Finsight)

---
<img width="1917" height="912" alt="image" src="https://github.com/user-attachments/assets/25ac308b-8d7d-433e-912a-4ecea2ca5b42" />

---

## What it does

FinSight is a full-stack personal finance web app that analyses your Indian bank statements. Upload a CSV, Excel or PDF statement and the system:

- **Categorises every UPI/NEFT/IMPS payment** using a TF-IDF + Logistic Regression classifier trained on 4,697 real Indian bank narrations (94.68% accuracy)
- **Forecasts next month's spend per category** using Holt-Winters exponential smoothing, with a weighted-average fallback for short histories (3.63% MAPE on held-out data)
- **Flags unusual transactions** automatically with Isolation Forest (92% precision, 92% recall)
- **Answers questions in plain English** via a private NLP assistant that runs entirely on the server — no data ever leaves FinSight
- **Tracks budgets, savings goals and recurring bills** and warns you before you overspend

---

## Screenshots

<img width="1918" height="912" alt="image" src="https://github.com/user-attachments/assets/93a49b06-6dd7-42db-8701-2d7b21cc98e2" />


---

<img width="1917" height="911" alt="image" src="https://github.com/user-attachments/assets/a45ddf49-e1d9-48b2-9ed5-46ee6a7de38e" />


---

<img width="1918" height="908" alt="image" src="https://github.com/user-attachments/assets/10a4dcc7-8065-4d85-8b31-8d39c6ebada7" />


---

<img width="1918" height="911" alt="image" src="https://github.com/user-attachments/assets/9375eef8-bde6-426d-aa56-4f21550c3d3e" />


---

<img width="1918" height="911" alt="image" src="https://github.com/user-attachments/assets/da80cd25-667f-49a2-867a-b4de435cfb31" />


---

<img width="1918" height="908" alt="image" src="https://github.com/user-attachments/assets/3ee5fe8a-9602-4cfd-b771-6715de39e645" />

---

<img width="1918" height="908" alt="image" src="https://github.com/user-attachments/assets/45997dc6-3dac-4a5d-8997-bdf7cf03a1e3" />

---

## Tech stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18, Vite, Tailwind CSS, Recharts, Motion |
| **Backend** | FastAPI (Python 3.12), SQLAlchemy, JWT auth |
| **ML / NLP** | scikit-learn, statsmodels, SciPy, NumPy |
| **Database** | PostgreSQL (Neon, permanent cloud storage) |
| **Deployment** | Render (backend), Vercel (frontend) |
| **Monitoring** | UptimeRobot (always-on, 5-minute pings) |

---

## ML performance targets (all met on live system)

| Metric | Target | Measured |
|---|---|---|
| Categorisation accuracy (940 test samples) | ≥ 90% | **94.68%** |
| Categorisation macro F1 | ≥ 0.85 | **0.948** |
| Inference time per transaction | < 50 ms | **~1 ms** |
| Forecast error (MAPE, 4 held-out months) | ≤ 20% | **3.63%** |
| Anomaly precision / recall | ≥ 80% / ≥ 75% | **92% / 92%** |
| CSV import, 500 rows | < 3 s | **~20 ms** |
| Dashboard API response | < 500 ms | **~100 ms** |
| AI assistant response (local NLP) | < 5 s | **~3 ms** |

These numbers are measured live from the running system, not from a notebook. Open the **Metrics** page on the live site to see them yourself.

---

## Key features

### Statement import
- CSV, Excel (.xlsx / .xls) and **PDF** (multi-page tables, text-layout statements, password-protected)
- Every import is a batch — undo a wrong file in one click
- Duplicate detection: importing overlapping date ranges never double-counts

### AI assistant (private, no API key)
- Understands **21 question types** with a TF-IDF + Logistic Regression intent classifier (87.2% ± 4.5% accuracy, 5-fold cross-validation on unseen phrasing)
- Entity extraction: dates ("last month", "in August"), categories, merchant names, goal names
- Answers from your data, entirely on the server — zero external API calls
- Suggests follow-up questions after every answer

### Budgets and goals
- Monthly budget per category with live pacing (are you ahead or behind the calendar?)
- Savings goals with ETA based on your recent savings rate
- Daily allowance: how much can you spend today and still stay within budget?

### Metrics page (public, read-only)
- Document targets checked against live system measurements, refreshed every 2 seconds
- Admin-only controls: retrain model, run load test, view user statistics
- Retraining uses only trusted accounts (min. 10 transactions, demo account excluded, max 50 corrections per user) to prevent data poisoning

### Security
- bcrypt password hashing, stateless JWT sessions
- Admin role set by server environment variable only — no admin signup page
- Per-IP rate limiting (300 req/min general, 10 attempts / 5 min for auth)
- CORS restricted to the production Vercel domain

---

## Fast cold starts (production)
Models are **pre-trained during Render's build step** (`python -m app.build_artifacts`), so the server loads them instead of training at startup. Forecasts and ML insights are cached in the database by a fingerprint of each user's transactions and read back after a restart. The result: the server is fully ready in under 30 seconds even on Render's free 0.1-vCPU tier.

---

## Running locally

### Prerequisites
- Python 3.12, Node.js 18+

### Backend
```bash
cd backend
python -m venv venv && venv\Scripts\activate   # Windows
pip install -r requirements.txt
python -m app.build_artifacts                  # build pre-trained models once
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev                                    # http://localhost:5173
```

The backend defaults to SQLite (`finsight.db`) locally. Set `DATABASE_URL` in `backend/.env` to use PostgreSQL.

### Admin access (local)
Create `backend/.env` and set `ADMIN_EMAILS=your@email.com`, then sign up with that email. Run `python -m app.manage admins` to confirm.

---

## Deployment guide
See [DEPLOY.md](DEPLOY.md) for the full step-by-step: Neon (free Postgres) → Render (backend) → Vercel (frontend) → UptimeRobot (keep-alive).

---

## Tests (42 automated)
```bash
cd backend && python -m pytest -v
```
Covers: auth, JWT, privacy between users, CSV / Excel / PDF import (incl. password-protected PDFs), ML categorisation and insights, assistant understanding of 16 question types, admin access control, data-poisoning guard, rate limiting, HEAD requests on monitoring endpoints. Run with and without pre-built artifacts and on both SQLite and PostgreSQL.

---

## Project structure

```
finsight/
├── backend/
│   ├── app/
│   │   ├── main.py              Entry point, lifespan, middleware, rate limiting
│   │   ├── db.py                SQLAlchemy models (users, transactions, budgets, goals, …)
│   │   ├── auth.py              bcrypt + JWT, admin role
│   │   ├── assistant_engine.py  Local NLP: intent classifier, entity extraction, 21 handlers
│   │   ├── artifacts.py         Save/load pre-trained model files
│   │   ├── build_artifacts.py   Build script (runs at deploy time)
│   │   ├── statement_parser.py  CSV / Excel / PDF statement parsing
│   │   ├── seed.py              Demo account with 6 months of realistic data
│   │   ├── ml/
│   │   │   ├── categorizer.py   TF-IDF + LR transaction classifier
│   │   │   ├── analytics.py     Forecasting, anomaly detection, health score
│   │   │   ├── benchmarks.py    Offline model evaluation
│   │   │   └── ml_insights.py   K-Means clusters, linear trend detection
│   │   └── routers/             FastAPI routers (auth, transactions, analytics, metrics, …)
│   └── tests/test_api.py        42 API tests
└── frontend/
    └── src/
        ├── pages/               Overview, Transactions, Assistant, Budgets, Goals, Insights, Metrics
        └── components/          UI library, Layout, ImportCsv, ManageImports, ChangePassword, …
```

---

## Built and Developed by

**Pavan Kumar** (Pindiprolu Phani Pavan Kumar)

[GitHub](https://github.com/pavankumar369-ML) · [LinkedIn](https://www.linkedin.com/in/pindiprolu-phani-pavan-kumar-236280385)
