import os
import tempfile

# Point the app at a throwaway data directory BEFORE app modules are imported.
_tmp = tempfile.mkdtemp(prefix="urtiscan-test-")
os.environ["URTISCAN_DATA_DIR"] = _tmp
os.environ["URTISCAN_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
