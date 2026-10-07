"""
BTMS Alert Service
─────────────────────────────────────────────────────────────────────
Event-driven consumer of the 'btms_alerts' Kafka topic (published by the
AI engine). Persists every alert to SQLite and exposes a REST API for
querying alerts and aggregate statistics.
"""

import json
import logging
import os
import sqlite3
import threading
import time

from confluent_kafka import Consumer, KafkaException
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
ALERTS_TOPIC = os.getenv("KAFKA_ALERTS_TOPIC", "btms_alerts")
GROUP_ID = os.getenv("KAFKA_GROUP_ID", "btms-alert-service")
DB_PATH = os.getenv("DB_PATH", "/data/alerts.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [alert-service] %(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_db_lock = threading.Lock()
_consumer_ok = False


def _db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


conn = _db()
conn.execute(
    """CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tick INTEGER, pack_id TEXT, timestamp TEXT, severity TEXT,
        anomalous_cells TEXT, confidence REAL, max_temp REAL, delta_t REAL,
        target_re REAL, al2o3_vol_percent REAL,
        kafka_partition INTEGER, kafka_offset INTEGER
    )"""
)
conn.commit()


def store(evt: dict, partition: int, offset: int) -> None:
    with _db_lock:
        conn.execute(
            "INSERT INTO alerts (tick, pack_id, timestamp, severity, anomalous_cells, confidence, max_temp,"
            " delta_t, target_re, al2o3_vol_percent, kafka_partition, kafka_offset)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                evt.get("tick"), evt.get("pack_id"), evt.get("timestamp"), evt.get("severity"),
                json.dumps(evt.get("anomalous_cells", [])), evt.get("confidence"), evt.get("max_temp"),
                evt.get("delta_t"), evt.get("target_re"), evt.get("al2o3_vol_percent"), partition, offset,
            ),
        )
        conn.commit()


def consume_loop() -> None:
    global _consumer_ok
    consumer = None
    logger.info("Alert consumer starting — topic '%s'", ALERTS_TOPIC)
    while True:
        try:
            if consumer is None:
                consumer = Consumer({
                    "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
                    "group.id": GROUP_ID,
                    "auto.offset.reset": "earliest",
                    "enable.auto.commit": True,
                })
                consumer.subscribe([ALERTS_TOPIC])
            msg = consumer.poll(2.0)
            if msg is None:
                continue
            if msg.error():
                # topic may not exist until the first alert is published
                if "UNKNOWN_TOPIC_OR_PART" in str(msg.error()):
                    time.sleep(2)
                    continue
                raise KafkaException(msg.error())
            _consumer_ok = True
            store(json.loads(msg.value().decode("utf-8")), msg.partition(), msg.offset())
        except KafkaException as e:
            _consumer_ok = False
            logger.error("Kafka error: %s — retrying in 3 s", e)
            time.sleep(3)
        except Exception as e:
            logger.exception("Bad alert message skipped: %s", e)


app = FastAPI(title="BTMS Alert Service", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@app.on_event("startup")
def startup():
    threading.Thread(target=consume_loop, daemon=True).start()


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["anomalous_cells"] = json.loads(d["anomalous_cells"] or "[]")
    return d


@app.get("/health")
def health():
    with _db_lock:
        total = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    return {"service": "alert-service", "status": "ok", "kafka_consumer": _consumer_ok, "alerts_stored": total}


@app.get("/alerts")
def alerts(limit: int = Query(50, ge=1, le=500), severity: str | None = None):
    sql, args = "SELECT * FROM alerts", []
    if severity:
        sql += " WHERE severity = ?"
        args.append(severity)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with _db_lock:
        return [_row(r) for r in conn.execute(sql, args).fetchall()]


@app.get("/alerts/stats")
def stats():
    with _db_lock:
        by_sev = {r["severity"]: r["n"] for r in conn.execute("SELECT severity, COUNT(*) n FROM alerts GROUP BY severity")}
        agg = conn.execute("SELECT COUNT(*) n, AVG(max_temp) avg_tmax, MAX(max_temp) peak_tmax, AVG(confidence) avg_conf FROM alerts").fetchone()
        cell_counts: dict = {}
        for r in conn.execute("SELECT anomalous_cells FROM alerts"):
            for c in json.loads(r["anomalous_cells"] or "[]"):
                cell_counts[c] = cell_counts.get(c, 0) + 1
    return {
        "total": agg["n"],
        "by_severity": by_sev,
        "avg_max_temp": round(agg["avg_tmax"], 2) if agg["avg_tmax"] is not None else None,
        "peak_max_temp": agg["peak_tmax"],
        "avg_confidence": round(agg["avg_conf"], 3) if agg["avg_conf"] is not None else None,
        "alerts_per_cell": dict(sorted(cell_counts.items())),
    }
