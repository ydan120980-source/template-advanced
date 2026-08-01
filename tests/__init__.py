"""Test package marker so unittest discovery from the tests root works."""

import sys


# The suite must pass even when the caller did not set
# PYTHONDONTWRITEBYTECODE or pass -B. Setting this flag before any project
# module is imported means the unittest run itself never writes bytecode
# caches into the workspace, so the workspace stays a clean release tree.
sys.dont_write_bytecode = True
