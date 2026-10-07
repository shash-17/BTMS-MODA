"""
unit/test_cfd_physics.py — Unit Tests for BTMS AI Engine & Ingestion Service
────────────────────────────────────────────────────────────────────────────────
Tests individual, isolated functions with no external dependencies.

Run:
    pytest tests/unit/test_cfd_physics.py -v
    pytest tests/unit/ -v --html=tests/reports/unit_report.html
"""

import math
import sys
import importlib.util
from pathlib import Path

import pytest

# ── Explicit module loading to avoid sys.path conflicts ───────────────────────
ROOT = Path(__file__).resolve().parents[2]


def _load_module(mod_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, mod_path)
    mod = importlib.util.module_from_spec(spec)
    # Ensure the module's own directory is in path for its own imports
    mod_dir = str(mod_path.parent)
    if mod_dir not in sys.path:
        sys.path.insert(0, mod_dir)
    spec.loader.exec_module(mod)
    return mod


ai_main = _load_module(ROOT / "ai_engine" / "main.py", "ai_main")
ing_app = _load_module(ROOT / "ingestion" / "app.py", "ing_app")

nanofluid_properties = ai_main.nanofluid_properties
compute_flow_velocity = ai_main.compute_flow_velocity
compute_nusselt = ai_main.compute_nusselt
cfd_optimise = ai_main.cfd_optimise
CONC_TABLE = ai_main.CONC_TABLE
RE_MIN = ai_main.RE_MIN
RE_MAX = ai_main.RE_MAX
DH = ai_main.DH
TEMP_CRITICAL = ai_main.TEMP_CRITICAL
RHO_WATER = ai_main.RHO_WATER
MU_WATER = ai_main.MU_WATER
K_WATER = ai_main.K_WATER
RHO_AL2O3 = ai_main.RHO_AL2O3

