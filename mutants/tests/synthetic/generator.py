"""
generator.py  — Synthetic Telemetry Data Generator for BTMS
─────────────────────────────────────────────────────────────────────
AI-driven synthetic data generation that produces realistic, statistically
diverse battery pack telemetry datasets for testing.

Generation strategies:
  1. RANDOM BASELINE       — pure statistical randomness (Monte Carlo)
  2. PHYSICS-CONSTRAINED   — Gaussian noise around physical models
  3. SCENARIO-DRIVEN       — named fault/operational scenarios
  4. ADVERSARIAL           — edge cases & boundary-condition stress data
  5. AUGMENTED             — interpolates between known scenarios

Each generated dataset is written as:
  tests/synthetic/generated/<strategy>_<timestamp>.json

Usage:
    python tests/synthetic/generator.py
    python tests/synthetic/generator.py --strategy all --ticks 200 --seed 42
    python tests/synthetic/generator.py --strategy adversarial --ticks 50
"""

import argparse
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Output directory ───────────────────────────────────────────────────────────
HERE       = Path(__file__).resolve().parent
OUTPUT_DIR = HERE / "generated"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Physical constants (mirror ai_engine/main.py) ─────────────────────────────
NUM_CELLS        = 10
NOMINAL_VOLTAGE  = 3.6      # V
NOMINAL_CURRENT  = 2.5      # A
BASE_TEMP_MIN    = 22.0     # °C
BASE_TEMP_MAX    = 38.0     # °C
SPIKE_TEMP_MIN   = 46.0     # °C
SPIKE_TEMP_MAX   = 58.0     # °C
TEMP_MIN_NORM    = 0.0
TEMP_MAX_NORM    = 60.0

TEMP_WARN_THRESH = 40.0
TEMP_CRIT_THRESH = 45.0

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _norm(temp: float) -> float:
    return round((temp - TEMP_MIN_NORM) / (TEMP_MAX_NORM - TEMP_MIN_NORM), 6)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _gaussian(mu: float, sigma: float, lo: float = None, hi: float = None) -> float:
    v = random.gauss(mu, sigma)
    if lo is not None and hi is not None:
        v = _clamp(v, lo, hi)
    return v


def _cell(cell_id: int, temperature: float, soc: float,
          voltage_noise: float = 0.05, current_noise: float = 0.3) -> dict:
    voltage = _clamp(
        NOMINAL_VOLTAGE - (1 - soc / 100) * 0.5 + random.uniform(-voltage_noise, voltage_noise),
        2.5, 4.2,
    )
    current = _clamp(
        NOMINAL_CURRENT + random.uniform(-current_noise, current_noise),
        0.5, 6.0,
    )
    is_spike = temperature > TEMP_CRIT_THRESH
    return {
        "cell_id":          cell_id,
        "voltage":          round(voltage, 4),
        "current":          round(current, 4),
        "temperature":      round(temperature, 4),
        "soc":              round(soc, 2),
        "is_spike":         is_spike,
        "temperature_norm": _norm(temperature),
    }


