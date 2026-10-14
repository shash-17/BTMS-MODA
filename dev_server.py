"""
BTMS Local Dev Server — All-in-one (no Kafka, no Docker needed)
─────────────────────────────────────────────────────────────────
Runs the simulator + ML anomaly detector + AI engine in a single process.
Serves FastAPI on port 8000 so the Vite dashboard at localhost:5174
gets live telemetry, ML anomaly scores, and recommendations immediately.

Run:
    python3 dev_server.py
"""

import math
import random
import sys
import os
import threading
import time
from datetime import datetime

# Make ai_engine importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ai_engine"))
from anomaly_detector import BTMSAnomalyDetector

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ─── Physical constants ───────────────────────────────────────────────────────
DH = 0.001
RHO_WATER = 997.0
MU_WATER = 8.9e-4
K_WATER = 0.607
RHO_AL2O3 = 3960.0
TEMP_CRITICAL = 45.0
RE_MIN, RE_MAX = 400.0, 700.0
RE_TARGET_NORMAL = 450.0
RE_TARGET_SPIKE = 680.0
CONC_TABLE = {"low": 0.005, "medium": 0.015, "high": 0.030}

# ─── Simulator state ──────────────────────────────────────────────────────────
NUM_CELLS = 10
SPIKE_PROBABILITY = 0.15
soc = [100.0] * NUM_CELLS
tick_counter = 0

# ─── ML Anomaly Detector ──────────────────────────────────────────────────────
print("⏳  Bootstrapping IsolationForest anomaly detector...", flush=True)
detector = BTMSAnomalyDetector()
print(f"✓  ML model ready ({detector._bootstrap_n} bootstrap samples)", flush=True)

# ─── Shared state ─────────────────────────────────────────────────────────────
state_lock = threading.Lock()
latest_telemetry = None
latest_recommendation = None
latest_anomaly = None


# ══════════════════════════════════════════════════════════════════════════════
# Simulator functions
# ══════════════════════════════════════════════════════════════════════════════

def simulate_cell(cell_id: int) -> dict:
    global soc
    soc[cell_id] = max(0.0, soc[cell_id] - random.uniform(0.005, 0.02))
    voltage = 3.6 - (1 - soc[cell_id] / 100) * 0.5 + random.uniform(-0.05, 0.05)
    current = 2.5 + random.uniform(-0.3, 0.3)
    base_temp = 22.0 + (cell_id * 1.5) % 16.0
    temperature = base_temp + random.uniform(-1.0, 1.5)
    is_spike = False
    if random.random() < SPIKE_PROBABILITY:
        temperature = random.uniform(46.0, 58.0)
        is_spike = True
    return {
        "cell_id": cell_id,
        "voltage": round(voltage, 4),
        "current": round(current, 4),
        "temperature": round(temperature, 4),
        "temperature_norm": round(temperature / 60.0, 6),
        "soc": round(soc[cell_id], 2),
        "is_spike": is_spike,
    }


# ══════════════════════════════════════════════════════════════════════════════
# CFD heuristics (same as ai_engine/main.py)
# ══════════════════════════════════════════════════════════════════════════════

def nanofluid_properties(phi):
    return {
        "rho": phi * RHO_AL2O3 + (1 - phi) * RHO_WATER,
        "mu":  MU_WATER * math.exp(2.5 * phi),
        "k":   K_WATER * (1 + 3 * phi),
    }


def compute_flow_velocity(re_target, props):
    return (re_target * props["mu"]) / (props["rho"] * DH)


def compute_nusselt(re, pr):
    L = 0.1
    gz = re * pr * DH / L
    return round(3.66 + (0.065 * gz) / (1 + 0.04 * gz ** (2 / 3)), 3)


