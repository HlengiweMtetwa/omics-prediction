"""Ensures the repository root is on sys.path regardless of how pytest is
invoked. `python -m pytest` adds the CWD to sys.path automatically; the
bare `pytest` console script (as CI runs it) does not, which otherwise
breaks every `from ai_wasteguard import ...` / `from api import ...`
import in tests/ - not a hypothetical, this is what actually failed in CI
(see .github/workflows/python-package.yml run history).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