def _payload(tick: int, cells: list[dict], pack_id: str = "BTMS-PACK-001",
             metadata: dict = None) -> dict:
    return {
        "tick":      tick,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pack_id":   pack_id,
        "cells":     cells,
        **(metadata or {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Generation Strategies
# ─────────────────────────────────────────────────────────────────────────────

class BaseGenerator:
    """Abstract base — subclasses implement `generate_tick`."""

    name: str = "base"
    description: str = ""

    def __init__(self, seed: int = None):
        if seed is not None:
            random.seed(seed)
        self._soc = [100.0] * NUM_CELLS

    def _degrade_soc(self, cell_id: int) -> float:
        self._soc[cell_id] = _clamp(
            self._soc[cell_id] - random.uniform(0.005, 0.02), 0.0, 100.0
        )
        return self._soc[cell_id]

    def generate_tick(self, tick: int) -> dict:
        raise NotImplementedError

    def generate(self, num_ticks: int) -> list[dict]:
        return [self.generate_tick(t) for t in range(num_ticks)]


# ── 1. Random Baseline ─────────────────────────────────────────────────────────

class RandomBaselineGenerator(BaseGenerator):
    """
    Pure Monte Carlo — temperatures drawn uniformly from [BASE_MIN, BASE_MAX]
    with a 15% spike probability per cell per tick.
    """
    name        = "random_baseline"
    description = "Pure Monte Carlo: uniform random temps with 15% spike probability"

    def generate_tick(self, tick: int) -> dict:
        cells = []
        for i in range(NUM_CELLS):
            soc  = self._degrade_soc(i)
            if random.random() < 0.15:
                temp = random.uniform(SPIKE_TEMP_MIN, SPIKE_TEMP_MAX)
            else:
                temp = random.uniform(BASE_TEMP_MIN, BASE_TEMP_MAX)
            cells.append(_cell(i, temp, soc))
        return _payload(tick, cells, metadata={"generator": self.name})


# ── 2. Physics-Constrained ────────────────────────────────────────────────────

class PhysicsConstrainedGenerator(BaseGenerator):
    """
    Gaussian noise around a physics-grounded thermal model.
    Each cell has a base temperature determined by position (heat gradient)
    and time (slow heating/cooling cycles).
    """
    name        = "physics_constrained"
    description = "Gaussian noise around position-based thermal gradient model"

    def __init__(self, seed: int = None, cycle_period: int = 60):
        super().__init__(seed)
        self.cycle_period = cycle_period     # ticks for one heat-cool cycle

    def generate_tick(self, tick: int) -> dict:
        # Slow sinusoidal thermal cycle (simulates charge/discharge)
        cycle_phase = 2 * math.pi * tick / self.cycle_period
        pack_offset = 4.0 * math.sin(cycle_phase)   # ±4°C swing

        cells = []
        for i in range(NUM_CELLS):
            soc = self._degrade_soc(i)
            # Spatial gradient: cell position drives base temperature
            base = BASE_TEMP_MIN + (i / (NUM_CELLS - 1)) * (BASE_TEMP_MAX - BASE_TEMP_MIN)
            temp = _gaussian(base + pack_offset, sigma=1.5, lo=10.0, hi=55.0)
            cells.append(_cell(i, temp, soc, voltage_noise=0.02, current_noise=0.15))
        return _payload(tick, cells, metadata={"generator": self.name, "pack_offset": round(pack_offset, 2)})


# ── 3. Scenario-Driven ────────────────────────────────────────────────────────

class ScenarioDrivenGenerator(BaseGenerator):
    """
    Named fault and operational scenarios that repeat / cycle across ticks.
    Scenarios: nominal, warm_up, single_spike, multi_spike, recovery, balanced_cooling
    """
    name        = "scenario_driven"
    description = "Named operational/fault scenarios cycling across ticks"

    SCENARIOS = [
        "nominal",
        "warm_up",
        "single_spike",
        "multi_spike",
        "recovery",
        "balanced_cooling",
    ]

    def __init__(self, seed: int = None, scenario_duration: int = 20):
        super().__init__(seed)
        self.scenario_duration = scenario_duration

    def _get_scenario(self, tick: int) -> str:
        idx = (tick // self.scenario_duration) % len(self.SCENARIOS)
        return self.SCENARIOS[idx]

    def _temps_for_scenario(self, scenario: str) -> list[float]:
        if scenario == "nominal":
            return [_gaussian(28.0, 1.5, 20.0, 38.0) for _ in range(NUM_CELLS)]

        elif scenario == "warm_up":
            # Gradually increasing temps 30-42°C
            return [_gaussian(30.0 + i * 1.2, 1.0, 25.0, 44.0) for i in range(NUM_CELLS)]

        elif scenario == "single_spike":
            temps = [_gaussian(30.0, 1.5, 22.0, 38.0) for _ in range(NUM_CELLS)]
            spike_idx = random.randint(0, NUM_CELLS - 1)
            temps[spike_idx] = random.uniform(SPIKE_TEMP_MIN, SPIKE_TEMP_MAX)
            return temps

        elif scenario == "multi_spike":
            temps = [_gaussian(32.0, 2.0, 22.0, 40.0) for _ in range(NUM_CELLS)]
            num_spikes = random.randint(2, 4)
            indices = random.sample(range(NUM_CELLS), num_spikes)
            for idx in indices:
                temps[idx] = random.uniform(SPIKE_TEMP_MIN, SPIKE_TEMP_MAX)
            return temps

        elif scenario == "recovery":
            # Temps cooling down from warning zone back to nominal
            return [_gaussian(38.0, 2.0, 28.0, 44.0) for _ in range(NUM_CELLS)]

        elif scenario == "balanced_cooling":
            # Near-uniform cooling — minimal ΔT
            base = _gaussian(25.0, 1.0, 20.0, 30.0)
            return [_gaussian(base, 0.3, 18.0, 32.0) for _ in range(NUM_CELLS)]

        return [30.0] * NUM_CELLS

    def generate_tick(self, tick: int) -> dict:
        scenario = self._get_scenario(tick)
        temps    = self._temps_for_scenario(scenario)
        cells    = [_cell(i, temps[i], self._degrade_soc(i)) for i in range(NUM_CELLS)]
        return _payload(tick, cells, metadata={"generator": self.name, "scenario": scenario})


# ── 4. Adversarial / Edge-Case ────────────────────────────────────────────────

class AdversarialGenerator(BaseGenerator):
    """
    Deliberately extreme boundary cases for robustness testing:
    • All cells at exactly TEMP_CRITICAL
    • Massive ΔT (one near-zero, one near-max)
    • All cells at 0 °C (dead cold pack)
    • All cells at 59.9 °C (just below physical max)
    • Single-cell isolation: only one cell active
    • Voltage and current at absolute limits
    """
    name        = "adversarial"
    description = "Boundary-condition stress data for robustness testing"

    CASES = [
        "all_at_critical",
        "max_delta_t",
        "dead_cold",
        "near_max_heat",
        "single_active",
        "all_warning_border",
        "alternating_spike",
        "soc_depleted",
    ]

    def _get_case(self, tick: int) -> str:
        return self.CASES[tick % len(self.CASES)]

    def generate_tick(self, tick: int) -> dict:
        case  = self._get_case(tick)
        cells = []

        if case == "all_at_critical":
            for i in range(NUM_CELLS):
                cells.append(_cell(i, TEMP_CRIT_THRESH + 0.01, 80.0))

        elif case == "max_delta_t":
            for i in range(NUM_CELLS):
                temp = SPIKE_TEMP_MAX if i == 0 else BASE_TEMP_MIN
                cells.append(_cell(i, temp, 80.0))

        elif case == "dead_cold":
            for i in range(NUM_CELLS):
                cells.append(_cell(i, 0.1, 100.0, voltage_noise=0.001, current_noise=0.01))

        elif case == "near_max_heat":
            for i in range(NUM_CELLS):
                cells.append(_cell(i, 59.9, 20.0))

        elif case == "single_active":
            for i in range(NUM_CELLS):
                temp = 35.0 if i == 0 else BASE_TEMP_MIN
                soc  = self._degrade_soc(i)
                cells.append(_cell(i, temp, soc))

        elif case == "all_warning_border":
            for i in range(NUM_CELLS):
                cells.append(_cell(i, 40.1, 70.0))

        elif case == "alternating_spike":
            for i in range(NUM_CELLS):
                temp = SPIKE_TEMP_MIN + 2 if i % 2 == 0 else 28.0
                cells.append(_cell(i, temp, 75.0))

        elif case == "soc_depleted":
            for i in range(NUM_CELLS):
                cells.append(_cell(i, 32.0, 2.0))

        return _payload(tick, cells, metadata={"generator": self.name, "case": case})


# ── 5. Augmented / Interpolated ────────────────────────────────────────────────

class AugmentedGenerator(BaseGenerator):
    """
    Interpolates between known start/end states using linear or sinusoidal
    blending to create smooth transition datasets — useful for testing
    the dashboard's real-time rendering and AI engine's reaction latency.
    """
    name        = "augmented"
    description = "Smooth linear interpolation between nominal and critical states"

    def __init__(self, seed: int = None, num_ticks: int = 100):
        super().__init__(seed)
        self._total = num_ticks

    def generate_tick(self, tick: int) -> dict:
        # α goes 0→1→0 over the total ticks (up/down arc)
        alpha = abs(math.sin(math.pi * tick / max(self._total - 1, 1)))
        cells = []
        for i in range(NUM_CELLS):
            soc       = self._degrade_soc(i)
            temp_low  = BASE_TEMP_MIN + (i / (NUM_CELLS - 1)) * 10
            temp_high = SPIKE_TEMP_MIN + (i / (NUM_CELLS - 1)) * 6
            temp      = temp_low + alpha * (temp_high - temp_low)
            temp      = _gaussian(temp, 0.8, 10.0, 59.0)
            cells.append(_cell(i, temp, soc, voltage_noise=0.03))
        return _payload(
            tick, cells,
            metadata={"generator": self.name, "alpha": round(alpha, 4)},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

GENERATORS = {
    "random_baseline":     RandomBaselineGenerator,
    "physics_constrained": PhysicsConstrainedGenerator,
    "scenario_driven":     ScenarioDrivenGenerator,
    "adversarial":         AdversarialGenerator,
    "augmented":           AugmentedGenerator,
}


def run_generator(
    strategy: str,
    num_ticks: int = 100,
    seed: int      = 42,
    quiet: bool    = False,
) -> Path:
    cls = GENERATORS[strategy]
    if strategy == "augmented":
        gen = cls(seed=seed, num_ticks=num_ticks)
    else:
        gen = cls(seed=seed)

    if not quiet:
        print(f"  ▶  [{strategy}]  {cls.description}")
        print(f"     Generating {num_ticks} ticks …", end=" ", flush=True)

    t0   = time.perf_counter()
    data = gen.generate(num_ticks)
    dt   = time.perf_counter() - t0

    # Compute quick statistics for provenance
    all_temps = [c["temperature"] for tick in data for c in tick["cells"]]
    stats = {
        "strategy":    strategy,
        "description": cls.description,
        "seed":        seed,
        "num_ticks":   num_ticks,
        "num_cells":   NUM_CELLS,
        "total_samples": len(all_temps),
        "temp_min":    round(min(all_temps), 4),
        "temp_max":    round(max(all_temps), 4),
        "temp_mean":   round(sum(all_temps) / len(all_temps), 4),
        "spike_count": sum(1 for t in all_temps if t > TEMP_CRIT_THRESH),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation_ms": round(dt * 1000, 2),
    }

    output = {
        "provenance": stats,
        "ticks":      data,
    }

    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"{strategy}_{ts}.json"
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    if not quiet:
        print(f"done  ({dt*1000:.0f} ms)")
        print(f"     Samples : {stats['total_samples']}  |  "
              f"Tmin={stats['temp_min']}°C  Tmax={stats['temp_max']}°C  "
              f"Spikes={stats['spike_count']}")
        print(f"     Saved   → {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}\n")

    return path


def main():
    parser = argparse.ArgumentParser(description="BTMS Synthetic Telemetry Generator")
    parser.add_argument(
        "--strategy",
        default="all",
        choices=list(GENERATORS.keys()) + ["all"],
        help="Generation strategy (default: all)",
    )
    parser.add_argument("--ticks",  type=int, default=100, help="Ticks per dataset (default: 100)")
    parser.add_argument("--seed",   type=int, default=42,  help="Random seed (default: 42)")
    parser.add_argument("--quiet",  action="store_true",   help="Suppress progress output")
    args = parser.parse_args()

    strategies = list(GENERATORS.keys()) if args.strategy == "all" else [args.strategy]

    print("\n" + "═" * 65)
    print("  BTMS — Synthetic Telemetry Data Generator")
    print("  AI-driven multi-strategy data fabrication")
    print("═" * 65 + "\n")

    paths = []
    for s in strategies:
        path = run_generator(s, num_ticks=args.ticks, seed=args.seed, quiet=args.quiet)
        paths.append(path)

    print("═" * 65)
    print(f"  ✓  {len(paths)} dataset(s) written to: {OUTPUT_DIR}")
    print("═" * 65 + "\n")


if __name__ == "__main__":
    main()
