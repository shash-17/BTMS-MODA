"""
test_cfd_engine.py  — Data-Driven Tests for BTMS AI / CFD Engine
─────────────────────────────────────────────────────────────────────
Reads cfd_cases.csv and parametrises pytest so every CSV row becomes
a separate, individually-named test.  No live service required —
tests call the pure Python logic directly.

Run:
    pytest tests/data_driven/test_cfd_engine.py -v
    pytest tests/data_driven/test_cfd_engine.py -v --html=tests/reports/ddt_cfd.html
"""

import csv
import math
import os
import sys
from pathlib import Path

import pytest

# ── Source imports ─────────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parents[2]
AI_ENGINE  = ROOT / "ai_engine"
sys.path.insert(0, str(AI_ENGINE))

from main import (
    nanofluid_properties,
    compute_flow_velocity,
    compute_nusselt,
    cfd_optimise,
    CONC_TABLE,
    RE_MIN, RE_MAX, DH,
    TEMP_CRITICAL,
    RHO_WATER, MU_WATER, K_WATER, RHO_AL2O3,
)

DATASET = Path(__file__).parent / "datasets" / "cfd_cases.csv"


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _load_cfd_cases():
    """Return list of pytest.param objects from the CSV dataset."""
    params = []
    with open(DATASET, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            temps = [float(t) for t in row["temperatures"].split(",")]
            params.append(
                pytest.param(
                    row["test_id"],
                    int(row["num_cells"]),
                    temps,
                    row["expected_severity"],
                    row["expected_conc_key"],
                    float(row["expected_re_min"]),
                    float(row["expected_re_max"]),
                    id=f"{row['test_id']}::{row['description'][:40]}",
                )
            )
    return params


def _build_cells(temps: list[float]) -> list[dict]:
    """Build a minimal cell list from a temperature list."""
    return [
        {
            "cell_id":          i,
            "temperature":      t,
            "voltage":          3.6 - (1 - 90/100) * 0.5,  # nominal
            "current":          2.5,
            "soc":              90.0,
            "temperature_norm": t / 60.0,
        }
        for i, t in enumerate(temps)
    ]


_ML_SEVERITY_MAP = {
    "normal":   "normal",
    "warning":  "warning",
    "critical": "critical",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Data-Driven: CFD optimise  — severity
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "test_id,num_cells,temps,exp_severity,exp_conc,exp_re_min,exp_re_max",
    _load_cfd_cases(),
)
def test_cfd_severity(test_id, num_cells, temps, exp_severity, exp_conc, exp_re_min, exp_re_max):
    """[DDT] cfd_optimise returns the correct severity when driven by the expected ML verdict."""
    cells = _build_cells(temps)
    # Drive CFD with the expected ML severity (isolates CFD logic from ML variability)
    rec   = cfd_optimise(cells, ml_severity=exp_severity)
    assert rec["severity"] == exp_severity, (
        f"[{test_id}] Expected severity='{exp_severity}' "
        f"but got '{rec['severity']}' (Tmax={max(temps)}°C)"
    )


@pytest.mark.parametrize(
    "test_id,num_cells,temps,exp_severity,exp_conc,exp_re_min,exp_re_max",
    _load_cfd_cases(),
)
def test_cfd_concentration_key(test_id, num_cells, temps, exp_severity, exp_conc, exp_re_min, exp_re_max):
    """[DDT] cfd_optimise selects the correct Al₂O₃ concentration key."""
    cells = _build_cells(temps)
    rec   = cfd_optimise(cells, ml_severity=exp_severity)
    assert rec["concentration_key"] == exp_conc, (
        f"[{test_id}] Expected conc='{exp_conc}' "
        f"but got '{rec['concentration_key']}'"
    )


@pytest.mark.parametrize(
    "test_id,num_cells,temps,exp_severity,exp_conc,exp_re_min,exp_re_max",
    _load_cfd_cases(),
)
def test_cfd_re_in_bounds(test_id, num_cells, temps, exp_severity, exp_conc, exp_re_min, exp_re_max):
    """[DDT] Reynolds number must always stay in [RE_MIN, RE_MAX]."""
    cells = _build_cells(temps)
    rec   = cfd_optimise(cells, ml_severity=exp_severity)
    assert exp_re_min <= rec["target_re"] <= exp_re_max, (
        f"[{test_id}] Re={rec['target_re']} outside [{exp_re_min}, {exp_re_max}]"
    )


@pytest.mark.parametrize(
    "test_id,num_cells,temps,exp_severity,exp_conc,exp_re_min,exp_re_max",
    _load_cfd_cases(),
)
def test_cfd_flow_rate_positive(test_id, num_cells, temps, exp_severity, exp_conc, exp_re_min, exp_re_max):
    """[DDT] Flow rate must always be a positive value."""
    cells = _build_cells(temps)
    rec   = cfd_optimise(cells, ml_severity=exp_severity)
    assert rec["flow_rate_ml_min"] > 0, (
        f"[{test_id}] flow_rate_ml_min={rec['flow_rate_ml_min']} ≤ 0"
    )


@pytest.mark.parametrize(
    "test_id,num_cells,temps,exp_severity,exp_conc,exp_re_min,exp_re_max",
    _load_cfd_cases(),
)
def test_cfd_nusselt_above_floor(test_id, num_cells, temps, exp_severity, exp_conc, exp_re_min, exp_re_max):
    """[DDT] Nusselt number must be ≥ 3.66 (fully-developed laminar floor)."""
    cells = _build_cells(temps)
    rec   = cfd_optimise(cells, ml_severity=exp_severity)
    assert rec["nusselt_number"] >= 3.66, (
        f"[{test_id}] Nu={rec['nusselt_number']} < 3.66"
    )


@pytest.mark.parametrize(
    "test_id,num_cells,temps,exp_severity,exp_conc,exp_re_min,exp_re_max",
    _load_cfd_cases(),
)
def test_cfd_htc_positive(test_id, num_cells, temps, exp_severity, exp_conc, exp_re_min, exp_re_max):
    """[DDT] Heat-transfer coefficient must be positive."""
    cells = _build_cells(temps)
    rec   = cfd_optimise(cells, ml_severity=exp_severity)
    assert rec["heat_transfer_coeff_W_m2K"] > 0, (
        f"[{test_id}] HTC={rec['heat_transfer_coeff_W_m2K']} ≤ 0"
    )


@pytest.mark.parametrize(
    "test_id,num_cells,temps,exp_severity,exp_conc,exp_re_min,exp_re_max",
    _load_cfd_cases(),
)
def test_cfd_spike_cells_correct(test_id, num_cells, temps, exp_severity, exp_conc, exp_re_min, exp_re_max):
    """[DDT] spike_cells list must exactly match cells above TEMP_CRITICAL (HW safety floor)."""
    cells = _build_cells(temps)
    rec   = cfd_optimise(cells, ml_severity=exp_severity)
    expected_spikes = sorted([i for i, t in enumerate(temps) if t > TEMP_CRITICAL])
    assert sorted(rec["spike_cells"]) == expected_spikes, (
        f"[{test_id}] spike_cells={rec['spike_cells']} "
        f"but expected {expected_spikes}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Standalone pure-physics Data-Driven tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("phi,expected_rho_min,expected_rho_max", [
    (0.005, 1005.0, 1020.0),  # 0.5 vol% — slight increase from pure water
    (0.015, 1035.0, 1055.0),  # 1.5 vol%
    (0.030, 1075.0, 1100.0),  # 3.0 vol%
], ids=["phi=0.5%", "phi=1.5%", "phi=3.0%"])
def test_nanofluid_density_range(phi, expected_rho_min, expected_rho_max):
    """[DDT] Nanofluid density must be within physical bounds for each φ."""
    props = nanofluid_properties(phi)
    assert expected_rho_min <= props["rho"] <= expected_rho_max, (
        f"φ={phi*100}% → ρ={props['rho']:.2f} outside [{expected_rho_min}, {expected_rho_max}]"
    )


