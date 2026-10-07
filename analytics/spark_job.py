"""
BTMS Big-Data Streaming Analytics (Apache Spark Structured Streaming)
─────────────────────────────────────────────────────────────────────
Consumes the Kafka 'battery_stream' topic (independent consumer group via
Spark) and writes a Parquet data lake with three layers:

  lake/raw/            Bronze – every cell reading, flattened, partitioned by date
  lake/cell_metrics/   Silver – 30 s sliding windows (10 s slide) per cell:
                       avg/min/max/stddev temperature, voltage, current, SoC,
                       spike count
  lake/pack_metrics/   Gold   – 10 s tumbling windows per pack: Tmax, Tmin, Tavg,
                       ΔT (thermal uniformity), spiking-cell count

Windowed layers use a 10 s event-time watermark, so each window is appended
once, after it closes.
"""

import os

from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import (
    ArrayType, BooleanType, DoubleType, IntegerType, LongType, StringType, StructField, StructType,
)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "message-broker:19092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "battery_stream")
LAKE = os.getenv("LAKE_PATH", "/data/lake")
CHECKPOINTS = os.path.join(LAKE, "_checkpoints")
TRIGGER = os.getenv("SPARK_TRIGGER", "10 seconds")
KAFKA_PKG = os.getenv("SPARK_KAFKA_PKG", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1")

CELL_SCHEMA = StructType([
    StructField("cell_id", IntegerType()),
    StructField("voltage", DoubleType()),
    StructField("current", DoubleType()),
    StructField("temperature", DoubleType()),
    StructField("soc", DoubleType()),
    StructField("is_spike", BooleanType()),
    StructField("temperature_norm", DoubleType()),
])
PAYLOAD_SCHEMA = StructType([
    StructField("tick", LongType()),
    StructField("timestamp", StringType()),
    StructField("pack_id", StringType()),
    StructField("cells", ArrayType(CELL_SCHEMA)),
])


def build_session() -> SparkSession:
    return (
        SparkSession.builder.appName("btms-streaming-analytics")
        .config("spark.jars.packages", KAFKA_PKG)
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )


def main():
    spark = build_session()
    spark.sparkContext.setLogLevel("WARN")

    raw_stream = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .load()
    )

    parsed = (
        raw_stream
        .select(F.from_json(F.col("value").cast("string"), PAYLOAD_SCHEMA).alias("p"), F.col("timestamp").alias("kafka_ts"))
        .select(
            F.coalesce(F.col("p.timestamp").cast("timestamp"), F.col("kafka_ts")).alias("event_time"),
            F.col("p.tick").alias("tick"),
            F.col("p.pack_id").alias("pack_id"),
            F.explode("p.cells").alias("c"),
        )
        .select(
            "event_time", "tick", "pack_id",
            F.col("c.cell_id").alias("cell_id"),
            F.col("c.temperature").alias("temperature"),
            F.col("c.voltage").alias("voltage"),
            F.col("c.current").alias("current"),
            F.col("c.soc").alias("soc"),
            F.col("c.is_spike").cast("int").alias("is_spike"),
        )
        .withColumn("date", F.to_date("event_time"))
    )

    # ── Bronze: raw archive ──────────────────────────────────────────────────
    q_raw = (
        parsed.writeStream.format("parquet")
        .option("path", f"{LAKE}/raw")
        .option("checkpointLocation", f"{CHECKPOINTS}/raw")
        .partitionBy("date")
        .outputMode("append")
        .trigger(processingTime=TRIGGER)
        .start()
    )

    watermarked = parsed.withWatermark("event_time", "10 seconds")

    # ── Silver: per-cell sliding-window statistics ───────────────────────────
    cell_metrics = (
        watermarked.groupBy(F.window("event_time", "30 seconds", "10 seconds"), "pack_id", "cell_id")
        .agg(
            F.avg("temperature").alias("avg_temp"),
            F.min("temperature").alias("min_temp"),
            F.max("temperature").alias("max_temp"),
            F.stddev("temperature").alias("std_temp"),
            F.avg("voltage").alias("avg_voltage"),
            F.avg("current").alias("avg_current"),
            F.avg("soc").alias("avg_soc"),
            F.sum("is_spike").alias("spike_count"),
            F.count("*").alias("samples"),
        )
        .select(
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            "*",
        ).drop("window")
    )
    q_cell = (
        cell_metrics.writeStream.format("parquet")
        .option("path", f"{LAKE}/cell_metrics")
        .option("checkpointLocation", f"{CHECKPOINTS}/cell_metrics")
        .outputMode("append")
        .trigger(processingTime=TRIGGER)
        .start()
    )

    # ── Gold: pack-level tumbling windows ────────────────────────────────────
    pack_metrics = (
        watermarked.groupBy(F.window("event_time", "10 seconds"), "pack_id")
        .agg(
            F.max("temperature").alias("max_temp"),
            F.min("temperature").alias("min_temp"),
            F.avg("temperature").alias("avg_temp"),
            F.avg("voltage").alias("avg_voltage"),
            F.avg("soc").alias("avg_soc"),
            F.sum("is_spike").alias("spike_readings"),
            F.approx_count_distinct(F.when(F.col("is_spike") == 1, F.col("cell_id"))).alias("spiking_cells"),
            F.count("*").alias("samples"),
        )
        .withColumn("delta_t", F.col("max_temp") - F.col("min_temp"))
        .select(
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            "*",
        ).drop("window")
    )
    q_pack = (
        pack_metrics.writeStream.format("parquet")
        .option("path", f"{LAKE}/pack_metrics")
        .option("checkpointLocation", f"{CHECKPOINTS}/pack_metrics")
        .outputMode("append")
        .trigger(processingTime=TRIGGER)
        .start()
    )

    print(f"[spark] streaming {KAFKA_TOPIC}@{KAFKA_BOOTSTRAP_SERVERS} → {LAKE}", flush=True)
    spark.streams.awaitAnyTermination()
    for q in (q_raw, q_cell, q_pack):
        q.stop()


if __name__ == "__main__":
    main()
