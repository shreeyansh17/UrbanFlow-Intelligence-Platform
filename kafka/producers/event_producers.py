"""
Urban Pulse — Kafka Producers
Sends Uber ride events and Zomato order events to Kafka topics
"""

import os
import json
import time
import threading
from datetime import datetime
from typing import Optional
from kafka import KafkaProducer, KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError
from loguru import logger
import sys
sys.path.append("../data_generators")
from uber_generator import UberRideGenerator
from zomato_generator import ZomatoOrderGenerator

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# ─── Topic Definitions ────────────────────────────────────────────────────────
TOPICS = [
    NewTopic(name="rides-stream",    num_partitions=6, replication_factor=1),
    NewTopic(name="orders-stream",   num_partitions=6, replication_factor=1),
    NewTopic(name="weather-events",  num_partitions=2, replication_factor=1),
    NewTopic(name="surge-events",    num_partitions=3, replication_factor=1),
    NewTopic(name="rides-dlq",       num_partitions=1, replication_factor=1),  # Dead Letter Queue
    NewTopic(name="orders-dlq",      num_partitions=1, replication_factor=1),
]


def create_topics():
    """Create Kafka topics if they don't exist"""
    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP_SERVERS)
    try:
        admin.create_topics(TOPICS)
        logger.success(f"Created {len(TOPICS)} Kafka topics")
    except TopicAlreadyExistsError:
        logger.info("Topics already exist")
    finally:
        admin.close()


def get_producer() -> KafkaProducer:
    """Create a Kafka producer with retry logic"""
    for attempt in range(5):
        try:
            producer = KafkaProducer(
                bootstrap_servers=BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',                    # Wait for all replicas
                retries=3,
                max_in_flight_requests_per_connection=1,
                compression_type='gzip',       # Compress messages
                batch_size=16384,
                linger_ms=10,                  # Micro-batching
            )
            logger.success("Connected to Kafka")
            return producer
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/5: {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError("Could not connect to Kafka")


class RideProducer:
    def __init__(self):
        self.producer = get_producer()
        self.generator = UberRideGenerator()
        self.sent_count = 0
        self.error_count = 0

    def on_send_success(self, record_metadata):
        self.sent_count += 1
        if self.sent_count % 1000 == 0:
            logger.info(f"[RIDES] Sent {self.sent_count:,} messages to {record_metadata.topic}")

    def on_send_error(self, excp):
        self.error_count += 1
        logger.error(f"Kafka send error: {excp}")
        # Send to DLQ
        self.producer.send("rides-dlq", value={"error": str(excp), "ts": datetime.now().isoformat()})

    def run(self, events_per_second: int = 10):
        logger.info(f"Starting Ride Producer @ {events_per_second} events/sec")
        for event in self.generator.stream_events(events_per_second):
            self.producer.send(
                "rides-stream",
                key=event["ride_id"],
                value=event,
                headers=[("source", b"urban-pulse"), ("version", b"1.0")]
            ).add_callback(self.on_send_success).add_errback(self.on_send_error)

            # Also publish surge events separately for real-time dashboard
            if event.get("surge_multiplier", 1.0) > 1.0:
                surge_event = {
                    "zone": event["pickup_zone"],
                    "surge": event["surge_multiplier"],
                    "vehicle_type": event["vehicle_type"],
                    "timestamp": event["timestamp"]
                }
                self.producer.send("surge-events", value=surge_event)


class OrderProducer:
    def __init__(self):
        self.producer = get_producer()
        self.generator = ZomatoOrderGenerator()
        self.sent_count = 0

    def on_send_success(self, record_metadata):
        self.sent_count += 1
        if self.sent_count % 1000 == 0:
            logger.info(f"[ORDERS] Sent {self.sent_count:,} messages")

    def on_send_error(self, excp):
        logger.error(f"Order send error: {excp}")
        self.producer.send("orders-dlq", value={"error": str(excp)})

    def run(self, events_per_second: int = 8):
        logger.info(f"Starting Order Producer @ {events_per_second} events/sec")
        for event in self.generator.stream_events(events_per_second):
            self.producer.send(
                "orders-stream",
                key=event["order_id"],
                value=event
            ).add_callback(self.on_send_success).add_errback(self.on_send_error)


if __name__ == "__main__":
    create_topics()

    ride_producer = RideProducer()
    order_producer = OrderProducer()

    t1 = threading.Thread(target=ride_producer.run, args=(15,), daemon=True)
    t2 = threading.Thread(target=order_producer.run, args=(10,), daemon=True)

    t1.start()
    t2.start()
    logger.info("All producers running. Press Ctrl+C to stop.")

    try:
        t1.join(); t2.join()
    except KeyboardInterrupt:
        logger.info("Producers stopped")
