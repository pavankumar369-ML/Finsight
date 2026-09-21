import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["FINSIGHT_DB"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["ADMIN_EMAILS"] = "boss@example.com"
os.environ["API_RATE_LIMIT"] = "100000"


import time as _time
import urllib.request as _u
def _wait_ready(client):
    for _ in range(200):
        if client.get("/api/health").json().get("ready"):
            return
        _time.sleep(0.05)
    raise RuntimeError("app did not become ready in time")
