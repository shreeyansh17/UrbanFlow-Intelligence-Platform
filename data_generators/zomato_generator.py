"""
Urban Pulse — Zomato Food Order Event Generator
Simulates realistic food delivery events with restaurant data,
menu items, delivery patterns, and ratings
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
    CITY_ZONES, RESTAURANT_CHAINS, CUISINE_TYPES,
    HOURLY_DEMAND, WEEKEND_MULTIPLIER, RAIN_MULTIPLIER_FOOD,
    FOOD_PRICING, VEHICLE_TYPES
)

fake = Faker('en_IN')


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class Restaurant:
    restaurant_id: str
    name: str
    chain: Optional[str]
    cuisine: str
    zone_id: int
    lat: float
    lon: float
    rating: float
    total_orders: int
    avg_prep_time: int      # minutes
    is_pure_veg: bool
    price_category: str     # budget / mid / premium
    opening_hour: int
    closing_hour: int

@dataclass
class OrderEvent:
    event_id: str
    event_type: str          # placed, accepted, preparing, picked_up, delivered, cancelled
    timestamp: str
    order_id: str
    user_id: str
    restaurant_id: str
    restaurant_zone: int
    delivery_zone: int
    delivery_lat: float
    delivery_lon: float
    items: List[dict]
    item_count: int
    subtotal: float
    delivery_fee: float
    platform_fee: float
    gst: float
    discount: float
    total_amount: float
    payment_method: str
    delivery_distance_km: float
    prep_time_minutes: int
    delivery_time_minutes: int
    total_time_minutes: int
    delivery_agent_id: str
    food_rating: Optional[float]
    delivery_rating: Optional[float]
    cancellation_reason: Optional[str]
    weather_condition: str
    is_peak_hour: bool
    promo_code: Optional[str]
    platform: str = "Urban_Zomato"


# ─── Menu Generator ───────────────────────────────────────────────────────────

MENU_ITEMS = {
    "North Indian": [
        ("Butter Chicken", 320), ("Dal Makhani", 240), ("Paneer Tikka", 280),
        ("Biryani", 350), ("Naan", 40), ("Gulab Jamun", 80), ("Lassi", 60)
    ],
    "South Indian": [
        ("Masala Dosa", 120), ("Idli Sambar", 90), ("Vada", 70),
        ("Uttapam", 110), ("Chettinad Chicken", 320), ("Filter Coffee", 50)
    ],
    "Chinese": [
        ("Hakka Noodles", 180), ("Chilli Chicken", 280), ("Fried Rice", 160),
        ("Manchurian", 200), ("Spring Rolls", 150), ("Wonton Soup", 140)
    ],
    "Pizza": [
        ("Margherita Pizza", 350), ("Pepperoni Pizza", 450), ("BBQ Chicken Pizza", 480),
        ("Cheese Burst Pizza", 420), ("Garlic Bread", 120), ("Pasta", 220)
    ],
    "Burgers": [
        ("Classic Burger", 180), ("Double Patty Burger", 280), ("Veggie Burger", 150),
        ("Crispy Chicken Burger", 220), ("Fries", 80), ("Milkshake", 120)
    ],
    "Biryani": [
        ("Hyderabadi Biryani", 320), ("Lucknowi Biryani", 300), ("Kolkata Biryani", 290),
        ("Veg Biryani", 220), ("Raita", 40), ("Shorba", 60)
    ],
    "Fast Food": [
        ("Samosa", 30), ("Pav Bhaji", 120), ("Vada Pav", 25), ("Bhel Puri", 60),
        ("Pani Puri", 50), ("Misal Pav", 100)
    ]
}


class RestaurantPool:
    def __init__(self, num_restaurants: int = 200):
        self.restaurants: Dict[str, Restaurant] = {}
        self._generate_restaurants(num_restaurants)
        logger.info(f"Generated {num_restaurants} restaurants")

    def _generate_restaurants(self, n: int):
        for i in range(n):
            restaurant_id = f"RST_{uuid.uuid4().hex[:8].upper()}"
            zone_id = random.choice(list(CITY_ZONES.keys()))
            zone = CITY_ZONES[zone_id]
            is_chain = random.random() < 0.4
            cuisine = random.choice(CUISINE_TYPES)

            self.restaurants[restaurant_id] = Restaurant(
                restaurant_id=restaurant_id,
                name=random.choice(RESTAURANT_CHAINS) if is_chain else f"{fake.last_name()}'s {cuisine} Kitchen",
                chain=random.choice(RESTAURANT_CHAINS) if is_chain else None,
                cuisine=cuisine,
                zone_id=zone_id,
                lat=zone["lat"] + random.uniform(-0.015, 0.015),
                lon=zone["lon"] + random.uniform(-0.015, 0.015),
                rating=round(random.gauss(3.9, 0.4), 1),
                total_orders=random.randint(100, 50000),
                avg_prep_time=random.randint(15, 35),
                is_pure_veg=random.random() < 0.35,
                price_category=random.choices(
                    ["budget", "mid", "premium"], weights=[0.40, 0.45, 0.15]
                )[0],
                opening_hour=random.choice([7, 8, 9, 10, 11]),
                closing_hour=random.choice([22, 23, 0, 1])
            )

    def get_open_restaurants(self, hour: int, zone_id: int) -> List[Restaurant]:
        nearby = [
            r for r in self.restaurants.values()
            if abs(r.zone_id - zone_id) <= 3
        ]
        return nearby if nearby else list(self.restaurants.values())[:20]


class ZomatoOrderGenerator:
    def __init__(self, restaurant_pool: Optional[RestaurantPool] = None):
        self.restaurant_pool = restaurant_pool or RestaurantPool(200)
        self.user_pool = [f"USR_{uuid.uuid4().hex[:8].upper()}" for _ in range(3000)]
        self.agent_pool = [f"DEL_{uuid.uuid4().hex[:8].upper()}" for _ in range(300)]
        logger.info("ZomatoOrderGenerator initialized")

    def _generate_order_items(self, restaurant: Restaurant) -> tuple:
        """Generate realistic order items"""
        cuisine_key = restaurant.cuisine if restaurant.cuisine in MENU_ITEMS else "Fast Food"
        available_items = MENU_ITEMS.get(cuisine_key, MENU_ITEMS["Fast Food"])

        n_items = random.choices([1, 2, 3, 4, 5], weights=[0.15, 0.30, 0.30, 0.15, 0.10])[0]
        selected = random.sample(available_items, min(n_items, len(available_items)))

        items = []
        subtotal = 0
        for name, base_price in selected:
            qty = random.choices([1, 2, 3], weights=[0.65, 0.25, 0.10])[0]
            price = base_price * random.uniform(0.9, 1.1)  # price variance
            items.append({"name": name, "quantity": qty, "unit_price": round(price, 2), "total": round(price * qty, 2)})
            subtotal += price * qty

        return items, round(subtotal, 2)

    def _calculate_delivery_fee(self, distance_km: float) -> float:
        base = FOOD_PRICING["delivery_fee_base"]
        per_km = FOOD_PRICING["delivery_fee_per_km"]
        fee = base + max(0, (distance_km - 2) * per_km)
        return round(fee, 2)

    def _get_discount(self, subtotal: float, promo: Optional[str]) -> float:
        if promo is None:
            return 0
        discounts = {
            "FLAT50": min(50, subtotal * 0.1),
            "NEW100": min(100, subtotal * 0.2),
            "SAVE20": subtotal * 0.20,
            "FREEDLY": 0,  # free delivery handled separately
        }
        return round(discounts.get(promo, 0), 2)

    def generate_order(self, timestamp: Optional[datetime] = None) -> OrderEvent:
        if timestamp is None:
            timestamp = datetime.now()

        hour = timestamp.hour
        order_id = f"ORD_{uuid.uuid4().hex[:10].upper()}"
        user_id = random.choice(self.user_pool)
        delivery_zone_id = random.choice(list(CITY_ZONES.keys()))
        delivery_zone = CITY_ZONES[delivery_zone_id]

        # Pick restaurant near delivery zone
        available_rests = self.restaurant_pool.get_open_restaurants(hour, delivery_zone_id)
        restaurant = random.choice(available_rests)

        # Delivery distance
        dist = math.sqrt(
            (restaurant.lat - delivery_zone["lat"])**2 +
            (restaurant.lon - delivery_zone["lon"])**2
        ) * 111
        dist = round(max(0.5, dist + random.uniform(-0.5, 1.5)), 2)

        items, subtotal = self._generate_order_items(restaurant)
        delivery_fee = self._calculate_delivery_fee(dist)
        platform_fee = FOOD_PRICING["platform_fee"]

        # Promo code (25% chance)
        promo = random.choice([None, None, None, "FLAT50", "SAVE20", "NEW100"]) if random.random() < 0.25 else None
        discount = self._get_discount(subtotal, promo)
        gst = round(subtotal * FOOD_PRICING["gst_rate"], 2)
        total = round(subtotal + delivery_fee + platform_fee + gst - discount, 2)

        is_raining = random.random() < 0.15
        weather = "Rain" if is_raining else random.choice(["Clear", "Cloudy", "Haze"])

        # Time calculations — rain increases time
        prep_time = restaurant.avg_prep_time + random.randint(-5, 10)
        base_delivery = int((dist / 15) * 60) + random.randint(5, 15)  # 15 km/h avg
        if is_raining:
            base_delivery = int(base_delivery * 1.4)
        delivery_time = max(10, base_delivery)

        delivery_lat = delivery_zone["lat"] + random.uniform(-0.01, 0.01)
        delivery_lon = delivery_zone["lon"] + random.uniform(-0.01, 0.01)

        return OrderEvent(
            event_id=f"EVT_{uuid.uuid4().hex[:8].upper()}",
            event_type="delivered",
            timestamp=timestamp.isoformat(),
            order_id=order_id,
            user_id=user_id,
            restaurant_id=restaurant.restaurant_id,
            restaurant_zone=restaurant.zone_id,
            delivery_zone=delivery_zone_id,
            delivery_lat=round(delivery_lat, 6),
            delivery_lon=round(delivery_lon, 6),
            items=items,
            item_count=sum(i["quantity"] for i in items),
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            platform_fee=platform_fee,
            gst=gst,
            discount=discount,
            total_amount=max(0, total),
            payment_method=random.choices(
                ["UPI", "Card", "Cash", "Wallet", "Netbanking"],
                weights=[0.55, 0.20, 0.15, 0.07, 0.03]
            )[0],
            delivery_distance_km=dist,
            prep_time_minutes=max(10, prep_time),
            delivery_time_minutes=delivery_time,
            total_time_minutes=max(10, prep_time) + delivery_time,
            delivery_agent_id=random.choice(self.agent_pool),
            food_rating=round(max(1, min(5, random.gauss(4.0, 0.7))), 1) if random.random() > 0.3 else None,
            delivery_rating=round(max(1, min(5, random.gauss(4.1, 0.6))), 1) if random.random() > 0.3 else None,
            cancellation_reason=None,
            weather_condition=weather,
            is_peak_hour=hour in [12, 13, 19, 20, 21],
            promo_code=promo
        )

    def generate_batch(self, n: int = 1000, start_date: datetime = None) -> List[dict]:
        if start_date is None:
            start_date = datetime.now() - timedelta(days=90)

        records = []
        logger.info(f"Generating {n} historical order records...")

        for i in range(n):
            random_offset = random.uniform(0, 90 * 24 * 3600)
            ts = start_date + timedelta(seconds=random_offset)

            # Bias towards meal times
            if random.random() < 0.75:
                ts = ts.replace(hour=random.choices(
                    list(HOURLY_DEMAND.keys()),
                    weights=[v[1] for v in HOURLY_DEMAND.values()]
                )[0])

            order = self.generate_order(ts)
            records.append(asdict(order))

            if (i + 1) % 10000 == 0:
                logger.info(f"Generated {i + 1}/{n} order records")

        return records

    def stream_events(self, events_per_second: int = 8) -> Generator[dict, None, None]:
        while True:
            events_this_second = max(1, int(random.gauss(events_per_second, events_per_second * 0.2)))
            for _ in range(events_this_second):
                order = self.generate_order()
                yield asdict(order)
            time.sleep(1)


if __name__ == "__main__":
    generator = ZomatoOrderGenerator()
    batch = generator.generate_batch(n=100)
    print(f"Generated {len(batch)} order records")
    print(json.dumps(batch[0], indent=2, default=str))
