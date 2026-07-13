"""Urban Pulse — Health, Rides, and Orders Routers"""

from datetime import datetime

from fastapi import APIRouter

# ── Health ────────────────────────────────────────────────────────────────────
router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Urban Pulse API",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "api": "operational",
            "ml_models": "operational",
            "database": "operational",
        },
    }
