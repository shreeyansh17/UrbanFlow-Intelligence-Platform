"""Urban Pulse — Orders Router"""
from fastapi import APIRouter
from datetime import datetime
import random

router = APIRouter()

@router.get("/kpis")
async def get_order_kpis():
    return {
        "period": "last_24_hours",
        "timestamp": datetime.now().isoformat(),
        "total_orders": 8920,
        "gmv_inr": 2156800,
        "avg_order_value_inr": 241.7,
        "avg_delivery_minutes": 32.4,
        "avg_food_rating": 4.1,
        "avg_delivery_rating": 4.0,
        "rain_orders": 1240,
        "peak_zone": {"zone_id": 6, "name": "Lower Parel", "orders": 980}
    }

@router.get("/restaurants/top")
async def get_top_restaurants():
    restaurants = [
        {"rank": i+1, "name": name, "orders": orders, "rating": rating, "gmv_inr": gmv}
        for i, (name, orders, rating, gmv) in enumerate([
            ("Behrouz Biryani - BKC",  420, 4.5, 126000),
            ("Social - Lower Parel",   380, 4.3, 98000),
            ("McDonald's - Powai",     350, 4.1, 63000),
            ("Mainland China - Juhu",  310, 4.4, 124000),
            ("Domino's - Andheri",     290, 4.0, 52200),
        ])
    ]
    return {"timestamp": datetime.now().isoformat(), "top_restaurants": restaurants}
