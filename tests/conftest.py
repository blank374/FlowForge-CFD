"""Keep module startup and regression tests away from real engineering runs."""
import os
import tempfile
import atexit
_test_data = tempfile.TemporaryDirectory(prefix='flowforge-tests-', ignore_cleanup_errors=True)
os.environ['FLOWFORGE_DATA_DIR'] = _test_data.name
atexit.register(_test_data.cleanup)
