# conftest.py — shared pytest configuration for the BTMS test suite
# No fixtures needed yet; this file ensures correct sys.path for all tests.

import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Make source modules importable in all test files
for sub in ["ai_engine", "ingestion"]:
    p = str(ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)
