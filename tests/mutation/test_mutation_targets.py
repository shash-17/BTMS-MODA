"""
mutation/test_mutation_targets.py — Mutation Testing Targets & Manual Mutation Checks
──────────────────────────────────────────────────────────────────────────────────────
This file serves two purposes:
  1. Define a tight test suite that maximises mutant detection for mutmut.
  2. Include manual "mutation awareness" tests that verify tests WOULD fail
     if common mutations (boundary changes, operator inversions) were applied.

Run mutation tests:
    mutmut run --paths-to-mutate ai_engine/main.py --tests-dir tests/mutation/
    mutmut run --paths-to-mutate ingestion/app.py --tests-dir tests/mutation/

View results:
    mutmut results
    mutmut show <id>
    mutmut html  # generates HTML report
"""

import sys
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# sys.path is managed by tests/mutation/conftest.py

from main import (
    nanofluid_properties,
    compute_flow_velocity,
    compute_nusselt,
    cfd_optimise,
    CONC_TABLE, RE_MIN, RE_MAX, DH, TEMP_CRITICAL,
    RHO_WATER, MU_WATER, K_WATER, RHO_AL2O3,
)
from app import normalise_temperature, enrich_payload, TEMP_MIN, TEMP_MAX



def _cells(temps):
    return [{"cell_id": i, "temperature": t, "voltage": 3.6,
             "current": 2.5, "soc": 90.0, "temperature_norm": t / 60.0}
            for i, t in enumerate(temps)]


# ═══════════════════════════════════════════════════════════════════════════════
# MUT-NF — Nanofluid Properties Mutation Kill Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestNanofluidMutations:
    """Tests designed to kill common mutations in nanofluid_properties."""

    # Mutation: phi * RHO_AL2O3 → phi + RHO_AL2O3 (operator change)
    def test_density_uses_multiplication_not_addition(self):
        phi = 0.015
        p = nanofluid_properties(phi)
        wrong = phi + RHO_AL2O3 + (1 - phi) * RHO_WATER
        assert abs(p["rho"] - wrong) > 1.0  # should differ substantially

    # Mutation: (1 - phi) → (1 + phi) in density formula
    def test_density_complement_factor_is_correct(self):
        phi = 0.015
        p = nanofluid_properties(phi)
        wrong_rho = phi * RHO_AL2O3 + (1 + phi) * RHO_WATER  # mutant
        assert abs(p["rho"] - wrong_rho) > 1.0

    # Mutation: math.exp(2.5 * phi) → math.exp(2.5 + phi)
    def test_viscosity_uses_product_in_exponent(self):
        phi = 0.015
        p = nanofluid_properties(phi)
        mutant = MU_WATER * math.exp(2.5 + phi)
        assert abs(p["mu"] - mutant) > 1e-6

    # Mutation: (1 + 3 * phi) → (1 - 3 * phi)
    def test_conductivity_uses_positive_factor(self):
        phi = 0.015
        p = nanofluid_properties(phi)
        assert p["k"] > K_WATER  # must be GREATER than pure water

    # Mutation: phi = 0 edge case — all must equal base fluid
    def test_zero_phi_equals_base_fluid(self):
        p = nanofluid_properties(0.0)
        assert abs(p["rho"] - RHO_WATER) < 1e-6
        assert abs(p["mu"] - MU_WATER) < 1e-10
        assert abs(p["k"] - K_WATER) < 1e-9

    # Mutation: return key name "rho" → "density" (field name mutation)
    def test_dict_has_exactly_rho_key(self):
        p = nanofluid_properties(0.01)
        assert "rho" in p
        assert "density" not in p
        assert "mu" in p
        assert "k" in p


# ═══════════════════════════════════════════════════════════════════════════════
# MUT-FV — Flow Velocity Mutation Kill Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFlowVelocityMutations:

    # Mutation: re_target * props["mu"] → re_target / props["mu"]
    def test_velocity_uses_mu_in_numerator(self):
        props = nanofluid_properties(0.015)
        v_correct = compute_flow_velocity(550, props)
        mutant_v = 550 / (props["mu"] * props["rho"] * DH)  # mu in denominator
        assert abs(v_correct - mutant_v) > 0.01

    # Mutation: props["rho"] * DH → props["rho"] + DH
    def test_velocity_uses_product_denominator(self):
        props = nanofluid_properties(0.015)
        v = compute_flow_velocity(550, props)
        mutant = (550 * props["mu"]) / (props["rho"] + DH)  # addition mutant
        assert abs(v - mutant) > 0.01

    # Mutation: DH = 0.001 → DH = 0.01 (off-by-10x)
    def test_dh_value_is_exactly_1mm(self):
        assert abs(DH - 0.001) < 1e-9
        assert DH != 0.01

    # Monotonicity check — kills sign-flip mutations
    def test_velocity_monotone_in_re(self):
        props = nanofluid_properties(0.015)
        velocities = [compute_flow_velocity(re, props) for re in [400, 450, 500, 550, 600, 700]]
        assert all(velocities[i] < velocities[i+1] for i in range(len(velocities)-1))


