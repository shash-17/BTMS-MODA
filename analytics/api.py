"""
BTMS Analytics API
─────────────────────────────────────────────────────────────────────
Serves batch-style analytics (pandas + PyArrow) over the Parquet data lake
written by the Spark Structured Streaming job.
"""

import glob
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

LAKE = os.getenv("LAKE_PATH", "/data/lake")
SPIKE_TEMP_C = 45.0
RAW_TAIL_ROWS = 100_000   # cap rows scanned from the raw layer

app = FastAPI(title="BTMS Analytics API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


# ─── Lake helpers ─────────────────────────────────────────────────────────────

def _files(layer: str) -> list:
    return sorted(glob.glob(os.path.join(LAKE, layer, "**", "*.parquet"), recursive=True), key=os.path.getmtime)


def _read(layer: str, tail_files: int = 200) -> pd.DataFrame:
    files = _files(layer)[-tail_files:]
    if not files:
        return pd.DataFrame()
    frames = []
    for f in files:
        try:
            frames.append(pd.read_parquet(f))
        except Exception:
            continue   # file still being written
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _raw(minutes: int) -> pd.DataFrame:
    df = _read("raw", tail_files=400)
    if df.empty:
        return df
    df["event_time"] = pd.to_datetime(df["event_time"], utc=True)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    df = df[df["event_time"] >= cutoff]
    return df.tail(RAW_TAIL_ROWS)


def _iso(df: pd.DataFrame, cols) -> pd.DataFrame:
    for c in cols:
        df[c] = pd.to_datetime(df[c], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return df


def _clean(df: pd.DataFrame) -> list:
    return df.replace({np.nan: None}).to_dict(orient="records")


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    layers = {l: len(_files(l)) for l in ("raw", "cell_metrics", "pack_metrics")}
    return {"service": "analytics-api", "status": "ok", "lake_files": layers, "lake_ready": layers["raw"] > 0}


@app.get("/summary")
def summary(minutes: int = Query(15, ge=1, le=1440)):
    """Headline KPIs computed over the recent raw layer."""
    raw = _raw(minutes)
    if raw.empty:
        return {"ready": False, "window_minutes": minutes}
    by_cell = raw.groupby("cell_id")["temperature"].mean()
    per_tick = raw.groupby("tick")["temperature"].agg(["max", "min"])
    delta = (per_tick["max"] - per_tick["min"])
    return {
        "ready": True,
        "window_minutes": minutes,
        "readings": int(len(raw)),
        "ticks": int(raw["tick"].nunique()),
        "spike_rate_pct": round(float((raw["temperature"] > SPIKE_TEMP_C).mean() * 100), 2),
        "temp_mean": round(float(raw["temperature"].mean()), 2),
        "temp_p95": round(float(raw["temperature"].quantile(0.95)), 2),
        "temp_p99": round(float(raw["temperature"].quantile(0.99)), 2),
        "delta_t_mean": round(float(delta.mean()), 2),
        "delta_t_p95": round(float(delta.quantile(0.95)), 2),
        "uniformity_compliance_pct": round(float((delta < 5.0).mean() * 100), 2),
        "hottest_cell": int(by_cell.idxmax()),
        "coolest_cell": int(by_cell.idxmin()),
        "soc_mean": round(float(raw["soc"].mean()), 2),
    }


@app.get("/pack-trend")
def pack_trend(minutes: int = Query(15, ge=1, le=1440)):
    """10 s tumbling-window pack metrics (Gold layer)."""
    df = _read("pack_metrics")
    if df.empty:
        return []
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    df = df[df["window_start"] >= datetime.now(timezone.utc) - timedelta(minutes=minutes)]
    df = df.sort_values("window_start").drop_duplicates("window_start")
    return _clean(_iso(df, ["window_start", "window_end"]))


@app.get("/cells")
def cells(minutes: int = Query(15, ge=1, le=1440)):
    """Per-cell statistics and a composite thermal-risk ranking."""
    raw = _raw(minutes)
    if raw.empty:
        return []
    g = raw.groupby("cell_id")
    out = pd.DataFrame({
        "mean_temp": g["temperature"].mean(),
        "std_temp": g["temperature"].std(),
        "p95_temp": g["temperature"].quantile(0.95),
        "max_temp": g["temperature"].max(),
        "spike_rate_pct": g["temperature"].apply(lambda s: (s > SPIKE_TEMP_C).mean() * 100),
        "avg_voltage": g["voltage"].mean(),
        "avg_soc": g["soc"].mean(),
        "samples": g.size(),
    }).reset_index()
    # Risk score: 0-100, weighted blend of spike rate, p95 temperature and variability
    out["risk_score"] = (
        0.5 * out["spike_rate_pct"].clip(0, 100)
        + 0.35 * ((out["p95_temp"] - 25) / 30 * 100).clip(0, 100)
        + 0.15 * (out["std_temp"].fillna(0) / 10 * 100).clip(0, 100)
    )
    out = out.sort_values("risk_score", ascending=False).round(2)
    out["rank"] = range(1, len(out) + 1)
    return _clean(out)


@app.get("/correlation")
def correlation(minutes: int = Query(15, ge=1, le=1440)):
    """Pearson correlation matrix across temperature, voltage, current and SoC."""
    raw = _raw(minutes)
    cols = ["temperature", "voltage", "current", "soc"]
    if len(raw) < 10:
        return {"columns": cols, "matrix": []}
    corr = raw[cols].corr().fillna(0).round(3)
    return {"columns": cols, "matrix": corr.values.tolist()}


@app.get("/distribution")
def distribution(minutes: int = Query(15, ge=1, le=1440), bins: int = Query(14, ge=4, le=40)):
    """Temperature histogram of recent readings."""
    raw = _raw(minutes)
    if raw.empty:
        return {"bins": [], "counts": []}
    counts, edges = np.histogram(raw["temperature"], bins=bins)
    return {"bins": [round(float(e), 1) for e in edges[:-1]], "bin_width": round(float(edges[1] - edges[0]), 2), "counts": counts.tolist()}


@app.get("/anomalies")
def anomalies(limit: int = Query(25, ge=1, le=200)):
    """Most recent pack windows containing a thermal spike or ΔT violation."""
    df = _read("pack_metrics")
    if df.empty:
        return []
    df = df[(df["spike_readings"] > 0) | (df["delta_t"] >= 5.0)]
    df = df.sort_values("window_start", ascending=False).drop_duplicates("window_start").head(limit)
    return _clean(_iso(df, ["window_start", "window_end"]).round(2))
