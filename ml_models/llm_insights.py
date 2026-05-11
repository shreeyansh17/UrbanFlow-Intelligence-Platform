"""
Urban Pulse — LLM Business Insights Engine
Uses Claude API to answer natural language questions about the data
This is the flagship AI feature that makes recruiters go WOW
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional
import anthropic
import pandas as pd
from loguru import logger


SYSTEM_PROMPT = """You are Urban Pulse AI, a senior data analyst assistant for a ride-hailing 
and food delivery platform serving Mumbai. You have access to real-time KPI summaries and can 
answer business questions clearly and concisely.

When answering:
- Lead with the KEY insight in 1 sentence
- Support with 2-3 specific data points
- End with 1 actionable recommendation
- Use Indian currency (₹) and Indian context
- Be specific, not generic — cite actual numbers from the data provided

Format: Plain paragraphs. No bullet overload. Sound like a smart analyst, not a chatbot."""


class LLMInsightsEngine:
    """
    Answers business questions about Urban Pulse data using Claude AI.
    Takes pre-computed KPI summaries and generates natural language insights.
    """

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
        self.conversation_history = []
        logger.info("LLM Insights Engine initialized with Claude")

    def _build_data_context(self, kpi_summary: dict) -> str:
        """Build a structured data context string for the LLM"""
        return f"""
=== URBAN PULSE LIVE KPI SUMMARY ===
Report Time: {datetime.now().strftime('%Y-%m-%d %H:%M IST')}

RIDES (Last 24 Hours):
- Total Rides: {kpi_summary.get('total_rides', 'N/A'):,}
- Completed: {kpi_summary.get('completed_rides', 'N/A'):,}
- Cancelled: {kpi_summary.get('cancelled_rides', 'N/A'):,}
- Completion Rate: {kpi_summary.get('completion_rate', 0):.1f}%
- Total Revenue: ₹{kpi_summary.get('ride_revenue', 0):,.0f}
- Avg Fare: ₹{kpi_summary.get('avg_fare', 0):.2f}
- Avg Surge: {kpi_summary.get('avg_surge', 1.0):.2f}x
- Peak Zone: {kpi_summary.get('peak_ride_zone', 'N/A')}

FOOD ORDERS (Last 24 Hours):
- Total Orders: {kpi_summary.get('total_orders', 'N/A'):,}
- Total GMV: ₹{kpi_summary.get('total_gmv', 0):,.0f}
- Avg Order Value: ₹{kpi_summary.get('avg_order_value', 0):.2f}
- Avg Delivery Time: {kpi_summary.get('avg_delivery_time', 0):.1f} min
- Top Restaurant Zone: {kpi_summary.get('top_restaurant_zone', 'N/A')}
- Rain Orders: {kpi_summary.get('rain_orders', 0):,}

ML PREDICTIONS:
- Tomorrow Peak Hour: {kpi_summary.get('predicted_peak_hour', 'N/A')}
- Surge Risk Zones: {kpi_summary.get('surge_risk_zones', [])}
- Anomalies Detected Today: {kpi_summary.get('anomalies_today', 0)}

ZONE PERFORMANCE (Top 3 by Revenue):
{json.dumps(kpi_summary.get('top_zones', []), indent=2)}
=====================================
"""

    def ask(self, question: str, kpi_summary: dict = None, use_history: bool = True) -> str:
        """
        Ask a natural language question about the data.

        Args:
            question: Business question in plain English/Hindi-English
            kpi_summary: Pre-computed KPI dictionary
            use_history: Maintain conversation context

        Returns:
            str: AI-generated business insight
        """
        if kpi_summary is None:
            kpi_summary = self._get_demo_kpis()

        data_context = self._build_data_context(kpi_summary)

        user_message = f"""
DATA CONTEXT:
{data_context}

QUESTION: {question}