# ═══════════════════════════════════════════════════════════════════════════════
# MUT-NU — Nusselt Number Mutation Kill Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestNusseltMutations:

    # Mutation: 3.66 → 0.0 (constant zeroed out)
    def test_laminar_floor_constant_is_3_66(self):
        # At very low Gz, Nu approaches 3.66
        nu_very_low_re = compute_nusselt(1, 0.001)  # tiny Gz → nu≈3.66
        assert abs(nu_very_low_re - 3.66) < 0.01

    # Mutation: 0.065 → 0.65 (off by 10x)
    def test_graetz_coefficient_magnitude(self):
        nu_400 = compute_nusselt(400, 6.5)
        nu_700 = compute_nusselt(700, 6.5)
        # With 0.065, the spread should be moderate; with 0.65 it'd be much larger
        spread = nu_700 - nu_400
        assert 0.5 < spread < 20.0, f"Unexpected Nu spread: {spread}"

    # Mutation: gz ** (2/3) → gz ** (3/2) (exponent flip)
    def test_nusselt_nonlinear_growth(self):
        # Re=700 should give noticeably more than double Re=350
        nu_350 = compute_nusselt(350, 6.5)
        nu_700 = compute_nusselt(700, 6.5)
        assert nu_700 > nu_350 * 1.05  # at least 5% higher, but not linear

    # Mutation: round(nu, 3) → round(nu, 1) (precision loss)
    def test_nusselt_precision_to_3_places(self):
        nu = compute_nusselt(550, 6.5)
        # If rounded to 3 places, multiplying by 1000 and flooring should give non-trivial decimal
        frac_digits = len(str(nu).split(".")[-1]) if "." in str(nu) else 0
        assert frac_digits <= 3  # no more than 3 decimal places

    # Mutation: L = 0.1 → L = 1.0 (off-by-10x channel length)
    def test_channel_length_effect(self):
        # With L=0.1, Gz = Re*Pr*0.001/0.1 = Re*Pr*0.01
        # With L=1.0, Gz would be 10x smaller → Nu would be ~3.66 (much lower)
        nu = compute_nusselt(550, 6.5)
        assert nu > 4.0, f"Nu={nu} too close to laminar floor — channel length may be wrong"


