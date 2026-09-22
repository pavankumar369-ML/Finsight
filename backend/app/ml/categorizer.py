"""TF-IDF + Logistic Regression transaction categoriser that retrains with user corrections."""
import json, re, time, threading
import numpy as np
from . import dataset

# scikit-learn is imported inside train() rather than at module level: importing it is itself
# a slow step under a throttled CPU (e.g. Render's free tier), and this module is imported as
# part of the app's startup chain, so a module-level import would block the server from opening
# its port. Nothing else in this file needs it (predict() only calls methods on an already-fitted
# pipeline object).


def clean(text: str) -> str:
    t = text.lower()
    t = re.sub(r"\d{3,}", " ", t)          # drop reference numbers
    t = re.sub(r"[^a-z ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


class Categorizer:
    def __init__(self):
        self.pipe = None
        self.labels = dataset.EXPENSE_CATEGORIES
        self.last_report = None
        self._lock = threading.Lock()

    def load(self, pipe, report):
        """Install a pre-trained pipeline (see app/artifacts.py) instead of training at startup."""
        with self._lock:
            self.pipe = pipe
        self.last_report = report
        return report

    def train(self, corrections=None):
        """corrections: list of (description, category) from users. Returns a metrics report dict."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
        from sklearn.pipeline import make_pipeline
        rows = dataset.generate()
        corrections = corrections or []
        X = [clean(d) for d, _ in rows]
        y = [c for _, c in rows]
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
        # user corrections always go into training, weighted up so the model actually adapts to them
        for d, c in corrections:
            if c in self.labels:
                X_tr.extend([clean(d)] * 5)
                y_tr.extend([c] * 5)
        t0 = time.perf_counter()
        pipe = make_pipeline(
            TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=2, sublinear_tf=True),
            LogisticRegression(max_iter=2000, C=4.0),
        )
        pipe.fit(X_tr, y_tr)
        train_ms = (time.perf_counter() - t0) * 1000
        pred = pipe.predict(X_te)
        per_class = f1_score(y_te, pred, labels=self.labels, average=None)
        cm = confusion_matrix(y_te, pred, labels=self.labels)
        with self._lock:
            self.pipe = pipe
        self.last_report = {
            "n_train": len(X_tr), "n_test": len(X_te), "n_corrections": len(corrections),
            "accuracy": float(accuracy_score(y_te, pred)),
            "f1_macro": float(f1_score(y_te, pred, average="macro")),
            "train_ms": train_ms,
            "details": json.dumps({"labels": self.labels,
                                   "per_class_f1": [round(float(v), 4) for v in per_class],
                                   "confusion": cm.tolist()}),
        }
        return self.last_report

    def predict(self, descriptions):
        """Returns list of (category, confidence, top3[(cat, p)])."""
        with self._lock:
            pipe = self.pipe
        probs = pipe.predict_proba([clean(d) for d in descriptions])
        classes = pipe.classes_
        out = []
        for p in probs:
            order = np.argsort(p)[::-1][:3]
            out.append((str(classes[order[0]]), float(p[order[0]]),
                        [(str(classes[i]), round(float(p[i]), 4)) for i in order]))
        return out


categorizer = Categorizer()
