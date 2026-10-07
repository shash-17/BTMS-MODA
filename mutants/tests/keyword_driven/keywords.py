"""
keywords.py  — Keyword-Driven Testing (KDT) action library for BTMS
─────────────────────────────────────────────────────────────────────
Each keyword is a plain Python function.  The runner maps keyword
strings (from the CSV test suite) to these functions at runtime.

Keyword signature convention:
    keyword_func(*args) -> (passed: bool, detail: str)
"""

import math
import json
import sys
import os

# ── Make source modules importable without installing ─────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AI_ENGINE = os.path.join(ROOT, "ai_engine")
INGESTION  = os.path.join(ROOT, "ingestion")
sys.path.insert(0, AI_ENGINE)
sys.path.insert(0, INGESTION)

from main import (              # ai_engine/main.py
    nanofluid_properties,
    compute_flow_velocity,
    compute_nusselt,
    cfd_optimise,
    CONC_TABLE,
    RE_MIN, RE_MAX,
    TEMP_CRITICAL,
)
from app import (               # ingestion/app.py
    normalise_temperature,
    enrich_payload,
)


# ═══════════════════════════════════════════════════════════════════════════════
# CFD / AI-Engine Keywords
# ═══════════════════════════════════════════════════════════════════════════════

def keyword_nanofluid_density_in_range(phi_str: str, expected_min: str, expected_max: str):
    """
    VERIFY NANOFLUID DENSITY IN RANGE
    Checks that ρ_nf for volume fraction φ falls within [expected_min, expected_max].
    """
    phi = float(phi_str)
    lo, hi = float(expected_min), float(expected_max)
    props = nanofluid_properties(phi)
    rho = props["rho"]
    passed = lo <= rho <= hi
    detail = f"φ={phi*100:.1f}% → ρ_nf={rho:.2f} kg/m³  (expected [{lo}, {hi}])"
    return passed, detail


def keyword_flow_velocity_positive(phi_str: str, re_target_str: str):
    """
    VERIFY FLOW VELOCITY POSITIVE
    Flow velocity computed from Re target must be > 0.
    """
    phi = float(phi_str)
    re  = float(re_target_str)
    props = nanofluid_properties(phi)
    v = compute_flow_velocity(re, props)
    passed = v > 0
    detail = f"Re={re}, φ={phi*100:.1f}% → v={v:.6f} m/s"
    return passed, detail


def keyword_nusselt_number_minimum(re_str: str, pr_str: str, min_nu: str):
    """
    VERIFY NUSSELT NUMBER MINIMUM
    Nu must exceed the Nusselt floor (3.66 for fully-developed laminar).
    """
    re = float(re_str)
    pr = float(pr_str)
    nu_floor = float(min_nu)
    nu = compute_nusselt(re, pr)
    passed = nu >= nu_floor
    detail = f"Re={re}, Pr={pr} → Nu={nu:.3f}  (min {nu_floor})"
    return passed, detail


def keyword_cfd_severity_normal(temp_str: str):
    """
    VERIFY CFD SEVERITY NORMAL
    For a uniform pack where all cells are below the warning threshold the
    severity must be 'normal'.
    """
    temp = float(temp_str)
    cells = [{"cell_id": i, "temperature": temp, "voltage": 3.6, "current": 2.5,
              "soc": 90.0, "temperature_norm": temp/60}
             for i in range(10)]
    rec = cfd_optimise(cells, ml_severity="normal")
    passed = rec["severity"] == "normal"
    detail = f"Tmax={temp}°C → severity='{rec['severity']}'"
    return passed, detail


def keyword_cfd_severity_warning(temp_str: str):
    """
    VERIFY CFD SEVERITY WARNING
    For a pack with max temp in warning band the severity must be 'warning'.
    """
    temp = float(temp_str)
    cells = [{"cell_id": i, "temperature": temp, "voltage": 3.6, "current": 2.5,
              "soc": 80.0, "temperature_norm": temp/60}
             for i in range(10)]
    rec = cfd_optimise(cells, ml_severity="warning")
    passed = rec["severity"] == "warning"
    detail = f"Tmax={temp}°C → severity='{rec['severity']}'"
    return passed, detail


def keyword_cfd_severity_critical(temp_str: str):
    """
    VERIFY CFD SEVERITY CRITICAL
    For a pack containing a spiked cell the severity must be 'critical'.
    """
    temp = float(temp_str)
    cells = [{"cell_id": i, "temperature": 30.0, "voltage": 3.6, "current": 2.5,
              "soc": 75.0, "temperature_norm": 30/60}
             for i in range(10)]
    cells[0] = {"cell_id": 0, "temperature": temp, "voltage": 3.1,
                "current": 4.5, "soc": 65.0, "temperature_norm": temp/60}
    rec = cfd_optimise(cells, ml_severity="critical")
    passed = rec["severity"] == "critical"
    detail = f"Spike cell T={temp}°C → severity='{rec['severity']}', spike_cells={rec['spike_cells']}"
    return passed, detail


