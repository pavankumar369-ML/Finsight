import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["FINSIGHT_DB"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["ADMIN_EMAILS"] = "boss@example.com"
os.environ["API_RATE_LIMIT"] = "100000"
