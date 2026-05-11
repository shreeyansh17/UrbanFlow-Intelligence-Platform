"""
Urban Pulse — FastAPI Backend
Production-ready REST API serving ML predictions,
live KPIs, and business insights
"""

import os
import sys
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional
import asyncio

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from loguru import logger

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from api.routers import rides, orders, predictions, insights, health
from api.schemas.common import APIResponse

# ─── App Startup / Shutdown ───────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models and connections on startup"""
    logger.info("🚀 Urban Pulse API starting up...")

    # Load ML models into app state
    try:
        from ml_models.surge_prediction import SurgePredictionModel
        app.state.surge_model = SurgePredictionModel.load()
        logger.success("✅ Surge prediction model loaded")
    except Exception as e:
        logger.warning(f"⚠️ Surge model not found ({e}) — using fallback")
        app.state.surge_model = None

    try:
        from ml_models.eta_prediction import ETAPredictionModel
        app.state.eta_model = ETAPredictionModel()
        logger.success("✅ ETA prediction model loaded")
    except Exception as e:
        logger.warning(f"⚠️ ETA model not found ({e})")
        app.state.eta_model = None

    try:
        from ml_models.anomaly_detection import RideAnomalyDetector
        app.state.anomaly_detector = RideAnomalyDetector.load()
        logger.success("✅ Anomaly detector loaded")
    except Exception as e:
        logger.warning(f"⚠️ Anomaly detector not found ({e})")
        app.state.anomaly_detector = None

    logger.success("🎯 Urban Pulse API ready!")
    yield

    logger.info("👋 Urban Pulse API shutting down...")


# ─── App Configuration ────────────────────────────────────────────────────────

app = FastAPI(
    title="Urban Pulse Intelligence Platform API",
    description="""
## 🏙️ Urban Pulse — Ride & Food Delivery Analytics API

End-to-end data platform for urban mobility intelligence.

### Features
- 🚗 **Real-time ride analytics** — surge pricing, demand forecasting
- 🍔 **Food delivery intelligence** — ETA prediction, restaurant rankings
- 🤖 **AI-powered insights** — Natural language business analytics (Claude)
- 🚨 **Anomaly detection** — Fraud detection, demand spikes
- 📊 **Live KPI dashboard** — Zone-level metrics, driver performance

### Tech Stack
`PySpark` `Kafka` `Snowflake` `dbt` `XGBoost` `Prophet` `LSTM` `Claude AI`
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    contact={"name": "Urban Pulse Team", "email": "data@urbanpulse.in"}
)

# ─── Middleware ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(health.router,       prefix="/api/v1",            tags=["Health"])
app.include_router(rides.router,        prefix="/api/v1/rides",       tags=["Rides"])
app.include_router(orders.router,       prefix="/api/v1/orders",      tags=["Food Orders"])
app.include_router(predictions.router,  prefix="/api/v1/predictions", tags=["ML Predictions"])
app.include_router(insights.router,     prefix="/api/v1/insights",    tags=["AI Insights"])


# ─── Root Endpoint ────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return {
        "name": "Urban Pulse Intelligence Platform",
        "version": "1.0.0",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "docs": "/docs",
        "endpoints": {
            "health":      "/api/v1/health",
            "rides":       "/api/v1/rides/kpis",
            "orders":      "/api/v1/orders/kpis",
            "predictions": "/api/v1/predictions/surge",
            "insights":    "/api/v1/insights/ask",
        }
    }


@app.get("/api/v1/kpis/dashboard", tags=["Dashboard"])
async def get_dashboard_kpis():
    """
    Master dashboard endpoint — returns all KPIs in one call.
    Used by Power BI and Plotly dashboard.
    """
    now = datetime.now()

    # In production, this queries Snowflake / PostgreSQL
    # Here we return computed mock data for demo
    return {
        "timestamp": now.isoformat(),
        "period": "last_24_hours",
        "rides": {
            "total": 12450,
            "completed": 10580,
            "cancelled": 1870,
            "completion_rate_pct": 85.0,
            "revenue_inr": 1876500,
            "avg_fare_inr": 177.3,
            "avg_surge": 1.28,
            "avg_distance_km": 8.4,
        },
        "orders": {
            "total": 8920,
            "gmv_inr": 2156800,
            "avg_order_value_inr": 241.7,
            "avg_delivery_minutes": 32.4,
            "avg_food_rating": 4.1,
            "rain_orders": 1240,
        },
        "platform_combined": {
            "total_revenue_inr": 4033300,
            "total_unique_users": 18400,
            "active_drivers": 342,
            "active_delivery_agents": 218,
            "anomalies_detected": 43,
        },
        "zone_rankings": [
            {"zone_id": 2, "zone_name": "Bandra Kurla",  "revenue": 380000, "rank": 1},
            {"zone_id": 6, "zone_name": "Lower Parel",   "revenue": 295000, "rank": 2},
            {"zone_id": 8, "zone_name": "Powai",         "revenue": 198000, "rank": 3},
        ],
        "ml_signals": {
            "surge_risk_zones": [12, 1],
            "predicted_peak_hour": 19,
            "demand_trend": "increasing",
        }
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 8000)),
        reload=True,
        log_level="info"
    )
