"""Run Guard test package."""

import sys
import atexit
import shutil
from pathlib import Path


# Python 3.13 unittest discovery imports this subpackage as a top-level module
# when `discover -s tests` is used, so this marker (not tests/__init__.py) is
# the reliable hook to stop the test run from writing bytecode caches.
sys.dont_write_bytecode = True

# The first package imported by discovery writes its own __init__ bytecode
# before the guard above takes effect. A scoped cleanup at interpreter exit
# guarantees the observable contract: `python -m unittest discover -s tests`
# never leaves __pycache__/pyc behind in the workspace.
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def _remove_workspace_bytecode_caches() -> None:
    for cache in list(_WORKSPACE_ROOT.rglob("__pycache__")):
        try:
            shutil.rmtree(cache)
        except OSError:
            pass


atexit.register(_remove_workspace_bytecode_caches)
