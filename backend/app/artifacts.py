"""Pre-trained model artifacts, built once at deploy time instead of at every server start.

Why: on a throttled free-tier CPU, training the categoriser and the assistant's intent classifier
(and re-running the offline benchmarks) at startup took minutes. The trained objects are
deterministic (fixed data + fixed random seeds), so they can be built once during the platform's
build step -- which runs on a fast machine -- and simply loaded at runtime.

Build:   python -m app.build_artifacts      (Render build command runs this after pip install)
Runtime: load_* functions below return None if an artifact is missing or was built with a
         different scikit-learn version; callers then fall back to training, exactly as before.
"""
import json, os

DIR = os.getenv("FINSIGHT_ARTIFACTS") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts")
FILES = {"categorizer": "categorizer.joblib", "intent": "intent.joblib", "benchmarks": "benchmarks.json"}


def path(name):
    return os.path.join(DIR, FILES[name])


def _sklearn_version():
    import sklearn
    return sklearn.__version__


def save_joblib(name, obj, meta):
    import joblib
    os.makedirs(DIR, exist_ok=True)
    joblib.dump({"obj": obj, "meta": {**meta, "sklearn": _sklearn_version()}}, path(name), compress=3)


def load_joblib(name):
    """Returns (obj, meta) or None. Rejects artifacts pickled by a different scikit-learn version,
    because unpickling across versions can silently change behaviour."""
    p = path(name)
    if not os.path.exists(p):
        return None
    try:
        import joblib
        data = joblib.load(p)
        if data["meta"].get("sklearn") != _sklearn_version():
            return None
        return data["obj"], data["meta"]
    except Exception:
        return None


def save_json(name, value):
    os.makedirs(DIR, exist_ok=True)
    with open(path(name), "w", encoding="utf-8") as f:
        json.dump(value, f)


def load_json(name):
    try:
        with open(path(name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