def cfd_optimise(cells, ml_severity="normal"):
    temps = [c["temperature"] for c in cells]
    max_temp = max(temps)
    avg_temp = sum(temps) / len(temps)
    delta_t = max(temps) - min(temps)
    hw_spike_cells = [c["cell_id"] for c in cells if c["temperature"] > TEMP_CRITICAL]

    # ML severity drives the decision (hardware spikes always override)
    if hw_spike_cells:
        re_target, severity, conc_key = RE_TARGET_SPIKE, "critical", "high"
    elif ml_severity == "critical":
        re_target, severity, conc_key = RE_TARGET_SPIKE, "critical", "high"
    elif ml_severity == "warning":
        re_target, severity, conc_key = RE_TARGET_NORMAL + 100.0, "warning", "medium"
    else:
        re_target, severity, conc_key = RE_TARGET_NORMAL, "normal", "low"

    re_target = max(RE_MIN, min(RE_MAX, re_target))
    phi = CONC_TABLE[conc_key]
    props = nanofluid_properties(phi)
    velocity = compute_flow_velocity(re_target, props)
    channel_area = math.pi * (DH / 2) ** 2
    flow_rate_ml_min = velocity * channel_area * 1e6 * 60
    CP_WATER = 4182.0
    pr = (props["mu"] * CP_WATER) / props["k"]
    nu = compute_nusselt(re_target, pr)
    htc = nu * props["k"] / DH

    return {
        "severity": severity,
        "ml_driven": True,
        "spike_cells": hw_spike_cells,
        "max_temp": round(max_temp, 2),
        "avg_temp": round(avg_temp, 2),
        "delta_t": round(delta_t, 2),
        "target_re": round(re_target, 1),
        "concentration_key": conc_key,
        "al2o3_vol_percent": round(phi * 100, 1),
        "flow_velocity_m_s": round(velocity, 6),
        "flow_rate_ml_min": round(flow_rate_ml_min, 4),
        "nusselt_number": nu,
        "heat_transfer_coeff_W_m2K": round(htc, 2),
        "nanofluid_density_kg_m3": round(props["rho"], 2),
        "nanofluid_viscosity_mPas": round(props["mu"] * 1000, 4),
        "nanofluid_conductivity_W_mK": round(props["k"], 4),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Background worker — simulate + compute every 1 second
# ══════════════════════════════════════════════════════════════════════════════

def simulation_worker():
    global tick_counter, latest_telemetry, latest_recommendation, latest_anomaly
    print("▶  Simulation worker started — generating telemetry every 1 s", flush=True)
    while True:
        cells = [simulate_cell(i) for i in range(NUM_CELLS)]
        payload = {
            "tick": tick_counter,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "pack_id": "BTMS-PACK-001",
            "cells": cells,
        }

        # ── ML anomaly detection ───────────────────────────────────────────────────
        detector.ingest(cells)
        anomaly_result = detector.detect(cells)
        ml_severity = anomaly_result.get("pack_severity", "normal")

        # ── CFD optimisation (ML-driven) ───────────────────────────────────────────
        rec = cfd_optimise(cells, ml_severity=ml_severity)

        with state_lock:
            latest_telemetry = payload
            latest_recommendation = rec
            latest_anomaly = anomaly_result

        # ── Console log ────────────────────────────────────────────────────────────────
        n_anom = len(anomaly_result.get("anomalous_cells", []))
        conf   = anomaly_result.get("pack_confidence", 0)
        spike_ids = [c["cell_id"] for c in cells if c["is_spike"]]
        if spike_ids:
            print(f"  [Tick {tick_counter:04d}] ⚠ SPIKE {spike_ids} | ML={ml_severity} conf={conf:.2f} | Re={rec['target_re']:.0f} | Al₂O₃={rec['al2o3_vol_percent']}%", flush=True)
        elif n_anom:
            print(f"  [Tick {tick_counter:04d}] 🔴 ML-ANOMALY cells={anomaly_result['anomalous_cells']} conf={conf:.2f} | {ml_severity}", flush=True)
        else:
            print(f"  [Tick {tick_counter:04d}] ✔ Tmax={rec['max_temp']}°C ΔT={rec['delta_t']}°C | ML={ml_severity} conf={conf:.2f}", flush=True)

        tick_counter += 1
        time.sleep(1.0)


# ══════════════════════════════════════════════════════════════════════════════
# FastAPI
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(title="BTMS Dev Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    t = threading.Thread(target=simulation_worker, daemon=True)
    t.start()


@app.get("/health")
def health():
    return {"service": "btms-dev-server", "status": "ok"}


@app.get("/recommendations")
def get_recommendations():
    with state_lock:
        if latest_recommendation is None:
            return {"status": "waiting", "message": "No telemetry yet"}
        return {"status": "ok", "recommendation": latest_recommendation}


@app.get("/telemetry/latest")
def get_latest_telemetry():
    with state_lock:
        if latest_telemetry is None:
            return {"status": "waiting", "message": "No telemetry yet"}
        return {"status": "ok", "telemetry": latest_telemetry}


@app.get("/anomaly")
def get_anomaly():
    with state_lock:
        if latest_anomaly is None:
            return {"status": "waiting", "message": "No telemetry yet",
                    "model": detector.status()}
        return {"status": "ok", "anomaly": latest_anomaly, "model": detector.status()}


@app.get("/anomaly/model")
def get_model_status():
    return {"status": "ok", "model": detector.status()}


if __name__ == "__main__":
    print("=" * 60)
    print("  BTMS Dev Server  →  http://localhost:8000")
    print("  Dashboard        →  http://localhost:5174")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
