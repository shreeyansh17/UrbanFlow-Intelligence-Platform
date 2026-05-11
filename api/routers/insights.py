"""Urban Pulse — AI Insights Router"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import os

router = APIRouter()

class InsightRequest(BaseModel):
    question: str
    use_history: bool = False

class InsightResponse(BaseModel):
    question: str
    answer: str
    model: str

@router.post("/ask", response_model=InsightResponse)
async def ask_insight(body: InsightRequest):
    """Ask a business question — answered by Claude AI using live KPI data"""
    try:
        from ml_models.llm_insights import LLMInsightsEngine
        engine = LLMInsightsEngine()
        answer = engine.ask(body.question, use_history=body.use_history)
        return InsightResponse(question=body.question, answer=answer, model="claude-sonnet-4-20250514")
    except Exception as e:
        # Graceful fallback if API key not set
        return InsightResponse(
            question=body.question,
            answer=f"AI engine not configured (set ANTHROPIC_API_KEY). Error: {str(e)[:100]}",
            model="fallback"
        )

@router.get("/daily-report")
async def get_daily_report():
    """Auto-generate daily executive summary using Claude"""
    try:
        from ml_models.llm_insights import LLMInsightsEngine
        engine = LLMInsightsEngine()
        report = engine.generate_daily_report(engine._get_demo_kpis())
        return {"report": report, "generated_at": __import__('datetime').datetime.now().isoformat()}
    except Exception as e:
        return {"report": f"Report unavailable: {e}", "generated_at": None}