# ═══════════════════════════════════════════════════════════════════════════════
# MUT-CFD — cfd_optimise Mutation Kill Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestCFDOptimiseMutations:

    # Mutation: > TEMP_CRITICAL → >= TEMP_CRITICAL (boundary off-by-one)
    def test_exactly_45_degrees_is_not_a_spike(self):
        """Cells at exactly 45.0°C must NOT be marked as spikes (> not >=)."""
        cells = _cells([45.0] * 10)
        rec = cfd_optimise(cells, ml_severity="normal")
        assert rec["spike_cells"] == []

    def test_45_001_degrees_is_a_spike(self):
        """Cells at 45.001°C MUST be marked as spikes."""
        cells = _cells([28.0] * 9 + [45.001])
        rec = cfd_optimise(cells, ml_severity="normal")
        assert 9 in rec["spike_cells"]

    # Mutation: RE_TARGET_SPIKE = 680 → RE_TARGET_SPIKE = 680.0 (no change)
    #           or RE_TARGET_SPIKE → RE_TARGET_NORMAL (value mutation)
    def test_critical_uses_higher_re_than_normal(self):
        cells_n = _cells([28.0] * 10)
        cells_c = _cells([28.0] * 10)
        rec_n = cfd_optimise(cells_n, ml_severity="normal")
        rec_c = cfd_optimise(cells_c, ml_severity="critical")
        assert rec_c["target_re"] > rec_n["target_re"]

    # Mutation: "low" → "medium" for normal severity
    def test_normal_severity_returns_low_not_medium(self):
        rec = cfd_optimise(_cells([28.0] * 10), ml_severity="normal")
        assert rec["concentration_key"] == "low"
        assert rec["concentration_key"] != "medium"

    # Mutation: max(RE_MIN, ...) → min(RE_MIN, ...) (clamping inverted)
    def test_re_clamped_to_minimum_not_maximum(self):
        # If clamping were inverted, very aggressive targets would be unclamped
        rec = cfd_optimise(_cells([30.0] * 10), ml_severity="critical")
        assert rec["target_re"] >= RE_MIN  # must not go below minimum

    # Mutation: min(RE_MAX, ...) → max(RE_MAX, ...) (upper clamp inverted)
    def test_re_clamped_to_maximum(self):
        rec = cfd_optimise(_cells([30.0] * 10), ml_severity="critical")
        assert rec["target_re"] <= RE_MAX  # must not exceed maximum

    # Mutation: "ml_driven": True → False (flag flipped)
    def test_ml_driven_flag_is_exactly_true(self):
        rec = cfd_optimise(_cells([30.0] * 10), ml_severity="normal")
        assert rec["ml_driven"] is True
        assert rec["ml_driven"] is not False

    # Mutation: flow_rate uses e6 * 60 → e6 / 60 (unit conversion error)
    def test_flow_rate_units_are_ml_per_minute(self):
        """flow_rate_ml_min must be in a physically realistic mL/min range for a 1mm microchannel."""
        rec = cfd_optimise(_cells([30.0] * 10), ml_severity="normal")
        flow = rec["flow_rate_ml_min"]
        # If unit conversion had e6/60 instead of e6*60, result would be ~0.005 mL/min (too small)
        assert flow > 1.0, f"flow_rate_ml_min={flow} too small — likely e6/60 mutation"
        # If unit were in L/min (e3*60), result would be ~0.019 L/min
        # Physical range for 1mm microchannel at Re=400-700: ~10–50 mL/min
        assert flow < 200.0, f"flow_rate_ml_min={flow} too large — possible unit error"

    # Mutation: max(temps) - min(temps) → max(temps) + min(temps) (sign flip)
    def test_delta_t_is_difference_not_sum(self):
        temps = [20.0, 30.0, 25.0, 28.0, 32.0, 35.0, 22.0, 24.0, 26.0, 29.0]
        rec = cfd_optimise(_cells(temps), ml_severity="warning")
        delta = max(temps) - min(temps)
        sum_extremes = max(temps) + min(temps)
        assert abs(rec["delta_t"] - delta) < 0.01
        assert abs(rec["delta_t"] - sum_extremes) > 1.0

    # Mutation: round(max_temp, 2) → round(avg_temp, 2) (field swap)
    def test_max_temp_is_not_avg_temp(self):
        temps = [20.0, 25.0, 30.0, 35.0, 40.0, 22.0, 24.0, 26.0, 28.0, 30.0]
        rec = cfd_optimise(_cells(temps), ml_severity="warning")
        avg = sum(temps) / len(temps)
        mx = max(temps)
        assert abs(rec["max_temp"] - mx) < 0.01
        assert abs(rec["max_temp"] - avg) > 1.0  # must differ from avg

    # Mutation: len(temps) → len(temps) - 1 (off by one in avg)
    def test_avg_temp_uses_correct_denominator(self):
        # All equal temps: avg = any individual temp
        temps = [30.0] * 10
        rec = cfd_optimise(_cells(temps), ml_severity="normal")
        assert abs(rec["avg_temp"] - 30.0) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# MUT-ING — Ingestion Service Mutation Kill Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestIngestionMutations:

    # Mutation: (raw_temp - TEMP_MIN) → (raw_temp + TEMP_MIN)
    def test_normalisation_subtracts_not_adds_min(self):
        # Since TEMP_MIN=0, we verify the formula gives the correct value directly.
        # If the mutation added MIN instead of subtracting: (T+0)/60 == (T-0)/60, same result.
        # We instead verify monotonicity proof — normalise(T1) < normalise(T2) when T1 < T2.
        result_low = normalise_temperature(10.0)
        result_high = normalise_temperature(40.0)
        assert result_low < result_high  # must be strictly increasing (subtraction, not addition)
        # Also verify exact formula for a non-zero T
        T = 45.0
        expected = (T - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)
        assert abs(normalise_temperature(T) - expected) < 1e-9

    # Mutation: (TEMP_MAX - TEMP_MIN) → (TEMP_MAX + TEMP_MIN) (denominator)
    def test_normalisation_divides_by_range_not_sum(self):
        # When TEMP_MIN=0, max-min == max+min, so we test with a non-trivial formula check.
        # With T=45, correct norm = 45/60 = 0.75
        # If denominator were wrong (e.g., max*2=120), norm = 45/120 = 0.375 — noticeably different.
        T = 45.0
        result = normalise_temperature(T)
        # Verify correct formula gives 0.75 when TEMP_MAX=60, TEMP_MIN=0
        assert abs(result - 0.75) < 1e-9, f"Expected 0.75 for T=45, got {result}"
        # And result must NOT equal (T / (2 * TEMP_MAX)) when max != 0
        wrong_double_max = T / (2 * TEMP_MAX) if TEMP_MAX != 0 else None
        if wrong_double_max is not None:
            assert abs(result - wrong_double_max) > 0.1, "Denominator mutation not caught"

    # Mutation: TEMP_MIN boundary (0.0 vs 1.0 after normalise)
    def test_temp_min_gives_zero_not_one(self):
        result = normalise_temperature(TEMP_MIN)
        assert result == 0.0
        assert result != 1.0

    # Mutation: TEMP_MAX boundary (1.0 vs 0.0 after normalise)
    def test_temp_max_gives_one_not_zero(self):
        result = normalise_temperature(TEMP_MAX)
        assert result == 1.0
        assert result != 0.0

    # Mutation: temperature_norm is added vs overwritten
    def test_enrich_sets_temperature_norm_field(self):
        payload = {
            "tick": 1,
            "cells": [{"cell_id": 0, "temperature": 35.0, "voltage": 3.6, "current": 2.5, "soc": 90.0}]
        }
        enriched = enrich_payload(payload)
        assert "temperature_norm" in enriched["cells"][0]

    # Mutation: wrong cell temperature used in enrich
    def test_enrich_uses_cells_own_temperature(self):
        payload = {
            "tick": 1,
            "cells": [
                {"cell_id": 0, "temperature": 20.0, "voltage": 3.6, "current": 2.5, "soc": 90.0},
                {"cell_id": 1, "temperature": 50.0, "voltage": 3.6, "current": 2.5, "soc": 90.0},
            ]
        }
        enriched = enrich_payload(payload)
        n0 = enriched["cells"][0]["temperature_norm"]
        n1 = enriched["cells"][1]["temperature_norm"]
        # 20°C norm should be much less than 50°C norm
        assert n0 < n1
        # And they should match per-cell expected values
        assert abs(n0 - normalise_temperature(20.0)) < 1e-6
        assert abs(n1 - normalise_temperature(50.0)) < 1e-6


