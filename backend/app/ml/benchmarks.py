"""Reproducible offline benchmarks for the forecaster and anomaly detector (shown on the Metrics page).
Uses the same seed and call order as the prototype evaluation reported in the project document."""
import time
import numpy as np
# sklearn/statsmodels imported inside run_all() -- see the note in categorizer.py


def run_all():
    import pandas as pd
    from sklearn.ensemble import IsolationForest
    from sklearn.metrics import precision_score, recall_score
    np.random.seed(42)
    n = 36
    idx = pd.date_range("2022-01-01", periods=n, freq="MS")
    series = pd.Series(8000 + np.linspace(0, 3000, n) + 1200 * np.sin(np.linspace(0, 6 * np.pi, n))
                       + np.random.normal(0, 400, n), index=idx).clip(lower=1000)
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    t0 = time.perf_counter()
    import warnings
    from statsmodels.tools.sm_exceptions import ConvergenceWarning
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        fit = ExponentialSmoothing(series[:-4], trend="add", seasonal="add", seasonal_periods=12).fit()
    fc = fit.forecast(4)
    f_ms = (time.perf_counter() - t0) * 1000
    mape = float(np.mean(np.abs((series[-4:].values - fc.values) / series[-4:].values)) * 100)

    normal = np.random.gamma(3, 250, 950)
    anomalies = np.random.uniform(1800, 12000, 50)
    X = np.concatenate([normal, anomalies]).reshape(-1, 1)
    y = np.array([0] * 950 + [1] * 50)
    perm = np.random.permutation(len(X))
    X, y = X[perm], y[perm]
    t0 = time.perf_counter()
    pred = (IsolationForest(contamination=0.05, random_state=42).fit(X).predict(X) == -1).astype(int)
    a_ms = (time.perf_counter() - t0) * 1000
    return {
        "forecast": {"mape": round(mape, 2), "fit_ms": round(f_ms, 1), "months": n, "held_out": 4,
                     "labels": [d.strftime("%b %Y") for d in series.index[-4:]],
                     "actual": [round(float(v)) for v in series[-4:].values],
                     "predicted": [round(float(v)) for v in fc.values]},
        "anomaly": {"precision": round(precision_score(y, pred) * 100, 2), "recall": round(recall_score(y, pred) * 100, 2),
                    "fit_ms": round(a_ms, 1), "samples": len(X), "injected": 50},
    }
