"""
Urban Pulse — Uber Ride Event Generator
Simulates realistic ride-hailing events with surge pricing,
driver behavior, cancellations, and geospatial data
"""

import uuid
import random
import json
import time
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Generator
from dataclasses import dataclass, asdict
from faker import Faker
from loguru import logger
from config import (
    CITY_ZONES, VEHICLE_TYPES, RATING_DISTRIBUTION,
    HOURLY_DEMAND, WEEKEND_MULTIPLIER, RAIN_MULTIPLIER_RIDES,
    RIDE_PRICING, SURGE_THRESHOLDS
)

fake = Faker('en_IN')

# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class Driver:
    driver_id: str
    name: str
    phone: str
    vehicle_type: str
    vehicle_number: str
    rating: float
    total_trips: int
    zone_id: int
    lat: float
    lon: float
    is_available: bool
    joined_date: str

@dataclass
class RideEvent:
    event_id: str
    event_type: str          # requested, accepted, started, completed, cancelled
    timestamp: str
    ride_id: str
    user_id: str
    driver_id: Optional[str]
    pickup_zone: int
    dropoff_zone: int
    pickup_lat: float
    pickup_lon: float
    dropoff_lat: float
    dropoff_lon: float
    vehicle_type: str
    distance_km: float
    duration_minutes: float
    base_fare: float
    surge_multiplier: float
    final_fare: float
    payment_method: str
    user_rating: Optional[float]
    driver_rating: Optional[float]
    cancellation_reason: Optional[str]
    weather_condition: str
    is_peak_hour: bool
    city: str = "Mumbai"
    platform: str = "Urban_Uber"


# ─── Driver Pool ──────────────────────────────────────────────────────────────

class DriverPool:
    def __init__(self, num_drivers: int = 500):
        self.drivers: Dict[str, Driver] = {}
        self._generate_drivers(num_drivers)
        logger.info(f"Generated {num_drivers} drivers")

    def _generate_drivers(self, n: int):
        for _ in range(n):
            driver_id = f"DRV_{uuid.uuid4().hex[:8].upper()}"
            zone_id = random.choice(list(CITY_ZONES.keys()))
            zone = CITY_ZONES[zone_id]
            rating_category = random.choices(
                list(RATING_DISTRIBUTION.keys()),
                weights=[v[2] for v in RATING_DISTRIBUTION.values()]
            )[0]
            rating_range = RATING_DISTRIBUTION[rating_category]
            
            self.drivers[driver_id] = Driver(
                driver_id=driver_id,
                name=fake.name(),
                phone=fake.phone_number(),
                vehicle_type=random.choice(VEHICLE_TYPES["uber"]),
                vehicle_number=f"MH{random.randint(1,48):02d}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.randint(1000,9999)}",
                rating=round(random.uniform(rating_range[0], rating_range[1]), 1),
                total_trips=random.randint(50, 5000),
                zone_id=zone_id,
                lat=zone["lat"] + random.uniform(-0.02, 0.02),
                lon=zone["lon"] + random.uniform(-0.02, 0.02),
                is_available=random.random() > 0.3,
                joined_date=fake.date_between(start_date='-3y', end_date='today').isoformat()
            )

    def get_available_driver(self, zone_id: int, vehicle_type: str) -> Optional[Driver]:
        candidates = [
            d for d in self.drivers.values()
            if d.is_available and d.vehicle_type == vehicle_type
            and abs(d.zone_id - zone_id) <= 2
        ]
        if not candidates:
            candidates = [d for d in self.drivers.values() if d.is_available]
        return random.choice(candidates) if candidates else None


# ─── Ride Generator ───────────────────────────────────────────────────────────