normalise_temperature = ing_app.normalise_temperature
enrich_payload = ing_app.enrich_payload
TEMP_MIN = ing_app.TEMP_MIN
TEMP_MAX = ing_app.TEMP_MAX


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _cells(temps, voltage=3.6, current=2.5, soc=90.0):
    return [
        {"cell_id": i, "temperature": t, "voltage": voltage,
         "current": current, "soc": soc, "temperature_norm": t / 60.0}
        for i, t in enumerate(temps)
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# UT-CFD-001 — nanofluid_properties
# ═══════════════════════════════════════════════════════════════════════════════

class TestNanofluidProperties:

    def test_pure_water_density_at_phi_zero(self):
        """UT-CFD-001a: phi=0 -> density equals pure water."""
        p = nanofluid_properties(0.0)
        assert abs(p["rho"] - RHO_WATER) < 1e-6

    def test_pure_water_viscosity_at_phi_zero(self):
        """UT-CFD-001b: phi=0 -> viscosity equals pure water."""
        p = nanofluid_properties(0.0)
        assert abs(p["mu"] - MU_WATER) < 1e-10

    def test_pure_water_conductivity_at_phi_zero(self):
        """UT-CFD-001c: phi=0 -> conductivity equals pure water."""
        p = nanofluid_properties(0.0)
        assert abs(p["k"] - K_WATER) < 1e-9

    def test_density_increases_monotonically_with_phi(self):
        """UT-CFD-001d: Higher nanoparticle loading -> higher density."""
        phis = [0.005, 0.010, 0.015, 0.020, 0.030]
        densities = [nanofluid_properties(p)["rho"] for p in phis]
        assert all(densities[i] < densities[i+1] for i in range(len(densities)-1))

    def test_viscosity_increases_monotonically_with_phi(self):
        """UT-CFD-001e: Higher phi -> higher viscosity (Einstein model)."""
        phis = [0.005, 0.010, 0.020, 0.030]
        viscosities = [nanofluid_properties(p)["mu"] for p in phis]
        assert all(viscosities[i] < viscosities[i+1] for i in range(len(viscosities)-1))

    def test_conductivity_increases_monotonically_with_phi(self):
        """UT-CFD-001f: Higher phi -> higher conductivity (Maxwell model)."""
        phis = [0.005, 0.010, 0.020, 0.030]
        conductivities = [nanofluid_properties(p)["k"] for p in phis]
        assert all(conductivities[i] < conductivities[i+1] for i in range(len(conductivities)-1))

    def test_returns_dict_with_required_keys(self):
        """UT-CFD-001g: nanofluid_properties must return dict with rho, mu, k."""
        p = nanofluid_properties(0.015)
        assert set(p.keys()) == {"rho", "mu", "k"}

    def test_density_formula_correctness(self):
        """UT-CFD-001h: Manual verification of mixture rule density formula."""
        phi = 0.015
        expected_rho = phi * RHO_AL2O3 + (1 - phi) * RHO_WATER
        p = nanofluid_properties(phi)
        assert abs(p["rho"] - expected_rho) < 1e-9

    def test_viscosity_formula_correctness(self):
        """UT-CFD-001i: Einstein model: mu_nf = mu_water * exp(2.5*phi)."""
        phi = 0.015
        expected_mu = MU_WATER * math.exp(2.5 * phi)
        p = nanofluid_properties(phi)
        assert abs(p["mu"] - expected_mu) < 1e-12

    def test_conductivity_formula_correctness(self):
        """UT-CFD-001j: Maxwell dilute model: k_nf = k_water * (1 + 3*phi)."""
        phi = 0.015
        expected_k = K_WATER * (1 + 3 * phi)
        p = nanofluid_properties(phi)
        assert abs(p["k"] - expected_k) < 1e-9

    @pytest.mark.parametrize("phi", [0.005, 0.015, 0.030])
    def test_all_properties_are_positive(self, phi):
        """UT-CFD-001k: All thermophysical properties must be strictly positive."""
        p = nanofluid_properties(phi)
        assert p["rho"] > 0 and p["mu"] > 0 and p["k"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# UT-CFD-002 — compute_flow_velocity
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeFlowVelocity:

    def test_velocity_formula_correctness(self):
        """UT-CFD-002a: v = Re * mu / (rho * Dh)."""
        phi = 0.015
        props = nanofluid_properties(phi)
        re = 550.0
        expected = (re * props["mu"]) / (props["rho"] * DH)
        result = compute_flow_velocity(re, props)
        assert abs(result - expected) < 1e-12

    def test_velocity_positive_for_positive_re(self):
        """UT-CFD-002b: Positive Re -> positive velocity."""
        props = nanofluid_properties(0.015)
        for re in [400, 500, 600, 700]:
            assert compute_flow_velocity(re, props) > 0

    def test_higher_re_gives_higher_velocity(self):
        """UT-CFD-002c: Velocity is proportional to Re for fixed phi."""
        props = nanofluid_properties(0.015)
        v_low = compute_flow_velocity(400, props)
        v_high = compute_flow_velocity(700, props)
        assert v_high > v_low

    def test_velocity_inverse_proportional_to_density(self):
        """UT-CFD-002d: Higher density (higher phi) -> lower velocity for same Re."""
        re = 550
        v_low_phi = compute_flow_velocity(re, nanofluid_properties(0.005))
        v_high_phi = compute_flow_velocity(re, nanofluid_properties(0.030))
        assert v_low_phi > v_high_phi

    def test_re_400_gives_plausible_velocity(self):
        """UT-CFD-002e: Re=400 gives physically plausible microchannel velocity."""
        props = nanofluid_properties(0.005)
        v = compute_flow_velocity(400, props)
        assert 0.01 < v < 5.0


# ═══════════════════════════════════════════════════════════════════════════════
# UT-CFD-003 — compute_nusselt
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeNusselt:

    def test_fully_developed_laminar_floor(self):
        """UT-CFD-003a: Nu must always be >= 3.66."""
        for re in [400, 450, 500, 600, 700]:
            for pr in [4.0, 6.0, 7.0]:
                nu = compute_nusselt(re, pr)
                assert nu >= 3.66, f"Nu={nu} < 3.66 for Re={re}, Pr={pr}"

    def test_nusselt_increases_with_re(self):
        """UT-CFD-003b: Higher Re -> higher Nu at fixed Pr."""
        pr = 6.5
        assert compute_nusselt(700, pr) > compute_nusselt(400, pr)

    def test_nusselt_increases_with_pr(self):
        """UT-CFD-003c: Higher Pr -> higher Nu at fixed Re."""
        re = 550
        assert compute_nusselt(re, 7.5) > compute_nusselt(re, 4.0)

    def test_nusselt_returns_float(self):
        """UT-CFD-003d: compute_nusselt must return a float."""
        assert isinstance(compute_nusselt(500, 6.5), float)

    def test_nusselt_rounded_to_3_decimal_places(self):
        """UT-CFD-003e: Return value must have at most 3 decimal places."""
        nu = compute_nusselt(500, 6.5)
        assert nu == round(nu, 3)


# ═══════════════════════════════════════════════════════════════════════════════
# UT-CFD-004 — cfd_optimise
# ═══════════════════════════════════════════════════════════════════════════════

class TestCfdOptimise:

    def test_normal_severity_uses_low_concentration(self):
        """UT-CFD-004a: ML severity=normal -> Al2O3 conc=low (0.5%)."""
        rec = cfd_optimise(_cells([28.0] * 10), ml_severity="normal")
        assert rec["concentration_key"] == "low"
        assert rec["al2o3_vol_percent"] == 0.5

    def test_warning_severity_uses_medium_concentration(self):
        """UT-CFD-004b: ML severity=warning -> Al2O3 conc=medium (1.5%)."""
        rec = cfd_optimise(_cells([42.0] * 10), ml_severity="warning")
        assert rec["concentration_key"] == "medium"
        assert rec["al2o3_vol_percent"] == 1.5

    def test_critical_severity_uses_high_concentration(self):
        """UT-CFD-004c: ML severity=critical -> Al2O3 conc=high (3.0%)."""
        rec = cfd_optimise(_cells([30.0] * 10), ml_severity="critical")
        assert rec["concentration_key"] == "high"
        assert rec["al2o3_vol_percent"] == 3.0

    def test_hw_spike_overrides_ml_normal(self):
        """UT-CFD-004d: Temperature > 45C physically overrides ML=normal -> critical."""
        rec = cfd_optimise(_cells([28.0] * 9 + [46.0]), ml_severity="normal")
        assert rec["severity"] == "critical"

    def test_spike_cells_identified_correctly(self):
        """UT-CFD-004e: spike_cells must list only cells above TEMP_CRITICAL."""
        temps = [28.0, 30.0, 32.0, 46.0, 35.0, 47.0, 25.0, 28.0, 30.0, 31.0]
        rec = cfd_optimise(_cells(temps), ml_severity="critical")
        assert sorted(rec["spike_cells"]) == [3, 5]

    def test_re_within_physical_bounds(self):
        """UT-CFD-004f: Re must always be in [RE_MIN, RE_MAX]=[400, 700]."""
        for severity in ["normal", "warning", "critical"]:
            rec = cfd_optimise(_cells([30.0] * 10), ml_severity=severity)
            assert RE_MIN <= rec["target_re"] <= RE_MAX

    def test_flow_rate_always_positive(self):
        """UT-CFD-004g: Flow rate must be > 0 for all severities."""
        for severity in ["normal", "warning", "critical"]:
            rec = cfd_optimise(_cells([30.0] * 10), ml_severity=severity)
            assert rec["flow_rate_ml_min"] > 0

    def test_htc_always_positive(self):
        """UT-CFD-004h: Heat transfer coefficient must be > 0."""
        rec = cfd_optimise(_cells([30.0] * 10), ml_severity="normal")
        assert rec["heat_transfer_coeff_W_m2K"] > 0

    def test_result_contains_required_keys(self):
        """UT-CFD-004i: Output dict must contain all required fields."""
        required = {
            "severity", "spike_cells", "max_temp", "avg_temp", "delta_t",
            "target_re", "concentration_key", "al2o3_vol_percent",
            "flow_velocity_m_s", "flow_rate_ml_min", "nusselt_number",
            "heat_transfer_coeff_W_m2K", "timestamp",
        }
        rec = cfd_optimise(_cells([30.0] * 10), ml_severity="normal")
        assert required.issubset(set(rec.keys()))

    def test_max_temp_correct(self):
        """UT-CFD-004j: max_temp must equal the maximum of input temperatures."""
        temps = [20.0, 22.0, 35.0, 40.0, 28.0, 30.0, 25.0, 27.0, 29.0, 31.0]
        rec = cfd_optimise(_cells(temps), ml_severity="warning")
        assert abs(rec["max_temp"] - 40.0) < 0.01

    def test_delta_t_correct(self):
        """UT-CFD-004k: delta_t must equal max - min temperature."""
        temps = [20.0, 30.0, 25.0, 28.0, 32.0, 35.0, 22.0, 24.0, 26.0, 29.0]
        rec = cfd_optimise(_cells(temps), ml_severity="warning")
        assert abs(rec["delta_t"] - (35.0 - 20.0)) < 0.01

    def test_ml_driven_flag_is_true(self):
        """UT-CFD-004l: ml_driven flag must be True in all responses."""
        rec = cfd_optimise(_cells([30.0] * 10), ml_severity="normal")
        assert rec.get("ml_driven") is True

    def test_single_cell_pack(self):
        """UT-CFD-004m: Engine must handle single-cell edge case."""
        rec = cfd_optimise(_cells([30.0]), ml_severity="normal")
        assert rec["severity"] == "normal"
        assert rec["delta_t"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# UT-ING-001 — normalise_temperature
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormaliseTemperature:

    def test_midpoint_normalises_to_half(self):
        """UT-ING-001a: Midpoint of [TEMP_MIN, TEMP_MAX] -> 0.5."""
        mid = (TEMP_MIN + TEMP_MAX) / 2
        assert abs(normalise_temperature(mid) - 0.5) < 1e-6

    def test_min_temp_normalises_to_zero(self):
        """UT-ING-001b: TEMP_MIN -> 0.0."""
        assert abs(normalise_temperature(TEMP_MIN) - 0.0) < 1e-9

    def test_max_temp_normalises_to_one(self):
        """UT-ING-001c: TEMP_MAX -> 1.0."""
        assert abs(normalise_temperature(TEMP_MAX) - 1.0) < 1e-9

    def test_result_always_in_unit_range(self):
        """UT-ING-001d: All in-range temps produce value in [0, 1]."""
        for t in range(0, 61, 5):
            r = normalise_temperature(float(t))
            assert 0.0 <= r <= 1.0

    def test_formula_min_max_normalization(self):
        """UT-ING-001e: formula = (T - min) / (max - min)."""
        for t in [15.0, 22.5, 35.0, 45.0]:
            expected = (t - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)
            assert abs(normalise_temperature(t) - expected) < 1e-6

    def test_reversibility(self):
        """UT-ING-001f: Denormalised value must recover original temperature."""
        for t in [15.0, 22.5, 30.0, 45.0, 55.0]:
            norm = normalise_temperature(t)
            recovered = norm * (TEMP_MAX - TEMP_MIN) + TEMP_MIN
            assert abs(recovered - t) < 1e-4

    def test_returns_float(self):
        """UT-ING-001g: Return type must be float."""
        assert isinstance(normalise_temperature(30.0), float)


# ═══════════════════════════════════════════════════════════════════════════════
# UT-ING-002 — enrich_payload
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnrichPayload:

    def _base_payload(self, temps):
        return {
            "tick": 1,
            "pack_id": "BTMS-PACK-001",
            "cells": [
                {"cell_id": i, "temperature": t, "voltage": 3.6, "current": 2.5, "soc": 90.0}
                for i, t in enumerate(temps)
            ],
        }

    def test_adds_temperature_norm_to_each_cell(self):
        """UT-ING-002a: temperature_norm field must be added to every cell."""
        enriched = enrich_payload(self._base_payload([28.0, 30.0, 32.0]))
        for cell in enriched["cells"]:
            assert "temperature_norm" in cell

    def test_temperature_norm_value_is_correct(self):
        """UT-ING-002b: temperature_norm value must match normalise_temperature."""
        enriched = enrich_payload(self._base_payload([35.0]))
        expected = normalise_temperature(35.0)
        assert abs(enriched["cells"][0]["temperature_norm"] - expected) < 1e-6

    def test_preserves_all_existing_cell_fields(self):
        """UT-ING-002c: Enrichment must not drop or mutate existing cell fields."""
        enriched = enrich_payload(self._base_payload([30.0, 40.0]))
        for cell in enriched["cells"]:
            assert "voltage" in cell and "current" in cell and "soc" in cell

    def test_preserves_top_level_fields(self):
        """UT-ING-002d: tick, pack_id must be preserved."""
        enriched = enrich_payload(self._base_payload([28.0]))
        assert enriched["tick"] == 1
        assert enriched["pack_id"] == "BTMS-PACK-001"

    def test_norms_are_finite_numbers(self):
        """UT-ING-002e: All norm values must be finite (no NaN/Inf)."""
        enriched = enrich_payload(self._base_payload([0.0, 15.0, 30.0, 45.0, 60.0]))
        for cell in enriched["cells"]:
            assert math.isfinite(cell["temperature_norm"])


# ═══════════════════════════════════════════════════════════════════════════════
# UT-CONC-001 — Constants & CONC_TABLE
# ═══════════════════════════════════════════════════════════════════════════════

class TestConstantsAndTable:

    def test_conc_table_has_three_entries(self):
        """UT-CONC-001a: CONC_TABLE must have exactly three keys."""
        assert set(CONC_TABLE.keys()) == {"low", "medium", "high"}

    def test_conc_table_values_ordered_correctly(self):
        """UT-CONC-001b: low < medium < high concentration."""
        assert CONC_TABLE["low"] < CONC_TABLE["medium"] < CONC_TABLE["high"]

    def test_re_min_less_than_re_max(self):
        """UT-CONC-001c: RE_MIN must be less than RE_MAX."""
        assert RE_MIN < RE_MAX

    def test_dh_is_1mm(self):
        """UT-CONC-001d: Hydraulic diameter must be 1 mm = 0.001 m."""
        assert abs(DH - 0.001) < 1e-9

    def test_temp_critical_is_45(self):
        """UT-CONC-001e: Critical temperature safety threshold is 45 C."""
        assert TEMP_CRITICAL == 45.0
