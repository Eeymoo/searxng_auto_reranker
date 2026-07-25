"""Pytest config: expose the plugin package to tests."""

import sys
import pathlib

# tests/ is at <repo>/tests/conftest.py -> parents[1] is repo root.
ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "searx" / "plugins"
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))