def keyword_cfd_re_in_bounds(temp_str: str):
    """
    VERIFY CFD RE IN BOUNDS
    Reynolds number chosen by cfd_optimise must always stay within [RE_MIN, RE_MAX].
    """
    temp = float(temp_str)
    cells = [{"cell_id": i, "temperature": temp, "voltage": 3.6, "current": 2.5,
              "soc": 80.0, "temperature_norm": temp/60}
             for i in range(10)]
    # Choose severity that matches the temp level
    if temp > TEMP_CRITICAL:
        sev = "critical"
    elif temp > 40.0:
        sev = "warning"
    else:
        sev = "normal"
    rec = cfd_optimise(cells, ml_severity=sev)
    re = rec["target_re"]
    passed = RE_MIN <= re <= RE_MAX
    detail = f"T={temp}°C → Re={re}  (allowed [{RE_MIN}, {RE_MAX}])"
    return passed, detail


def keyword_cfd_concentration_matches_severity(temp_str: str, expected_conc: str):
    """
    VERIFY CFD CONCENTRATION MATCHES SEVERITY
    Checks that the chosen concentration key matches the expected one.
    """
    temp = float(temp_str)
    cells = [{"cell_id": i, "temperature": temp, "voltage": 3.6, "current": 2.5,
              "soc": 80.0, "temperature_norm": temp/60}
             for i in range(10)]
    # Derive severity from concentration expectation
    sev_map = {"low": "normal", "medium": "warning", "high": "critical"}
    sev = sev_map.get(expected_conc, "normal")
    rec = cfd_optimise(cells, ml_severity=sev)
    passed = rec["concentration_key"] == expected_conc
    detail = (f"T={temp}°C → conc_key='{rec['concentration_key']}'  "
              f"(expected '{expected_conc}')")
    return passed, detail


# ═══════════════════════════════════════════════════════════════════════════════
# Ingestion-Service Keywords
# ═══════════════════════════════════════════════════════════════════════════════

def keyword_temperature_normalisation(raw_temp: str, expected_norm: str):
    """
    VERIFY TEMPERATURE NORMALISATION
    Min-max normalisation must map raw °C to the expected [0,1] value.
    """
    temp  = float(raw_temp)
    exp   = float(expected_norm)
    norm  = normalise_temperature(temp)
    passed = abs(norm - exp) < 1e-4
    detail = f"T={temp}°C → norm={norm:.6f}  (expected {exp})"
    return passed, detail


def keyword_enrich_payload_adds_norm(temp_str: str):
    """
    VERIFY ENRICH PAYLOAD ADDS NORM
    After enrichment every cell must have a 'temperature_norm' key.
    """
    temp = float(temp_str)
    payload = {
        "tick": 1,
        "cells": [
            {"cell_id": i, "temperature": temp, "voltage": 3.6, "current": 2.5, "soc": 90.0}
            for i in range(10)
        ],
    }
    enriched = enrich_payload(payload)
    all_have_norm = all("temperature_norm" in c for c in enriched["cells"])
    passed = all_have_norm
    detail = (f"All 10 cells have 'temperature_norm': {all_have_norm}  "
              f"(sample norm={enriched['cells'][0]['temperature_norm']})")
    return passed, detail


def keyword_normalisation_bounds(raw_temp: str):
    """
    VERIFY NORMALISATION BOUNDS
    Normalised value must always be in [0.0, 1.0].
    """
    temp = float(raw_temp)
    norm = normalise_temperature(temp)
    passed = 0.0 <= norm <= 1.0
    detail = f"T={temp}°C → norm={norm:.6f}  (must be in [0, 1])"
    return passed, detail


# ═══════════════════════════════════════════════════════════════════════════════
# Registry — maps keyword name (upper-case) to function
# ═══════════════════════════════════════════════════════════════════════════════

KEYWORD_REGISTRY: dict = {
    "VERIFY NANOFLUID DENSITY IN RANGE":        keyword_nanofluid_density_in_range,
    "VERIFY FLOW VELOCITY POSITIVE":            keyword_flow_velocity_positive,
    "VERIFY NUSSELT NUMBER MINIMUM":            keyword_nusselt_number_minimum,
    "VERIFY CFD SEVERITY NORMAL":               keyword_cfd_severity_normal,
    "VERIFY CFD SEVERITY WARNING":              keyword_cfd_severity_warning,
    "VERIFY CFD SEVERITY CRITICAL":             keyword_cfd_severity_critical,
    "VERIFY CFD RE IN BOUNDS":                  keyword_cfd_re_in_bounds,
    "VERIFY CFD CONCENTRATION MATCHES SEVERITY":keyword_cfd_concentration_matches_severity,
    "VERIFY TEMPERATURE NORMALISATION":         keyword_temperature_normalisation,
    "VERIFY ENRICH PAYLOAD ADDS NORM":          keyword_enrich_payload_adds_norm,
    "VERIFY NORMALISATION BOUNDS":              keyword_normalisation_bounds,
}
