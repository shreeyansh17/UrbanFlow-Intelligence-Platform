"""Urban Pulse — Rides Router"""
from fastapi import APIRouter
from datetime import datetime
import random

router = APIRouter()

@router.get("/kpis")
async def get_ride_kpis():
    """Live ride KPIs for dashboard"""
    return {
        "period": "last_24_hours",
        "timestamp": datetime.now().isoformat(),
        "total_rides": 12450,
        "completed": 10580,
        "cancelled": 1870,
        "completion_rate_pct": 85.0,
        "revenue_inr": 1876500,
        "avg_fare_inr": 177.3,
        "avg_surge": 1.28,
        "avg_distance_km": 8.4,
        "surge_rides": 3780,
        "peak_zone": {"zone_id": 2, "name": "Bandra Kurla", "rides": 1840}
    }

@router.get("/zone/{zone_id}")
async def get_zone_ride_stats(zone_id: int):
    """Per-zone ride stats"""
    if zone_id not in range(1, 13):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid zone_id")
    return {
        "zone_id": zone_id,
        "total_rides_today": random.randint(200, 2000),
        "avg_surge": round(random.uniform(1.0, 2.5), 2),
        "revenue_inr": random.randint(50000, 400000),
        "top_vehicle": "UberGo",
        "cancellation_rate_pct": round(random.uniform(10, 25), 1)
    }