@pytest.mark.parametrize("phi,expected_mu_min,expected_mu_max", [
    (0.005, 8.9e-4, 9.2e-4),
    (0.015, 9.2e-4, 9.7e-4),
    (0.030, 9.4e-4, 9.7e-4),
], ids=["phi=0.5%", "phi=1.5%", "phi=3.0%"])
def test_nanofluid_viscosity_increases_with_phi(phi, expected_mu_min, expected_mu_max):
    """[DDT] Adding nanoparticles increases viscosity (Einstein model)."""
    props = nanofluid_properties(phi)
    assert expected_mu_min <= props["mu"] <= expected_mu_max, (
        f"φ={phi*100}% → μ={props['mu']:.6f} Pa·s outside [{expected_mu_min:.6f}, {expected_mu_max:.6f}]"
    )


@pytest.mark.parametrize("re,pr", [
    (400, 6.0), (450, 6.5), (500, 6.8), (600, 7.0), (700, 7.2),
], ids=["Re=400", "Re=450", "Re=500", "Re=600", "Re=700"])
def test_nusselt_monotonically_increases_with_re(re, pr):
    """[DDT] Higher Re → higher Nu (monotone for laminar microchannel flow)."""
    nu_low  = compute_nusselt(re, pr)
    nu_high = compute_nusselt(re + 50, pr)
    assert nu_high > nu_low, (
        f"Nu did not increase: Nu({re})={nu_low:.3f} ≥ Nu({re+50})={nu_high:.3f}"
    )


@pytest.mark.parametrize("phi,re_target", [
    (0.005, 450), (0.015, 550), (0.030, 680),
], ids=["nominal", "warning", "critical"])
def test_flow_velocity_increases_with_re(phi, re_target):
    """[DDT] Higher Re target → higher flow velocity (for same φ)."""
    props_lo = nanofluid_properties(phi)
    v_lo = compute_flow_velocity(re_target, props_lo)
    v_hi = compute_flow_velocity(re_target + 50, props_lo)
    assert v_hi > v_lo


@pytest.mark.parametrize("phi", [0.005, 0.015, 0.030])
def test_nanofluid_conductivity_increases_with_phi(phi):
    """[DDT] Thermal conductivity must be higher than pure water for all φ > 0."""
    props = nanofluid_properties(phi)
    assert props["k"] > K_WATER, (
        f"φ={phi*100}% → k={props['k']:.4f} should exceed k_water={K_WATER}"
    )
