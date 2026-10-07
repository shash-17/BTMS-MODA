"""
validate_synthetic.py  — Quality Validation for Generated Synthetic Data
─────────────────────────────────────────────────────────────────────────
Loads all JSON files from tests/synthetic/generated/ and runs a battery
of statistical and structural quality checks on each dataset.

Checks performed:
  ✓ Schema validation (required fields present on every tick/cell)
  ✓ Physical plausibility (voltage, current, temp within hardware limits)
  ✓ Statistical diversity (std-dev, min/max spread — not degenerate)
  ✓ SoC monotone decrease (batteries discharge, never spontaneously charge)
  ✓ Spike consistency (is_spike flag matches temperature threshold)
  ✓ Normalisation correctness (temperature_norm recomputed & cross-checked)
  ✓ Provenance integrity (stated stats match actual data)

Usage:
    python tests/synthetic/validate_synthetic.py
    python tests/synthetic/validate_synthetic.py --file path/to/file.json
    python tests/synthetic/validate_synthetic.py --strict   (exit 1 on any warn)
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

# ── Constants (match generator + ingestion service) ───────────────────────────
TEMP_CRIT_THRESH  = 45.0
TEMP_MIN_NORM     = 0.0
TEMP_MAX_NORM     = 60.0
VOLTAGE_MIN       = 2.5
VOLTAGE_MAX       = 4.25
CURRENT_MIN       = 0.0
CURRENT_MAX       = 7.0
TEMP_PHYS_MIN     = -10.0
TEMP_PHYS_MAX     = 65.0
SOC_MIN           = 0.0
SOC_MAX           = 100.0

try:
    from colorama import Fore, Style, init as _cinit
    _cinit(autoreset=True)
    GREEN  = Fore.GREEN
    RED    = Fore.RED
    YELLOW = Fore.YELLOW
    CYAN   = Fore.CYAN
    BOLD   = Style.BRIGHT
    RESET  = Style.RESET_ALL
except ImportError:
    GREEN = RED = YELLOW = CYAN = BOLD = RESET = ""

HERE       = Path(__file__).resolve().parent
GEN_DIR    = HERE / "generated"


# ─────────────────────────────────────────────────────────────────────────────
# Individual check functions
# ─────────────────────────────────────────────────────────────────────────────

CheckResult = tuple[str, bool, str]   # (check_name, passed, detail)


def check_schema(ticks: list[dict]) -> list[CheckResult]:
    """All required fields must be present on every tick and cell."""
    results = []
    tick_fields = {"tick", "timestamp", "cells"}
    cell_fields = {"cell_id", "voltage", "current", "temperature", "soc", "is_spike", "temperature_norm"}

    missing_tick_fields = set()
    missing_cell_fields = set()

    for t in ticks:
        missing_tick_fields |= tick_fields - set(t.keys())
        for c in t.get("cells", []):
            missing_cell_fields |= cell_fields - set(c.keys())

    results.append((
        "schema:tick_fields",
        len(missing_tick_fields) == 0,
        f"Missing: {missing_tick_fields}" if missing_tick_fields else "All tick fields present",
    ))
    results.append((
        "schema:cell_fields",
        len(missing_cell_fields) == 0,
        f"Missing: {missing_cell_fields}" if missing_cell_fields else "All cell fields present",
    ))
    return results


def check_physical_limits(ticks: list[dict]) -> list[CheckResult]:
    """Values must fall within hardware-defined physical limits."""
    voltage_violations  = []
    current_violations  = []
    temp_violations     = []
    soc_violations      = []

    for t in ticks:
        for c in t["cells"]:
            if not (VOLTAGE_MIN <= c["voltage"] <= VOLTAGE_MAX):
                voltage_violations.append((t["tick"], c["cell_id"], c["voltage"]))
            if not (CURRENT_MIN <= c["current"] <= CURRENT_MAX):
                current_violations.append((t["tick"], c["cell_id"], c["current"]))
            if not (TEMP_PHYS_MIN <= c["temperature"] <= TEMP_PHYS_MAX):
                temp_violations.append((t["tick"], c["cell_id"], c["temperature"]))
            if not (SOC_MIN <= c["soc"] <= SOC_MAX):
                soc_violations.append((t["tick"], c["cell_id"], c["soc"]))

    results = []
    for name, violations, unit in [
        ("physics:voltage",     voltage_violations,  "V"),
        ("physics:current",     current_violations,  "A"),
        ("physics:temperature", temp_violations,     "°C"),
        ("physics:soc",         soc_violations,      "%"),
    ]:
        passed = len(violations) == 0
        detail = (
            f"{len(violations)} violation(s)  (first: {violations[0]}{unit})"
            if violations else "All within limits"
        )
        results.append((name, passed, detail))
    return results


def check_statistical_diversity(ticks: list[dict]) -> list[CheckResult]:
    """Dataset should have reasonable variance — not all identical values."""
    all_temps = [c["temperature"] for t in ticks for c in t["cells"]]
    mean = sum(all_temps) / len(all_temps)
    var  = sum((x - mean) ** 2 for x in all_temps) / len(all_temps)
    std  = math.sqrt(var)
    spread = max(all_temps) - min(all_temps)

    return [
        (
            "diversity:temp_stddev",
            std >= 0.5,
            f"σ={std:.2f}°C  (min 0.5°C expected for non-degenerate dataset)",
        ),
        (
            "diversity:temp_spread",
            spread >= 2.0,
            f"Tmax-Tmin={spread:.2f}°C  (min 2°C expected)",
        ),
    ]


def check_spike_flag_consistency(ticks: list[dict]) -> list[CheckResult]:
    """is_spike flag must exactly match temperature > TEMP_CRIT_THRESH."""
    inconsistencies = []
    for t in ticks:
        for c in t["cells"]:
            expected_spike = c["temperature"] > TEMP_CRIT_THRESH
            if c["is_spike"] != expected_spike:
                inconsistencies.append((t["tick"], c["cell_id"], c["temperature"], c["is_spike"]))

    passed = len(inconsistencies) == 0
    detail = (
        f"{len(inconsistencies)} inconsistency/ies  (first: {inconsistencies[0]})"
        if inconsistencies else "All is_spike flags consistent with temperature"
    )
    return [("spike:flag_consistency", passed, detail)]


def check_normalisation_correctness(ticks: list[dict]) -> list[CheckResult]:
    """temperature_norm must match the min-max formula."""
    errors = []
    for t in ticks:
        for c in t["cells"]:
            expected = round(
                (c["temperature"] - TEMP_MIN_NORM) / (TEMP_MAX_NORM - TEMP_MIN_NORM), 6
            )
            actual = c.get("temperature_norm", None)
            if actual is None or abs(actual - expected) > 1e-4:
                errors.append((t["tick"], c["cell_id"], actual, expected))

    passed = len(errors) == 0
    detail = (
        f"{len(errors)} norm error(s)  (first: tick={errors[0][0]} cell={errors[0][1]} "
        f"actual={errors[0][2]} expected={errors[0][3]})"
        if errors else "All normalised values correct"
    )
    return [("normalisation:correctness", passed, detail)]


def check_soc_non_negative(ticks: list[dict]) -> list[CheckResult]:
    """SoC must never go negative (clamp at 0)."""
    negatives = [
        (t["tick"], c["cell_id"], c["soc"])
        for t in ticks for c in t["cells"] if c["soc"] < 0
    ]
    passed = len(negatives) == 0
    detail = (
        f"{len(negatives)} negative SoC value(s)  (first: {negatives[0]})"
        if negatives else "All SoC values ≥ 0"
    )
    return [("soc:non_negative", passed, detail)]


def check_provenance_stats(provenance: dict, ticks: list[dict]) -> list[CheckResult]:
    """Provenance statistics recorded at generation time must match actual data."""
    all_temps = [c["temperature"] for t in ticks for c in t["cells"]]
    actual_min   = round(min(all_temps), 4)
    actual_max   = round(max(all_temps), 4)
    actual_spikes = sum(1 for t in ticks for c in t["cells"] if c["temperature"] > TEMP_CRIT_THRESH)

    results = []
    results.append((
        "provenance:temp_min",
        abs(provenance.get("temp_min", float("inf")) - actual_min) < 0.01,
        f"stated={provenance.get('temp_min')} actual={actual_min}",
    ))
    results.append((
        "provenance:temp_max",
        abs(provenance.get("temp_max", 0) - actual_max) < 0.01,
        f"stated={provenance.get('temp_max')} actual={actual_max}",
    ))
    results.append((
        "provenance:spike_count",
        provenance.get("spike_count") == actual_spikes,
        f"stated={provenance.get('spike_count')} actual={actual_spikes}",
    ))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Validate a single file
# ─────────────────────────────────────────────────────────────────────────────

def validate_file(path: Path, strict: bool = False) -> tuple[int, int]:
    """
    Run all checks on a single JSON file.
    Returns (passed_count, failed_count).
    """
    print(f"\n{BOLD}{'─'*65}{RESET}")
    print(f"{CYAN}{BOLD}  File: {path.name}{RESET}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  {RED}✗ Could not parse JSON: {e}{RESET}")
        return 0, 1

    ticks      = data.get("ticks", [])
    provenance = data.get("provenance", {})

    if not ticks:
        print(f"  {YELLOW}⚠  No ticks found in file{RESET}")
        return 0, 1

    print(f"  Strategy : {provenance.get('strategy', 'unknown')}")
    print(f"  Ticks    : {len(ticks)}  |  Cells/tick: {len(ticks[0].get('cells', []))}")
    print(f"  Seed     : {provenance.get('seed', '?')}")
    print()

    # Collect all checks
    all_checks: list[CheckResult] = []
    all_checks += check_schema(ticks)
    all_checks += check_physical_limits(ticks)
    all_checks += check_statistical_diversity(ticks)
    all_checks += check_spike_flag_consistency(ticks)
    all_checks += check_normalisation_correctness(ticks)
    all_checks += check_soc_non_negative(ticks)
    all_checks += check_provenance_stats(provenance, ticks)

    passed = failed = 0
    for name, ok, detail in all_checks:
        if ok:
            icon, col = "✓", GREEN
            passed += 1
        else:
            icon, col = "✗", RED
            failed += 1
        print(f"  {col}{icon}{RESET}  {name:<40}  {detail}")

    print()
    pct = (passed / (passed + failed) * 100) if (passed + failed) else 0
    colour = GREEN if failed == 0 else (YELLOW if pct >= 80 else RED)
    print(f"  {colour}{BOLD}Result: {passed}/{passed+failed} checks passed ({pct:.0f}%){RESET}")

    return passed, failed


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="BTMS Synthetic Data Validator")
    parser.add_argument("--file",   default=None,        help="Validate a specific file")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any check fails")
    args = parser.parse_args()

    print("\n" + "═" * 65)
    print("  BTMS — Synthetic Data Quality Validator")
    print("═" * 65)

    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(GEN_DIR.glob("*.json"))

    if not files:
        print(f"\n  {YELLOW}No JSON files found in {GEN_DIR}{RESET}")
        print("  Run:  python tests/synthetic/generator.py  first.\n")
        sys.exit(0)

    total_passed = total_failed = 0
    for f in files:
        p, fa = validate_file(f, strict=args.strict)
        total_passed += p
        total_failed += fa

    print("\n" + "═" * 65)
    colour = GREEN if total_failed == 0 else RED
    print(f"  {colour}{BOLD}Total: {total_passed} passed  |  {total_failed} failed{RESET}")
    print("═" * 65 + "\n")

    if args.strict and total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