Answer based strictly on the data provided above.
"""

        if use_history:
            self.conversation_history.append({"role": "user", "content": user_message})
            messages = self.conversation_history
        else:
            messages = [{"role": "user", "content": user_message}]

        response = self.client.messages.create(
            model=self.model,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=messages
        )

        answer = response.content[0].text

        if use_history:
            self.conversation_history.append({"role": "assistant", "content": answer})

            # Keep history manageable (last 10 turns)
            if len(self.conversation_history) > 20:
                self.conversation_history = self.conversation_history[-20:]

        logger.info(f"LLM Q: {question[:60]}... | Tokens: {response.usage.input_tokens}in/{response.usage.output_tokens}out")
        return answer

    def generate_daily_report(self, kpi_summary: dict) -> str:
        """Auto-generate a daily executive summary"""
        prompt = """Generate a concise daily executive report for our Urban Pulse platform. 
Include: 1) Overall performance vs yesterday, 2) Top 3 highlights, 
3) Top 2 concerns, 4) Key recommendation for tomorrow's operations.
Keep it under 250 words. Sound like a McKinsey analyst."""

        return self.ask(prompt, kpi_summary, use_history=False)

    def explain_surge(self, zone_id: int, surge_value: float, kpi_summary: dict) -> str:
        """Explain why surge is happening in a specific zone"""
        prompt = f"""Zone {zone_id} is currently showing {surge_value}x surge pricing. 
Explain likely reasons based on current conditions and recommend 2 actions to normalize it."""
        return self.ask(prompt, kpi_summary, use_history=False)

    def predict_demand_insight(self, zone_id: int, forecast_data: dict, kpi_summary: dict) -> str:
        """Natural language explanation of demand forecast"""
        kpi_summary["forecast"] = forecast_data
        prompt = f"""Based on demand forecasting for Zone {zone_id}, 
explain the expected demand pattern for next 24 hours and suggest optimal driver/restaurant deployment."""
        return self.ask(prompt, kpi_summary, use_history=False)

    def reset_conversation(self):
        self.conversation_history = []
        logger.info("Conversation history cleared")

    def _get_demo_kpis(self) -> dict:
        """Demo KPIs when no real data is available"""
        return {
            "total_rides": 12450,
            "completed_rides": 10580,
            "cancelled_rides": 1870,
            "completion_rate": 85.0,
            "ride_revenue": 1876500,
            "avg_fare": 177.3,
            "avg_surge": 1.28,
            "peak_ride_zone": "Bandra Kurla (Zone 2)",
            "total_orders": 8920,
            "total_gmv": 2156800,
            "avg_order_value": 241.7,
            "avg_delivery_time": 32.4,
            "top_restaurant_zone": "Lower Parel (Zone 6)",
            "rain_orders": 1240,
            "predicted_peak_hour": "6 PM - 8 PM",
            "surge_risk_zones": ["Airport Zone", "Andheri West"],
            "anomalies_today": 43,
            "top_zones": [
                {"zone": "Bandra Kurla", "revenue": 380000, "rides": 1840},
                {"zone": "Lower Parel", "revenue": 295000, "rides": 1420},
                {"zone": "Powai",        "revenue": 198000, "rides": 1150},
            ]
        }


# ─── CLI Demo ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    engine = LLMInsightsEngine()
    kpis = engine._get_demo_kpis()

    questions = [
        "Which zones should I deploy more drivers to right now?",
        "Why is our cancellation rate high today and how do I fix it?",
        "Rain impact kar raha hai delivery pe? Kya karna chahiye?",
        "Give me a daily executive summary for today's operations.",
    ]

    print("\n" + "="*60)
    print("URBAN PULSE AI — BUSINESS INSIGHTS DEMO")
    print("="*60)

    for q in questions:
        print(f"\n❓ {q}")
        print("-" * 40)
        answer = engine.ask(q, kpis, use_history=True)
        print(f"🤖 {answer}")
        print()
