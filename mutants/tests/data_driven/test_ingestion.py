"""
test_ingestion.py  — Data-Driven Tests for BTMS Ingestion Service
─────────────────────────────────────────────────────────────────────
Reads ingestion_cases.csv and parametrises pytest over temperature
normalisation and payload enrichment logic.  No Redis connection needed.

Run:
    pytest tests/data_driven/test_ingestion.py -v
"""

import csv
import math
import os
import sys
from pathlib import Path

import pytest

# ── Source imports ─────────────────────────────────────────────────────────────
ROOT      = Path(__file__).resolve().parents[2]
INGESTION = ROOT / "ingestion"
sys.path.insert(0, str(INGESTION))

from app import normalise_temperature, enrich_payload, TEMP_MIN, TEMP_MAX

DATASET = Path(__file__).parent / "datasets" / "ingestion_cases.csv"


# ═══════════════════════════════════════════════════════════════════════════════
# Load parametrised cases
# ═══════════════════════════════════════════════════════════════════════════════

def _load_ingestion_cases():
    params = []
    with open(DATASET, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            params.append(
                pytest.param(
                    row["test_id"],
                    float(row["raw_temp"]),
                    float(row["expected_norm"]),
                    float(row["clamp_expected"]),
                    id=f"{row['test_id']}::{row['description'][:40]}",
                )
            )
    return params


# ═══════════════════════════════════════════════════════════════════════════════
# Data-Driven: normalise_temperature
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "test_id,raw_temp,expected_norm,clamp_expected",
    _load_ingestion_cases(),
)
def test_normalisation_formula(test_id, raw_temp, expected_norm, clamp_expected):
    """[DDT] normalise_temperature applies min-max formula correctly."""
    result = normalise_temperature(raw_temp)
    assert abs(result - expected_norm) < 1e-4, (
        f"[{test_id}] T={raw_temp}°C → norm={result:.6f}, expected {expected_norm:.6f}"
    )


@pytest.mark.parametrize(
    "raw_temp",
    [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0],
    ids=[f"T={t}" for t in [0,5,10,15,20,25,30,35,40,45,50,55,60]],
)
def test_normalisation_always_in_unit_range(raw_temp):
    """[DDT] All temperatures in [TEMP_MIN, TEMP_MAX] must normalise to [0, 1]."""
    result = normalise_temperature(raw_temp)
    assert 0.0 <= result <= 1.0, (
        f"T={raw_temp}°C → norm={result:.6f} outside [0, 1]"
    )


@pytest.mark.parametrize(
    "raw_temp",
    [22.5, 38.4, 1.7, 59.1, 47.3],
    ids=["22.5", "38.4", "1.7", "59.1", "47.3"],
)
def test_normalisation_reversible(raw_temp):
    """[DDT] Normalisation must be reversible: de-normalised value matches original."""
    norm = normalise_temperature(raw_temp)
    recovered = norm * (TEMP_MAX - TEMP_MIN) + TEMP_MIN
    assert abs(recovered - raw_temp) < 1e-3, (
        f"T={raw_temp} → norm={norm:.6f} → recovered={recovered:.4f}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Data-Driven: enrich_payload
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "num_cells,temp",
    [(10, 28.0), (5, 35.0), (1, 45.0), (10, 55.0)],
    ids=["10cells@28", "5cells@35", "1cell@45", "10cells@55"],
)
def test_enrich_adds_temperature_norm_to_all_cells(num_cells, temp):
    """[DDT] enrich_payload must add 'temperature_norm' to every cell."""
    payload = {
        "tick": 1,
        "cells": [
            {"cell_id": i, "temperature": temp, "voltage": 3.6, "current": 2.5, "soc": 90.0}
            for i in range(num_cells)
        ],
    }
    enriched = enrich_payload(payload)
    for cell in enriched["cells"]:
        assert "temperature_norm" in cell, (
            f"Cell {cell['cell_id']} missing 'temperature_norm'"
        )


@pytest.mark.parametrize(
    "temp",
    [0.0, 15.0, 30.0, 45.0, 60.0],
    ids=["0C", "15C", "30C", "45C", "60C"],
)
def test_enrich_norm_value_matches_formula(temp):
    """[DDT] The norm value written by enrich_payload must match normalise_temperature."""
    payload = {
        "tick": 1,
        "cells": [{"cell_id": 0, "temperature": temp, "voltage": 3.6, "current": 2.5, "soc": 90.0}],
    }
    enriched = enrich_payload(payload)
    cell_norm = enriched["cells"][0]["temperature_norm"]
    expected  = normalise_temperature(temp)
    assert abs(cell_norm - expected) < 1e-6, (
        f"T={temp}°C — enrich wrote {cell_norm} but formula gives {expected}"
    )


@pytest.mark.parametrize(
    "tick,num_cells",
    [(0, 10), (100, 5), (9999, 1)],
    ids=["tick=0", "tick=100", "tick=9999"],
)
def test_enrich_preserves_other_fields(tick, num_cells):
    """[DDT] enrich_payload must not mutate or drop existing fields."""
    payload = {
        "tick":     tick,
        "pack_id":  "BTMS-PACK-001",
        "cells": [
            {"cell_id": i, "temperature": 30.0, "voltage": 3.6, "current": 2.5, "soc": 90.0}
            for i in range(num_cells)
        ],
    }
    enriched = enrich_payload(payload)
    assert enriched["tick"]    == tick
    assert enriched["pack_id"] == "BTMS-PACK-001"
    assert len(enriched["cells"]) == num_cells
    for cell in enriched["cells"]:
        assert cell["voltage"]  == 3.6
        assert cell["current"]  == 2.5
        assert cell["soc"]      == 90.0


@pytest.mark.parametrize(
    "temps",
    [
        [28.0, 30.0, 32.0, 35.0, 38.0, 40.0, 42.0, 44.0, 46.0, 50.0],
        [22.0] * 10,
        [46.0, 46.0, 46.0, 46.0, 46.0, 46.0, 46.0, 46.0, 46.0, 46.0],
    ],
    ids=["gradient", "uniform-cold", "uniform-spike"],
)
def test_enrich_all_norms_are_finite(temps):
    """[DDT] All normalised values in an enriched payload must be finite numbers."""
    payload = {
        "tick": 1,
        "cells": [
            {"cell_id": i, "temperature": t, "voltage": 3.6, "current": 2.5, "soc": 90.0}
            for i, t in enumerate(temps)
        ],
    }
    enriched = enrich_payload(payload)
    for cell in enriched["cells"]:
        norm = cell["temperature_norm"]
        assert math.isfinite(norm), f"Cell {cell['cell_id']} norm={norm} is not finite"


# ═══════════════════════════════════════════════════════════════════════════════
# Boundary & edge-case Data-Driven tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "test_id,raw_temp,expected_norm,clamp_expected",
    _load_ingestion_cases(),
)
def test_normalisation_matches_manual_formula(test_id, raw_temp, expected_norm, clamp_expected):
    """[DDT] Cross-verify against inline formula calculation."""
    manual = round((raw_temp - TEMP_MIN) / (TEMP_MAX - TEMP_MIN), 6)
    result = normalise_temperature(raw_temp)
    assert abs(result - manual) < 1e-6, (
        f"[{test_id}] Implementation result={result:.6f} differs from manual={manual:.6f}"
    )
