"""
Urban Pulse — Generator Orchestrator
Run this to start producing data to Kafka or save to local files
"""

import os
import json
import argparse
import threading
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger

from uber_generator import UberRideGenerator, DriverPool
from zomato_generator import ZomatoOrderGenerator, RestaurantPool

DATA_DIR = Path("../data")
DATA_DIR.mkdir(exist_ok=True)


def save_to_parquet(records: list, filename: str, subdir: str = "raw"):
    """Save records as Parquet files (simulating S3/Data Lake)"""
    path = DATA_DIR / subdir
    path.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(records)
    filepath = path / f"{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
    df.to_parquet(filepath, index=False, engine='pyarrow')
    logger.info(f"Saved {len(records)} records to {filepath}")
    return filepath


def save_to_csv(records: list, filename: str, subdir: str = "raw"):
    """Save records as CSV (for easy inspection)"""
    path = DATA_DIR / subdir / "csv"
    path.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(records)
    filepath = path / f"{filename}.csv"
    df.to_csv(filepath, index=False)
    logger.info(f"Saved {len(records)} records to {filepath}")
    return filepath


def generate_historical_data(
    uber_records: int = 100_000,
    zomato_records: int = 80_000,
    days_back: int = 90
):
    """Generate historical data for model training and analysis"""
    logger.info("=" * 60)
    logger.info("URBAN PULSE — Generating Historical Dataset")
    logger.info(f"Uber: {uber_records:,} records | Zomato: {zomato_records:,} records")
    logger.info(f"Period: Last {days_back} days")
    logger.info("=" * 60)

    start_date = datetime.now() - timedelta(days=days_back)

    # ── Uber Data ──────────────────────────────────────────────────
    logger.info("Generating Uber ride data...")
    driver_pool = DriverPool(num_drivers=500)
    uber_gen = UberRideGenerator(driver_pool)
    uber_records_data = uber_gen.generate_batch(n=uber_records, start_date=start_date)

    uber_parquet = save_to_parquet(uber_records_data, "uber_rides", "raw/uber")
    uber_csv = save_to_csv(uber_records_data[:5000], "uber_rides_sample", "raw/uber")
    logger.success(f"Uber data: {len(uber_records_data):,} records saved")

    # ── Zomato Data ────────────────────────────────────────────────
    logger.info("Generating Zomato order data...")
    restaurant_pool = RestaurantPool(num_restaurants=200)
    zomato_gen = ZomatoOrderGenerator(restaurant_pool)
    zomato_records_data = zomato_gen.generate_batch(n=zomato_records, start_date=start_date)

    zomato_parquet = save_to_parquet(zomato_records_data, "zomato_orders", "raw/zomato")
    zomato_csv = save_to_csv(zomato_records_data[:5000], "zomato_orders_sample", "raw/zomato")
    logger.success(f"Zomato data: {len(zomato_records_data):,} records saved")

    # ── Summary Stats ──────────────────────────────────────────────
    uber_df = pd.DataFrame(uber_records_data)
    zomato_df = pd.DataFrame(zomato_records_data)

    print("\n" + "=" * 60)
    print("📊 DATASET SUMMARY")
    print("=" * 60)
    print(f"\n🚗 UBER RIDES")
    print(f"  Total Records  : {len(uber_df):,}")
    print(f"  Completed Rides: {(uber_df['event_type'] == 'completed').sum():,}")
    print(f"  Avg Fare (₹)   : {uber_df['final_fare'].mean():.2f}")
    print(f"  Avg Surge      : {uber_df['surge_multiplier'].mean():.2f}x")
    print(f"  Avg Distance   : {uber_df['distance_km'].mean():.2f} km")

    print(f"\n🍔 ZOMATO ORDERS")
    print(f"  Total Records  : {len(zomato_df):,}")
    print(f"  Avg Order Value: ₹{zomato_df['total_amount'].mean():.2f}")
    print(f"  Avg Delivery   : {zomato_df['delivery_time_minutes'].mean():.1f} min")
    print(f"  Avg Total Time : {zomato_df['total_time_minutes'].mean():.1f} min")

    print(f"\n✅ Files saved to: {DATA_DIR}")
    print("=" * 60)

    return uber_df, zomato_df


def stream_to_kafka(uber_rate: int = 10, zomato_rate: int = 8):
    """Stream events to Kafka topics in real-time"""
    try:
        from kafka import KafkaProducer
        producer = KafkaProducer(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None
        )
        logger.info("Connected to Kafka")
    except Exception as e:
        logger.error(f"Kafka not available: {e}. Streaming to console instead.")
        producer = None

    uber_gen = UberRideGenerator()
    zomato_gen = ZomatoOrderGenerator()

    def uber_stream():
        for event in uber_gen.stream_events(events_per_second=uber_rate):
            if producer:
                producer.send("rides-stream", key=event["ride_id"], value=event)
            else:
                logger.debug(f"[UBER] {event['event_type']} | {event['vehicle_type']} | ₹{event['final_fare']}")

    def zomato_stream():
        for event in zomato_gen.stream_events(events_per_second=zomato_rate):
            if producer:
                producer.send("orders-stream", key=event["order_id"], value=event)
            else:
                logger.debug(f"[ZOMATO] {event['order_id']} | ₹{event['total_amount']}")

    t1 = threading.Thread(target=uber_stream, daemon=True)
    t2 = threading.Thread(target=zomato_stream, daemon=True)
    t1.start()
    t2.start()

    logger.info(f"Streaming: Uber @ {uber_rate}/sec | Zomato @ {zomato_rate}/sec")
    logger.info("Press Ctrl+C to stop")

    try:
        t1.join()
        t2.join()
    except KeyboardInterrupt:
        logger.info("Streaming stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Urban Pulse Data Generator")
    parser.add_argument("--mode", choices=["historical", "stream"], default="historical")
    parser.add_argument("--uber-records", type=int, default=100_000)
    parser.add_argument("--zomato-records", type=int, default=80_000)
    parser.add_argument("--uber-rate", type=int, default=10)
    parser.add_argument("--zomato-rate", type=int, default=8)
    parser.add_argument("--days-back", type=int, default=90)
    args = parser.parse_args()

    if args.mode == "historical":
        generate_historical_data(args.uber_records, args.zomato_records, args.days_back)
    else:
        stream_to_kafka(args.uber_rate, args.zomato_rate)
