"""Build pre-trained artifacts (run at deploy time):  python -m app.build_artifacts

Trains the transaction categoriser (base model, no user corrections -- those are applied at
runtime), the assistant's intent classifier, and runs the offline benchmarks, saving each to
backend/artifacts/. Takes a few seconds on a normal CPU."""
import time
from . import artifacts


def main():
    t0 = time.time()
    from .ml.categorizer import Categorizer
    cat = Categorizer()
    report = cat.train([])
    artifacts.save_joblib("categorizer", cat.pipe, {"report": report})
    print(f"categoriser: accuracy {report['accuracy']*100:.2f}%, macro F1 {report['f1_macro']:.3f} ({time.time()-t0:.1f}s)")

    t1 = time.time()
    from .assistant_engine import IntentModel
    im = IntentModel()
    artifacts.save_joblib("intent", im.pipe, {"n_examples": im.n_examples, "n_intents": im.n_intents, "n_test": im.n_test})
    print(f"intent model: {im.n_intents} intents, {im.n_examples} examples ({time.time()-t1:.1f}s)")

    t2 = time.time()
    from .ml import benchmarks
    bench = benchmarks.run_all()
    import app.ml.categorizer as C
    C.categorizer.pipe = cat.pipe                 # the CSV benchmark categorises 500 rows with this model
    from .routers.metrics import csv_benchmark
    bench["csv_500"] = csv_benchmark()
    artifacts.save_json("benchmarks", bench)
    print(f"benchmarks: MAPE {bench['forecast']['mape']}%, anomaly P/R {bench['anomaly']['precision']}/{bench['anomaly']['recall']}%, "
          f"CSV 500 rows {bench['csv_500']['ms']} ms ({time.time()-t2:.1f}s)")
    print(f"artifacts written to {artifacts.DIR} in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
