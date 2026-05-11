"""
Urban Pulse — PySpark Batch ETL Pipeline
Daily job: Raw Parquet → Cleaned → Snowflake-ready tables
Demonstrates: PySpark, Data Quality, Star Schema loading
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import argparse
from loguru import logger

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import *
from pyspark.sql.window import Window


# ─── Spark Session ────────────────────────────────────────────────────────────

def create_spark_session(app_name: str = "UrbanPulse_BatchETL") -> SparkSession:
    spark = (
        SparkSession.builder
        .appName(app_name)
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.sql.shuffle.partitions", "200")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        # Snowflake connector config
        .config("spark.jars.packages",
                "net.snowflake:snowflake-jdbc:3.14.4,"
                "net.snowflake:spark-snowflake_2.12:2.12.0-spark_3.4")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    logger.info(f"Spark {spark.version} session created")
    return spark


# ─── Schemas ──────────────────────────────────────────────────────────────────

RIDE_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("timestamp", StringType(), False),
    StructField("ride_id", StringType(), False),
    StructField("user_id", StringType(), False),
    StructField("driver_id", StringType(), True),
    StructField("pickup_zone", IntegerType(), False),
    StructField("dropoff_zone", IntegerType(), False),
    StructField("pickup_lat", DoubleType(), False),
    StructField("pickup_lon", DoubleType(), False),
    StructField("dropoff_lat", DoubleType(), False),
    StructField("dropoff_lon", DoubleType(), False),
    StructField("vehicle_type", StringType(), False),
    StructField("distance_km", DoubleType(), False),
    StructField("duration_minutes", DoubleType(), False),
    StructField("base_fare", DoubleType(), False),
    StructField("surge_multiplier", DoubleType(), False),
    StructField("final_fare", DoubleType(), False),
    StructField("payment_method", StringType(), False),
    StructField("user_rating", DoubleType(), True),
    StructField("driver_rating", DoubleType(), True),
    StructField("cancellation_reason", StringType(), True),
    StructField("weather_condition", StringType(), False),
    StructField("is_peak_hour", BooleanType(), False),
    StructField("city", StringType(), True),
    StructField("platform", StringType(), True),
])

ORDER_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("timestamp", StringType(), False),
    StructField("order_id", StringType(), False),
    StructField("user_id", StringType(), False),
    StructField("restaurant_id", StringType(), False),
    StructField("restaurant_zone", IntegerType(), False),
    StructField("delivery_zone", IntegerType(), False),
    StructField("delivery_lat", DoubleType(), False),
    StructField("delivery_lon", DoubleType(), False),
    StructField("item_count", IntegerType(), False),
    StructField("subtotal", DoubleType(), False),
    StructField("delivery_fee", DoubleType(), False),
    StructField("platform_fee", DoubleType(), False),
    StructField("gst", DoubleType(), False),
    StructField("discount", DoubleType(), False),
    StructField("total_amount", DoubleType(), False),
    StructField("payment_method", StringType(), False),
    StructField("delivery_distance_km", DoubleType(), False),
    StructField("prep_time_minutes", IntegerType(), False),
    StructField("delivery_time_minutes", IntegerType(), False),
    StructField("total_time_minutes", IntegerType(), False),
    StructField("delivery_agent_id", StringType(), False),
    StructField("food_rating", DoubleType(), True),
    StructField("delivery_rating", DoubleType(), True),
    StructField("cancellation_reason", StringType(), True),
    StructField("weather_condition", StringType(), False),
    StructField("is_peak_hour", BooleanType(), False),
    StructField("promo_code", StringType(), True),
    StructField("platform", StringType(), True),
])


# ─── Data Quality Checks ──────────────────────────────────────────────────────

class DataQualityChecker:
    def __init__(self, spark: SparkSession):
        self.spark = spark
        self.results = []

    def check(self, df: DataFrame, name: str) -> DataFrame:
        total = df.count()
        nulls = {col: df.filter(F.col(col).isNull()).count() for col in df.columns[:8]}

        logger.info(f"\n{'='*50}")
        logger.info(f"DQ Report: {name}")
        logger.info(f"Total rows: {total:,}")

        failed_rows = df.filter(
            (F.col("total_amount") < 0) |
            (F.col("timestamp").isNull())
        ) if "total_amount" in df.columns else self.spark.createDataFrame([], df.schema)

        bad_count = failed_rows.count()
        clean_df = df.subtract(failed_rows)

        logger.info(f"Bad rows removed: {bad_count}")
        logger.info(f"Clean rows: {clean_df.count():,}")

        self.results.append({
            "table": name, "total": total,
            "bad_rows": bad_count, "pass_rate": round((total - bad_count) / total * 100, 2)
        })
        return clean_df


# ─── ETL Transformations ──────────────────────────────────────────────────────

class RideETL:
    def __init__(self, spark: SparkSession):
        self.spark = spark
        self.dq = DataQualityChecker(spark)

    def extract(self, input_path: str) -> DataFrame:
        logger.info(f"Reading ride data from: {input_path}")
        df = self.spark.read.parquet(input_path) if input_path.endswith(".parquet") \
             else self.spark.read.option("header", True).csv(input_path)
        logger.info(f"Loaded {df.count():,} raw ride records")
        return df

    def transform(self, df: DataFrame) -> dict:
        # Parse timestamp
        df = df.withColumn("event_ts", F.to_timestamp("timestamp"))
        df = df.withColumn("event_date", F.to_date("event_ts"))
        df = df.withColumn("event_hour", F.hour("event_ts"))
        df = df.withColumn("event_day_of_week", F.dayofweek("event_ts"))
        df = df.withColumn("event_month", F.month("event_ts"))
        df = df.withColumn("is_weekend", F.dayofweek("event_ts").isin([1, 7]))

        # Clean & validate
        df = df.withColumn("distance_km", F.abs("distance_km"))
        df = df.withColumn("final_fare", F.when(F.col("final_fare") < 0, 0).otherwise(F.col("final_fare")))
        df = df.withColumn("surge_multiplier", F.when(F.col("surge_multiplier") < 1.0, 1.0).otherwise(F.col("surge_multiplier")))

        # Feature engineering
        df = df.withColumn("fare_per_km", F.round(F.col("final_fare") / F.col("distance_km"), 2))
        df = df.withColumn("speed_kmh", F.round(F.col("distance_km") / (F.col("duration_minutes") / 60), 1))
        df = df.withColumn("is_surge", F.col("surge_multiplier") > 1.0)
        df = df.withColumn("is_cancelled", F.col("event_type") == "cancelled")
        df = df.withColumn("has_rating", F.col("user_rating").isNotNull())

        # Run DQ
        clean_df = self.dq.check(df, "rides")

        # ── fact_rides ──────────────────────────────────────────────
        fact_rides = clean_df.select(
            "ride_id", "event_id", "event_type", "event_date", "event_ts",
            "event_hour", "event_day_of_week", "is_weekend",
            "user_id", "driver_id", "pickup_zone", "dropoff_zone",
            "vehicle_type", "distance_km", "duration_minutes",
            "base_fare", "surge_multiplier", "final_fare", "fare_per_km",
            "payment_method", "user_rating", "driver_rating",
            "is_cancelled", "is_surge", "weather_condition",
            "is_peak_hour", "speed_kmh"
        )

        # ── Zone-level aggregations ────────────────────────────────
        zone_hourly = clean_df.filter(~F.col("is_cancelled")).groupBy(
            "event_date", "event_hour", "pickup_zone"
        ).agg(
            F.count("ride_id").alias("total_rides"),
            F.avg("final_fare").alias("avg_fare"),
            F.avg("surge_multiplier").alias("avg_surge"),
            F.avg("distance_km").alias("avg_distance"),
            F.sum("final_fare").alias("total_revenue"),
            F.countDistinct("user_id").alias("unique_users"),
            F.avg("duration_minutes").alias("avg_duration")
        )

        # ── Driver performance ─────────────────────────────────────
        driver_perf = clean_df.filter(
            F.col("driver_id").isNotNull()
        ).groupBy("driver_id", "event_date").agg(
            F.count("ride_id").alias("trips"),
            F.sum("final_fare").alias("earnings"),
            F.avg("driver_rating").alias("avg_rating"),
            F.sum(F.col("is_cancelled").cast("int")).alias("cancellations"),
            F.avg("distance_km").alias("avg_distance")
        ).withColumn(
            "completion_rate",
            F.round(1 - F.col("cancellations") / F.col("trips"), 3)
        )

        logger.success("Ride ETL transformations complete")
        return {
            "fact_rides": fact_rides,
            "zone_hourly_rides": zone_hourly,
            "driver_daily_performance": driver_perf
        }

    def load_to_snowflake(self, tables: dict, snowflake_options: dict):
        for table_name, df in tables.items():
            logger.info(f"Loading {df.count():,} rows → Snowflake.{table_name}")
            df.write \
              .format("snowflake") \
              .options(**snowflake_options) \
              .option("dbtable", table_name.upper()) \
              .mode("append") \
              .save()
            logger.success(f"Loaded {table_name} to Snowflake")

    def load_to_parquet(self, tables: dict, output_dir: str):
        """Local fallback for when Snowflake is not configured"""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        for table_name, df in tables.items():
            path = f"{output_dir}/{table_name}"
            df.write.mode("overwrite").parquet(path)
            logger.success(f"Saved {table_name} to {path}")


class OrderETL:
    def __init__(self, spark: SparkSession):
        self.spark = spark
        self.dq = DataQualityChecker(spark)

    def extract(self, input_path: str) -> DataFrame:
        logger.info(f"Reading order data from: {input_path}")
        return self.spark.read.parquet(input_path) if input_path.endswith(".parquet") \
               else self.spark.read.option("header", True).csv(input_path)

    def transform(self, df: DataFrame) -> dict:
        df = df.withColumn("event_ts", F.to_timestamp("timestamp"))
        df = df.withColumn("event_date", F.to_date("event_ts"))
        df = df.withColumn("event_hour", F.hour("event_ts"))
        df = df.withColumn("is_weekend", F.dayofweek("event_ts").isin([1, 7]))

        # Derived columns
        df = df.withColumn("avg_item_value", F.round(F.col("subtotal") / F.col("item_count"), 2))
        df = df.withColumn("is_discounted", F.col("discount") > 0)
        df = df.withColumn("is_rain_order", F.col("weather_condition") == "Rain")
        df = df.withColumn(
            "delivery_speed_tier",
            F.when(F.col("delivery_time_minutes") <= 20, "fast")
             .when(F.col("delivery_time_minutes") <= 35, "normal")
             .otherwise("slow")
        )

        clean_df = self.dq.check(df, "orders")

        fact_orders = clean_df.select(
            "order_id", "event_date", "event_ts", "event_hour", "is_weekend",
            "user_id", "restaurant_id", "restaurant_zone", "delivery_zone",
            "item_count", "subtotal", "delivery_fee", "platform_fee",
            "gst", "discount", "total_amount", "avg_item_value",
            "payment_method", "delivery_distance_km",
            "prep_time_minutes", "delivery_time_minutes", "total_time_minutes",
            "delivery_agent_id", "food_rating", "delivery_rating",
            "weather_condition", "is_peak_hour", "promo_code",
            "is_discounted", "is_rain_order", "delivery_speed_tier"
        )

        # Restaurant performance
        restaurant_daily = clean_df.groupBy("restaurant_id", "event_date").agg(
            F.count("order_id").alias("total_orders"),
            F.sum("total_amount").alias("gmv"),
            F.avg("total_amount").alias("avg_order_value"),
            F.avg("food_rating").alias("avg_food_rating"),
            F.avg("prep_time_minutes").alias("avg_prep_time"),
            F.countDistinct("user_id").alias("unique_customers")
        )

        # Delivery agent performance
        agent_daily = clean_df.groupBy("delivery_agent_id", "event_date").agg(
            F.count("order_id").alias("deliveries"),
            F.avg("delivery_time_minutes").alias("avg_delivery_time"),
            F.avg("delivery_rating").alias("avg_rating"),
            F.sum("delivery_fee").alias("earnings"),
            F.avg("delivery_distance_km").alias("avg_distance")
        )

        # Zone GMV
        zone_gmv = clean_df.groupBy("delivery_zone", "event_date", "event_hour").agg(
            F.sum("total_amount").alias("zone_gmv"),
            F.count("order_id").alias("order_count"),
            F.avg("delivery_time_minutes").alias("avg_delivery_time"),
            F.countDistinct("restaurant_id").alias("active_restaurants")
        )

        logger.success("Order ETL transformations complete")
        return {
            "fact_orders": fact_orders,
            "restaurant_daily_performance": restaurant_daily,
            "agent_daily_performance": agent_daily,
            "zone_hourly_orders": zone_gmv
        }


# ─── Dimension Tables ─────────────────────────────────────────────────────────

def build_dim_tables(spark: SparkSession) -> dict:
    """Build dimension tables for Star Schema"""

    # dim_time
    from pyspark.sql.functions import expr
    date_range = spark.sql("""
        SELECT explode(sequence(
            to_date('2024-01-01'), 
            to_date('2025-12-31'), 
            interval 1 day
        )) AS date_val
    """)
    dim_time = date_range.select(
        F.date_format("date_val", "yyyyMMdd").cast("int").alias("time_id"),
        F.col("date_val").alias("full_date"),
        F.dayofmonth("date_val").alias("day"),
        F.month("date_val").alias("month"),
        F.quarter("date_val").alias("quarter"),
        F.year("date_val").alias("year"),
        F.dayofweek("date_val").alias("day_of_week"),
        F.date_format("date_val", "EEEE").alias("day_name"),
        F.date_format("date_val", "MMMM").alias("month_name"),
        F.dayofweek("date_val").isin([1, 7]).alias("is_weekend")
    )

    # dim_zone
    zones_data = [
        (1, "Andheri West", 19.1197, 72.8466, "residential", "high"),
        (2, "Bandra Kurla", 19.0596, 72.8650, "business", "very_high"),
        (3, "Colaba", 18.9067, 72.8147, "tourist", "medium"),
        (4, "Dadar", 19.0178, 72.8478, "mixed", "high"),
        (5, "Juhu", 19.1075, 72.8263, "premium", "medium"),
        (6, "Lower Parel", 18.9956, 72.8258, "business", "high"),
        (7, "Malad East", 19.1871, 72.8485, "residential", "very_high"),
        (8, "Powai", 19.1176, 72.9060, "tech_hub", "high"),
        (9, "Thane", 19.2183, 72.9781, "suburban", "high"),
        (10, "Borivali", 19.2307, 72.8567, "residential", "very_high"),
        (11, "Navi Mumbai", 19.0330, 73.0297, "planned", "medium"),
        (12, "Airport Zone", 19.0896, 72.8656, "transit", "medium"),
    ]
    dim_zone = spark.createDataFrame(
        zones_data,
        ["zone_id", "zone_name", "latitude", "longitude", "zone_type", "density"]
    )

    logger.success("Dimension tables built")
    return {"dim_time": dim_time, "dim_zone": dim_zone}


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def run_batch_pipeline(
    rides_path: str,
    orders_path: str,
    output_dir: str = "../data/processed",
    load_snowflake: bool = False
):
    spark = create_spark_session()

    try:
        # Extract & Transform
        ride_etl = RideETL(spark)
        order_etl = OrderETL(spark)

        rides_raw = ride_etl.extract(rides_path)
        orders_raw = order_etl.extract(orders_path)

        ride_tables = ride_etl.transform(rides_raw)
        order_tables = order_etl.transform(orders_raw)
        dim_tables = build_dim_tables(spark)

        all_tables = {**ride_tables, **order_tables, **dim_tables}

        # Load
        if load_snowflake:
            sf_options = {
                "sfURL": os.getenv("SNOWFLAKE_ACCOUNT"),
                "sfUser": os.getenv("SNOWFLAKE_USER"),
                "sfPassword": os.getenv("SNOWFLAKE_PASSWORD"),
                "sfDatabase": os.getenv("SNOWFLAKE_DATABASE", "URBAN_PULSE"),
                "sfSchema": os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC"),
                "sfWarehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
            }
            ride_etl.load_to_snowflake(ride_tables, sf_options)
            order_etl.load_to_snowflake(order_tables, sf_options)
        else:
            logger.info("Snowflake disabled — saving to Parquet")
            ride_etl.load_to_parquet(all_tables, output_dir)

        logger.success("=" * 50)
        logger.success("Batch ETL Pipeline Completed Successfully!")
        logger.success(f"Tables produced: {list(all_tables.keys())}")

    finally:
        spark.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rides-path",   default="../data/raw/uber/")
    parser.add_argument("--orders-path",  default="../data/raw/zomato/")
    parser.add_argument("--output-dir",   default="../data/processed/")
    parser.add_argument("--snowflake",    action="store_true")
    parser.add_argument("--date",         default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    run_batch_pipeline(
        args.rides_path,
        args.orders_path,
        args.output_dir,
        args.snowflake
    )
