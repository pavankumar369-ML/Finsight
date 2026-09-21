"""Recomputes the assistant's intent-classification accuracy via 5-fold cross-validation.
Run this after changing TRAIN in app/assistant_engine.py, and paste the printed CV_ACCURACY
tuple back into that file. Not run at server startup -- see the note there for why."""
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import FeatureUnion, make_pipeline
from app.assistant_engine import TRAIN, _normalise_for_training

base = [(_normalise_for_training(p), intent) for intent, phrases in TRAIN.items() for p in phrases]


def augment(pairs):
    X, y = [], []
    for p, intent in pairs:
        for v in (p, "please " + p, "can you tell me " + p):
            X.append(v)
            y.append(intent)
    return X, y


def make():
    return make_pipeline(
        FeatureUnion([("w", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
                      ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True))]),
        LogisticRegression(max_iter=3000, C=8.0))


P = np.array([p for p, _ in base])
Y = np.array([i for _, i in base])
accs = []
for tr, te in StratifiedKFold(5, shuffle=True, random_state=7).split(P, Y):
    m = make().fit(*augment(list(zip(P[tr], Y[tr]))))
    accs.append(float((m.predict(P[te]) == Y[te]).mean()))
mean, std = round(float(np.mean(accs)) * 100, 1), round(float(np.std(accs)) * 100, 1)
print(f"CV_ACCURACY = ({mean}, {std})")
