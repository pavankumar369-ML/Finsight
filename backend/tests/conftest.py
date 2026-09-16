import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["FINSIGHT_DB"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")
