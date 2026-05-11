"""
Urban Pulse - City Configuration
Simulates Mumbai (can be changed to any metro)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple
import random

# ─── City Zones ──────────────────────────────────────────────────────────────
CITY_ZONES = {
    1:  {"name": "Andheri West",     "lat": 19.1197, "lon": 72.8466, "type": "residential", "density": "high"},
    2:  {"name": "Bandra Kurla",     "lat": 19.0596, "lon": 72.8650, "type": "business",    "density": "very_high"},
    3:  {"name": "Colaba",           "lat": 18.9067, "lon": 72.8147, "type": "tourist",     "density": "medium"},
    4:  {"name": "Dadar",            "lat": 19.0178, "lon": 72.8478, "type": "mixed",       "density": "high"},
    5:  {"name": "Juhu",             "lat": 19.1075, "lon": 72.8263, "type": "premium",     "density": "medium"},
    6:  {"name": "Lower Parel",      "lat": 18.9956, "lon": 72.8258, "type": "business",    "density": "high"},
    7:  {"name": "Malad East",       "lat": 19.1871, "lon": 72.8485, "type": "residential", "density": "very_high"},
    8:  {"name": "Powai",            "lat": 19.1176, "lon": 72.9060, "type": "tech_hub",    "density": "high"},
    9:  {"name": "Thane",            "lat": 19.2183, "lon": 72.9781, "type": "suburban",    "density": "high"},
    10: {"name": "Borivali",         "lat": 19.2307, "lon": 72.8567, "type": "residential", "density": "very_high"},
    11: {"name": "Navi Mumbai",      "lat": 19.0330, "lon": 73.0297, "type": "planned",     "density": "medium"},
    12: {"name": "Airport Zone",     "lat": 19.0896, "lon": 72.8656, "type": "transit",     "density": "medium"},
}

# ─── Restaurants ─────────────────────────────────────────────────────────────
RESTAURANT_CHAINS = [
    "McDonald's", "Domino's", "Pizza Hut", "KFC", "Subway",
    "Burger King", "Taco Bell", "Haldiram's", "Barbeque Nation",
    "Social", "The Beer Café", "Wow! Momo", "Faasos", "Box8",
    "Behrouz Biryani", "Biryani By Kilo", "Chaayos", "Café Coffee Day",
    "Starbucks", "Mainland China", "Sushi Haus", "Paradise Biryani"
]

CUISINE_TYPES = [
    "North Indian", "South Indian", "Chinese", "Pizza", "Burgers",
    "Biryani", "Sushi", "Thai", "Continental", "Fast Food",
    "Healthy", "Desserts", "Sandwiches", "Mexican", "Middle Eastern"
]

# ─── Driver Categories ────────────────────────────────────────────────────────
VEHICLE_TYPES = {
    "uber": ["UberGo", "Premier", "UberXL", "Auto", "Moto"],
    "zomato": ["Bike", "Scooter", "Bicycle"]
}

RATING_DISTRIBUTION = {
    "excellent": (4.7, 5.0, 0.20),   # 20% drivers
    "good":      (4.3, 4.7, 0.45),   # 45% drivers
    "average":   (3.8, 4.3, 0.25),   # 25% drivers
    "poor":      (2.5, 3.8, 0.10),   # 10% drivers
}

# ─── Time-based Demand Multipliers ────────────────────────────────────────────
HOURLY_DEMAND = {
    # hour: (rides_multiplier, orders_multiplier)
    0:  (0.15, 0.10),
    1:  (0.10, 0.05),
    2:  (0.08, 0.03),
    3:  (0.06, 0.02),
    4:  (0.07, 0.02),
    5:  (0.20, 0.05),
    6:  (0.55, 0.15),
    7:  (0.85, 0.30),
    8:  (1.20, 0.50),   # Morning rush
    9:  (1.40, 0.65),   # Peak morning
    10: (0.90, 0.70),
    11: (0.80, 0.95),
    12: (0.75, 1.50),   # Lunch peak
    13: (0.70, 1.60),   # Lunch peak
    14: (0.65, 0.90),
    15: (0.70, 0.75),
    16: (0.85, 0.80),
    17: (1.10, 0.90),
    18: (1.50, 1.20),   # Evening rush
    19: (1.60, 1.50),   # Dinner peak
    20: (1.30, 1.80),   # Dinner peak
    21: (1.10, 1.60),
    22: (0.80, 1.20),
    23: (0.45, 0.60),
}

WEEKEND_MULTIPLIER = 1.35
HOLIDAY_MULTIPLIER = 1.80
RAIN_MULTIPLIER_RIDES = 1.60
RAIN_MULTIPLIER_FOOD = 2.20

# ─── Surge Pricing Config ─────────────────────────────────────────────────────
SURGE_THRESHOLDS = {
    1.0: (0.00, 0.70),   # No surge — supply > 70% of demand
    1.2: (0.70, 0.80),   # 1.2x surge
    1.5: (0.80, 0.88),   # 1.5x surge
    2.0: (0.88, 0.94),   # 2x surge
    2.5: (0.94, 0.97),   # 2.5x surge
    3.0: (0.97, 1.00),   # 3x surge (extreme)
}

# ─── Price Config ─────────────────────────────────────────────────────────────
RIDE_PRICING = {
    "UberGo":   {"base": 40, "per_km": 12, "per_min": 1.5, "min_fare": 50},
    "Premier":  {"base": 60, "per_km": 18, "per_min": 2.0, "min_fare": 80},
    "UberXL":   {"base": 80, "per_km": 22, "per_min": 2.5, "min_fare": 100},
    "Auto":     {"base": 25, "per_km": 8,  "per_min": 1.0, "min_fare": 35},
    "Moto":     {"base": 20, "per_km": 6,  "per_min": 0.8, "min_fare": 25},
}

FOOD_PRICING = {
    "min_order": 80,
    "max_order": 1200,
    "delivery_fee_base": 30,
    "delivery_fee_per_km": 5,
    "platform_fee": 5,
    "gst_rate": 0.05,
}