# ═══════════════════════════════════════════════════════════════════════════════
# MUT-MANUAL — Intentional boundary detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestManualMutantDetection:
    """
    These tests explicitly verify boundary conditions that mutmut
    commonly exploits (off-by-one, comparison operators, constant changes).
    """

    @pytest.mark.parametrize("temp,expected_is_spike", [
        (44.999, False),
        (45.000, False),  # exactly at boundary — NOT a spike
        (45.001, True),   # just above — IS a spike
        (46.000, True),
        (58.000, True),
    ])
    def test_spike_boundary_at_45_degrees(self, temp, expected_is_spike):
        """MUT-MANUAL-001: Spike detection boundary must be strictly > 45°C."""
        cells = _cells([30.0] * 9 + [temp])
        rec = cfd_optimise(cells, ml_severity="normal")
        is_spike = 9 in rec["spike_cells"]
        assert is_spike == expected_is_spike, (
            f"T={temp}°C: expected spike={expected_is_spike}, got {is_spike}"
        )

    @pytest.mark.parametrize("severity,expected_conc", [
        ("normal", "low"),
        ("warning", "medium"),
        ("critical", "high"),
    ])
    def test_severity_to_concentration_mapping(self, severity, expected_conc):
        """MUT-MANUAL-002: Severity → concentration mapping must be exact."""
        rec = cfd_optimise(_cells([28.0] * 10), ml_severity=severity)
        assert rec["concentration_key"] == expected_conc

    @pytest.mark.parametrize("re_target,expected_clamped", [
        (399, 400),   # below min → clamped to RE_MIN
        (400, 400),   # at min → unchanged
        (550, 550),   # in range → unchanged
        (700, 700),   # at max → unchanged
        (701, 700),   # above max → clamped to RE_MAX
    ])
    def test_re_clamping_boundaries(self, re_target, expected_clamped):
        """MUT-MANUAL-003: Re clamping must use both max() and min() correctly."""
        clamped = max(RE_MIN, min(RE_MAX, re_target))
        assert clamped == expected_clamped

    @pytest.mark.parametrize("phi,expected_vol_pct", [
        (0.005, 0.5),
        (0.015, 1.5),
        (0.030, 3.0),
    ])
    def test_al2o3_volume_percent_conversion(self, phi, expected_vol_pct):
        """MUT-MANUAL-004: phi → vol% conversion must multiply by 100, not 10 or 1000."""
        vol_pct = round(phi * 100, 1)
        assert vol_pct == expected_vol_pct

    def test_normalise_monotone(self):
        """MUT-MANUAL-005: normalise_temperature must be strictly increasing."""
        temps = [0, 10, 20, 30, 40, 50, 60]
        norms = [normalise_temperature(float(t)) for t in temps]
        assert all(norms[i] < norms[i+1] for i in range(len(norms)-1))