class UberRideGenerator:
    def __init__(self, driver_pool: Optional[DriverPool] = None):
        self.driver_pool = driver_pool or DriverPool(500)
        self.active_rides: Dict[str, dict] = {}
        self.user_pool = self._generate_user_pool(2000)
        logger.info("UberRideGenerator initialized")

    def _generate_user_pool(self, n: int) -> List[str]:
        return [f"USR_{uuid.uuid4().hex[:8].upper()}" for _ in range(n)]

    def _jitter_coords(self, lat: float, lon: float, radius_km: float = 1.0) -> tuple:
        """Add realistic GPS jitter within radius"""
        lat_delta = (random.uniform(-radius_km, radius_km)) / 111.0
        lon_delta = (random.uniform(-radius_km, radius_km)) / (111.0 * math.cos(math.radians(lat)))
        return round(lat + lat_delta, 6), round(lon + lon_delta, 6)

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Haversine distance formula"""
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return round(R * 2 * math.asin(math.sqrt(a)), 2)

    def _get_surge_multiplier(self, hour: int, zone_id: int, is_raining: bool) -> float:
        """Calculate surge based on demand-supply ratio"""
        demand_factor = HOURLY_DEMAND.get(hour, (1.0, 1.0))[0]
        if is_raining:
            demand_factor *= RAIN_MULTIPLIER_RIDES
        
        zone_type = CITY_ZONES[zone_id]["type"]
        if zone_type in ["business", "tech_hub"] and hour in range(8, 10):
            demand_factor *= 1.3
        
        # Simulate demand-supply ratio
        supply_ratio = random.uniform(0.5, 1.0) / demand_factor
        supply_ratio = max(0.0, min(1.0, supply_ratio))

        for multiplier, (low, high) in SURGE_THRESHOLDS.items():
            if low <= supply_ratio < high:
                return multiplier
        return 1.0

    def _calculate_fare(self, vehicle_type: str, distance_km: float,
                        duration_min: float, surge: float) -> tuple:
        pricing = RIDE_PRICING.get(vehicle_type, RIDE_PRICING["UberGo"])
        base = pricing["base"] + (distance_km * pricing["per_km"]) + (duration_min * pricing["per_min"])
        base = max(base, pricing["min_fare"])
        final = round(base * surge, 2)
        return round(base, 2), final

    def generate_ride_request(self, timestamp: Optional[datetime] = None) -> RideEvent:
        """Generate a new ride request event"""
        if timestamp is None:
            timestamp = datetime.now()

        ride_id = f"RIDE_{uuid.uuid4().hex[:10].upper()}"
        user_id = random.choice(self.user_pool)
        pickup_zone_id = random.choice(list(CITY_ZONES.keys()))
        dropoff_zone_id = random.choice([z for z in CITY_ZONES.keys() if z != pickup_zone_id])

        pickup_zone = CITY_ZONES[pickup_zone_id]
        dropoff_zone = CITY_ZONES[dropoff_zone_id]

        pickup_lat, pickup_lon = self._jitter_coords(pickup_zone["lat"], pickup_zone["lon"])
        dropoff_lat, dropoff_lon = self._jitter_coords(dropoff_zone["lat"], dropoff_zone["lon"])

        distance = self._calculate_distance(pickup_lat, pickup_lon, dropoff_lat, dropoff_lon)
        # Realistic Mumbai traffic: avg 12 km/h during peak, 25 km/h off-peak
        hour = timestamp.hour
        avg_speed = 12 if hour in [8, 9, 17, 18, 19] else 25
        duration = round((distance / avg_speed) * 60 + random.uniform(2, 8), 1)

        vehicle_type = random.choice(VEHICLE_TYPES["uber"])
        is_raining = random.random() < 0.15  # 15% chance of rain
        weather = "Rain" if is_raining else random.choice(["Clear", "Cloudy", "Haze", "Fog"])
        surge = self._get_surge_multiplier(hour, pickup_zone_id, is_raining)
        base_fare, final_fare = self._calculate_fare(vehicle_type, distance, duration, surge)

        event = RideEvent(
            event_id=f"EVT_{uuid.uuid4().hex[:8].upper()}",
            event_type="requested",
            timestamp=timestamp.isoformat(),
            ride_id=ride_id,
            user_id=user_id,
            driver_id=None,
            pickup_zone=pickup_zone_id,
            dropoff_zone=dropoff_zone_id,
            pickup_lat=pickup_lat,
            pickup_lon=pickup_lon,
            dropoff_lat=dropoff_lat,
            dropoff_lon=dropoff_lon,
            vehicle_type=vehicle_type,
            distance_km=distance,
            duration_minutes=duration,
            base_fare=base_fare,
            surge_multiplier=surge,
            final_fare=final_fare,
            payment_method=random.choices(
                ["UPI", "Card", "Cash", "Wallet"],
                weights=[0.45, 0.25, 0.20, 0.10]
            )[0],
            user_rating=None,
            driver_rating=None,
            cancellation_reason=None,
            weather_condition=weather,
            is_peak_hour=hour in [8, 9, 12, 13, 17, 18, 19, 20]
        )

        self.active_rides[ride_id] = asdict(event)
        return event

    def generate_ride_completion(self, ride_id: str, timestamp: datetime) -> Optional[RideEvent]:
        """Generate completion event for an active ride"""
        if ride_id not in self.active_rides:
            return None

        ride_data = self.active_rides[ride_id].copy()
        driver = self.driver_pool.get_available_driver(
            ride_data["pickup_zone"], ride_data["vehicle_type"]
        )

        # Cancellation probability (15%)
        if random.random() < 0.15:
            ride_data.update({
                "event_id": f"EVT_{uuid.uuid4().hex[:8].upper()}",
                "event_type": "cancelled",
                "timestamp": timestamp.isoformat(),
                "cancellation_reason": random.choice([
                    "driver_too_far", "user_cancelled", "driver_cancelled",
                    "no_driver_available", "user_no_show"
                ])
            })
            del self.active_rides[ride_id]
            return RideEvent(**ride_data)

        # Completed ride
        ride_data.update({
            "event_id": f"EVT_{uuid.uuid4().hex[:8].upper()}",
            "event_type": "completed",
            "timestamp": timestamp.isoformat(),
            "driver_id": driver.driver_id if driver else f"DRV_UNKNOWN",
            "user_rating": round(random.gauss(4.2, 0.5), 1),
            "driver_rating": round(random.gauss(4.3, 0.4), 1),
        })
        ride_data["user_rating"] = max(1.0, min(5.0, ride_data["user_rating"]))
        ride_data["driver_rating"] = max(1.0, min(5.0, ride_data["driver_rating"]))

        del self.active_rides[ride_id]
        return RideEvent(**ride_data)

    def generate_batch(self, n: int = 1000, start_date: datetime = None) -> List[dict]:
        """Generate a batch of historical ride records"""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=90)

        records = []
        logger.info(f"Generating {n} historical ride records...")

        for i in range(n):
            # Random timestamp in last 90 days
            random_offset = random.uniform(0, 90 * 24 * 3600)
            ts = start_date + timedelta(seconds=random_offset)

            # Bias timestamps towards demand patterns
            if random.random() < 0.7:
                ts = ts.replace(hour=random.choices(
                    list(HOURLY_DEMAND.keys()),
                    weights=[v[0] for v in HOURLY_DEMAND.values()]
                )[0])

            request = self.generate_ride_request(ts)
            complete_ts = ts + timedelta(minutes=request.duration_minutes + random.uniform(2, 10))
            completion = self.generate_ride_completion(request.ride_id, complete_ts)

            if completion:
                records.append(asdict(completion))
            else:
                records.append(asdict(request))

            if (i + 1) % 10000 == 0:
                logger.info(f"Generated {i + 1}/{n} ride records")

        return records

    def stream_events(self, events_per_second: int = 10) -> Generator[dict, None, None]:
        """Yield real-time simulated events"""
        logger.info(f"Starting Uber event stream at {events_per_second} events/sec")
        while True:
            events_this_second = max(1, int(random.gauss(events_per_second, events_per_second * 0.2)))
            for _ in range(events_this_second):
                event = self.generate_ride_request()
                yield asdict(event)
            time.sleep(1)


if __name__ == "__main__":
    generator = UberRideGenerator()

    # Generate sample batch
    batch = generator.generate_batch(n=100)
    print(f"Generated {len(batch)} ride records")
    print(json.dumps(batch[0], indent=2))
