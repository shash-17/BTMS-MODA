"""
mutation/conftest.py — sys.path setup for both pytest and mutmut runs
──────────────────────────────────────────────────────────────────────
mutmut 3.x copies test files to mutants/<test_dir>/
The source code stays in the original location (not copied).
"""
import sys
from pathlib import Path


def _find_btms_root():
    """Walk up from this file to find the BTMS root (has ai_engine/ and ingestion/)."""
    p = Path(__file__).resolve()
    for _ in range(10):
        if (p / "ai_engine").is_dir() and (p / "ingestion").is_dir():
            return p
        p = p.parent
    return None


ROOT = _find_btms_root()

if ROOT is not None:
    # ai_engine and ingestion MUST be first so 'from main import ...' picks them up
    # before auth_service/main.py (which is already in path via root conftest)
    for sub in ["ingestion", "ai_engine"]:  # insert in reverse so ai_engine ends up first
        p = str(ROOT / sub)
        # Insert at position 0 regardless of existing entries
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
