"""
Urban Pulse — PySpark Streaming Pipeline
Consumes Kafka topics in real-time, computes live KPIs,
detects anomalies, and writes to PostgreSQL for the dashboard
"""

import os
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import *
from loguru import logger


KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
CHECKPOINT_DIR = "/tmp/urban_pulse_checkpoints"

RIDE_SCHEMA = StructType([
    StructField("ride_id", StringType()),
    StructField("event_type", StringType()),
    StructField("timestamp", StringType()),
    StructField("pickup_zone", IntegerType()),
    StructField("vehicle_type", StringType()),
    StructField("final_fare", DoubleType()),
    StructField("surge_multiplier", DoubleType()),
    StructField("distance_km", DoubleType()),
    StructField("weather_condition", StringType()),
    StructField("is_peak_hour", BooleanType()),
])

ORDER_SCHEMA = StructType([
    StructField("order_id", StringType()),
    StructField("timestamp", StringType()),
    StructField("delivery_zone", IntegerType()),
    StructField("total_amount", DoubleType()),
    StructField("delivery_time_minutes", IntegerType()),
    StructField("restaurant_id", StringType()),
    StructField("weather_condition", StringType()),
])


def create_spark():
    return (
        SparkSession.builder
        .appName("UrbanPulse_Streaming")
        .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_DIR)
        .config("spark.jars.packages",
                "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,"
                "org.postgresql:postgresql:42.6.0")
        .getOrCreate()
    )


def read_kafka_stream(spark: SparkSession, topic: str):
    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_SERVERS)
        .option("subscribe", topic)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .load()
    )


def process_ride_stream(spark: SparkSession):
    """Real-time ride analytics: surge zones, demand heatmap, revenue"""
    raw = read_kafka_stream(spark, "rides-stream")

    rides = raw.select(
        F.from_json(F.col("value").cast("string"), RIDE_SCHEMA).alias("data")
    ).select("data.*").withColumn(
        "event_ts", F.to_timestamp("timestamp")
    )

    # ── 5-min windowed aggregation per zone ───────────────────────
    zone_window = rides.withWatermark("event_ts", "10 minutes").groupBy(
        F.window("event_ts", "5 minutes"),
        "pickup_zone"
    ).agg(
        F.count("ride_id").alias("ride_count"),
        F.avg("final_fare").alias("avg_fare"),
        F.avg("surge_multiplier").alias("avg_surge"),
        F.max("surge_multiplier").alias("max_surge"),
        F.sum("final_fare").alias("revenue")
    ).select(
        F.col("window.start").alias("window_start"),
        F.col("window.end").alias("window_end"),
        "pickup_zone", "ride_count", "avg_fare",
        "avg_surge", "max_surge", "revenue"
    )

    # ── Write to PostgreSQL for live dashboard ─────────────────────
    pg_options = {
        "url": f"jdbc:postgresql://{os.getenv('POSTGRES_HOST','localhost')}:5432/urban_pulse_ops",
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "postgres123"),
        "driver": "org.postgresql.Driver"
    }

    def write_to_pg(batch_df, batch_id):
        if batch_df.count() > 0:
            batch_df.withColumn("batch_id", F.lit(batch_id)) \
                    .write.format("jdbc").options(**pg_options) \
                    .option("dbtable", "live_zone_rides") \
                    .mode("append").save()
            logger.info(f"Batch {batch_id}: wrote {batch_df.count()} zone aggregations")

    query = (
        zone_window.writeStream
        .outputMode("update")
        .foreachBatch(write_to_pg)
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/rides")
        .trigger(processingTime="30 seconds")
        .start()
    )
    return query


def process_order_stream(spark: SparkSession):
    """Real-time order analytics: GMV, delivery times, zone demand"""
    raw = read_kafka_stream(spark, "orders-stream")

    orders = raw.select(
        F.from_json(F.col("value").cast("string"), ORDER_SCHEMA).alias("data")
    ).select("data.*").withColumn(
        "event_ts", F.to_timestamp("timestamp")
    )

    # ── 5-min GMV per zone ────────────────────────────────────────
    zone_gmv = orders.withWatermark("event_ts", "10 minutes").groupBy(
        F.window("event_ts", "5 minutes"), "delivery_zone"
    ).agg(
        F.count("order_id").alias("order_count"),
        F.sum("total_amount").alias("gmv"),
        F.avg("total_amount").alias("avg_order_value"),
        F.avg("delivery_time_minutes").alias("avg_delivery_min"),
        F.countDistinct("restaurant_id").alias("active_restaurants")
    )

    # ── Console output for debugging ──────────────────────────────
    debug_query = (
        zone_gmv.writeStream
        .outputMode("update")
        .format("console")
        .option("truncate", False)
        .trigger(processingTime="60 seconds")
        .start()
    )
    return debug_query


if __name__ == "__main__":
    spark = create_spark()
    spark.sparkContext.setLogLevel("WARN")

    logger.info("Starting Urban Pulse Streaming Pipeline...")
    q1 = process_ride_stream(spark)
    q2 = process_order_stream(spark)

    logger.info("Streaming queries running. Waiting for termination...")
    spark.streams.awaitAnyTermination()
