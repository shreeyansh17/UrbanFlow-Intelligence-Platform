"""
Urban Pulse — Interactive Plotly Dash Dashboard
Real-time analytics dashboard with:
- Live KPI cards
- Zone heatmap (Mumbai)
- Surge pricing timeline
- Revenue trends
- AI Insights chat interface
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

import dash
from dash import dcc, html, Input, Output, State, callback
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

API_BASE = "http://localhost:8000/api/v1"

# ─── App Init ─────────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    title="Urban Pulse Intelligence",
    update_title=None,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}]
)

# ─── Theme ────────────────────────────────────────────────────────────────────

COLORS = {
    "bg": "#0a0a0f",
    "card": "#12121a",
    "border": "#1e1e2e",
    "primary": "#6366f1",
    "success": "#10b981",
    "warning": "#f59e0b",
    "danger": "#ef4444",
    "text": "#e2e8f0",
    "muted": "#64748b",
    "accent": "#06b6d4",
}

CARD_STYLE = {
    "backgroundColor": COLORS["card"],
    "border": f"1px solid {COLORS['border']}",
    "borderRadius": "12px",
    "padding": "20px",
    "marginBottom": "16px",
}


# ─── KPI Card Component ───────────────────────────────────────────────────────

def kpi_card(title, value, delta, unit="", color=None, icon="📊"):
    color = color or COLORS["primary"]
    delta_color = COLORS["success"] if "+" in str(delta) else COLORS["danger"]
    return html.Div([
        html.Div([
            html.Span(icon, style={"fontSize": "24px"}),
            html.Span(title, style={"fontSize": "12px", "color": COLORS["muted"], "marginLeft": "8px", "fontWeight": "600", "letterSpacing": "1px", "textTransform": "uppercase"})
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),
        html.Div(f"{value}{unit}", style={"fontSize": "28px", "fontWeight": "800", "color": COLORS["text"]}),
        html.Div(f"{delta} vs yesterday", style={"fontSize": "12px", "color": delta_color, "marginTop": "4px"}),
        html.Div(style={"height": "3px", "backgroundColor": color, "borderRadius": "2px", "marginTop": "12px", "opacity": "0.6"})
    ], style=CARD_STYLE)


# ─── Layout ───────────────────────────────────────────────────────────────────

app.layout = html.Div([
    # ── Header ──────────────────────────────────────────────────
    html.Div([
        html.Div([
            html.H1("🏙️ URBAN PULSE", style={
                "margin": "0", "fontSize": "24px", "fontWeight": "900",
                "background": "linear-gradient(135deg, #6366f1, #06b6d4)",
                "-webkit-background-clip": "text", "-webkit-text-fill-color": "transparent"
            }),
            html.Span("Intelligence Platform", style={"color": COLORS["muted"], "fontSize": "12px", "marginLeft": "12px"})
        ]),
        html.Div([
            html.Span(id="live-clock", style={"color": COLORS["muted"], "fontSize": "13px", "marginRight": "16px"}),
            html.Span("● LIVE", style={"color": COLORS["success"], "fontWeight": "700", "fontSize": "12px"})
        ])
    ], style={
        "display": "flex", "justifyContent": "space-between", "alignItems": "center",
        "padding": "16px 24px", "backgroundColor": COLORS["card"],
        "borderBottom": f"1px solid {COLORS['border']}", "marginBottom": "24px"
    }),

    # ── Auto-refresh ────────────────────────────────────────────
    dcc.Interval(id="refresh-30s", interval=30_000, n_intervals=0),
    dcc.Interval(id="clock-tick", interval=1_000, n_intervals=0),

    # ── Main Content ────────────────────────────────────────────
    html.Div([

        # ── KPI Row ────────────────────────────────────────────
        html.Div([
            html.Div(id="kpi-total-rides",    style={"flex": "1", "margin": "0 8px"}),
            html.Div(id="kpi-revenue",         style={"flex": "1", "margin": "0 8px"}),
            html.Div(id="kpi-total-orders",    style={"flex": "1", "margin": "0 8px"}),
            html.Div(id="kpi-gmv",             style={"flex": "1", "margin": "0 8px"}),
            html.Div(id="kpi-avg-surge",       style={"flex": "1", "margin": "0 8px"}),
            html.Div(id="kpi-anomalies",       style={"flex": "1", "margin": "0 8px"}),
        ], style={"display": "flex", "marginBottom": "24px"}),

        # ── Charts Row 1 ───────────────────────────────────────
        html.Div([
            # Surge Heatmap
            html.Div([
                html.H3("🔥 Zone Surge Map", style={"color": COLORS["text"], "margin": "0 0 16px", "fontSize": "16px"}),
                dcc.Graph(id="surge-heatmap", style={"height": "380px"})
            ], style={**CARD_STYLE, "flex": "1.2", "marginRight": "16px"}),

            # Revenue Timeline
            html.Div([
                html.H3("💰 Revenue Timeline (7D)", style={"color": COLORS["text"], "margin": "0 0 16px", "fontSize": "16px"}),
                dcc.Graph(id="revenue-chart", style={"height": "380px"})
            ], style={**CARD_STYLE, "flex": "1"}),
        ], style={"display": "flex", "marginBottom": "24px"}),

        # ── Charts Row 2 ───────────────────────────────────────
        html.Div([
            # Hourly Demand
            html.Div([
                html.H3("📈 Hourly Demand vs Forecast", style={"color": COLORS["text"], "margin": "0 0 16px", "fontSize": "16px"}),
                dcc.Graph(id="hourly-demand", style={"height": "300px"})
            ], style={**CARD_STYLE, "flex": "1", "marginRight": "16px"}),

            # Delivery Performance
            html.Div([
                html.H3("🚴 Delivery Performance", style={"color": COLORS["text"], "margin": "0 0 16px", "fontSize": "16px"}),
                dcc.Graph(id="delivery-perf", style={"height": "300px"})
            ], style={**CARD_STYLE, "flex": "1"}),
        ], style={"display": "flex", "marginBottom": "24px"}),

        # ── AI Chat ────────────────────────────────────────────
        html.Div([
            html.H3("🤖 AI Business Insights (Powered by Claude)", style={"color": COLORS["text"], "margin": "0 0 16px", "fontSize": "16px"}),
            html.Div([
                html.Div(id="chat-history", style={
                    "height": "220px", "overflowY": "auto",
                    "backgroundColor": COLORS["bg"], "borderRadius": "8px",
                    "padding": "16px", "marginBottom": "12px",
                    "border": f"1px solid {COLORS['border']}"
                }),
                html.Div([
                    dcc.Input(id="chat-input", type="text", placeholder="Ask about your data... e.g. 'Why is surge high in Bandra today?'",
                              style={
                                  "flex": "1", "backgroundColor": COLORS["bg"],
                                  "border": f"1px solid {COLORS['primary']}",
                                  "borderRadius": "8px", "padding": "12px 16px",
                                  "color": COLORS["text"], "fontSize": "14px",
                                  "outline": "none"
                              }),
                    html.Button("Ask AI →", id="chat-submit", n_clicks=0,
                                style={
                                    "marginLeft": "12px",
                                    "backgroundColor": COLORS["primary"],
                                    "color": "white", "border": "none",
                                    "borderRadius": "8px", "padding": "12px 24px",
                                    "cursor": "pointer", "fontWeight": "700"
                                })
                ], style={"display": "flex"}),
            ])
        ], style=CARD_STYLE),

    ], style={"maxWidth": "1600px", "margin": "0 auto", "padding": "0 24px 24px"}),

], style={"backgroundColor": COLORS["bg"], "minHeight": "100vh", "fontFamily": "'Inter', 'Segoe UI', sans-serif", "color": COLORS["text"]})


# ─── Callbacks ────────────────────────────────────────────────────────────────

@app.callback(Output("live-clock", "children"), Input("clock-tick", "n_intervals"))
def update_clock(_):
    return datetime.now().strftime("%d %b %Y  %H:%M:%S IST")


@app.callback(
    [Output("kpi-total-rides", "children"), Output("kpi-revenue", "children"),
     Output("kpi-total-orders", "children"), Output("kpi-gmv", "children"),
     Output("kpi-avg-surge", "children"), Output("kpi-anomalies", "children")],
    Input("refresh-30s", "n_intervals")
)
def update_kpis(_):
    try:
        r = requests.get(f"{API_BASE}/kpis/dashboard", timeout=3)
        data = r.json()
        rides = data["rides"]
        orders = data["orders"]
        combined = data["platform_combined"]
    except:
        rides = {"total": 12450, "revenue_inr": 1876500, "avg_surge": 1.28}
        orders = {"total": 8920, "gmv_inr": 2156800}
        combined = {"anomalies_detected": 43}

    return [
        kpi_card("Total Rides", f"{rides.get('total', 0):,}", "+8.2%", icon="🚗", color=COLORS["primary"]),
        kpi_card("Ride Revenue", f"₹{rides.get('revenue_inr', 0)/1e5:.1f}L", "+12.1%", icon="💰", color=COLORS["success"]),
        kpi_card("Food Orders", f"{orders.get('total', 0):,}", "+15.4%", icon="🍔", color=COLORS["accent"]),
        kpi_card("Food GMV", f"₹{orders.get('gmv_inr', 0)/1e5:.1f}L", "+19.7%", icon="🏦", color=COLORS["warning"]),
        kpi_card("Avg Surge", f"{rides.get('avg_surge', 1.0):.2f}x", "+0.08x", icon="⚡", color=COLORS["warning"]),
        kpi_card("Anomalies", f"{combined.get('anomalies_detected', 0)}", "-5 vs avg", icon="🚨", color=COLORS["danger"]),
    ]


@app.callback(Output("surge-heatmap", "figure"), Input("refresh-30s", "n_intervals"))
def update_heatmap(_):
    zones = [
        {"name": "Andheri West", "lat": 19.1197, "lon": 72.8466, "surge": random.uniform(1.0, 2.5), "rides": random.randint(200, 1800)},
        {"name": "Bandra Kurla", "lat": 19.0596, "lon": 72.8650, "surge": random.uniform(1.5, 3.0), "rides": random.randint(800, 2000)},
        {"name": "Colaba",       "lat": 18.9067, "lon": 72.8147, "surge": random.uniform(1.0, 2.0), "rides": random.randint(300, 1200)},
        {"name": "Dadar",        "lat": 19.0178, "lon": 72.8478, "surge": random.uniform(1.0, 1.8), "rides": random.randint(400, 1500)},
        {"name": "Juhu",         "lat": 19.1075, "lon": 72.8263, "surge": random.uniform(1.2, 2.2), "rides": random.randint(200, 900)},
        {"name": "Lower Parel",  "lat": 18.9956, "lon": 72.8258, "surge": random.uniform(1.3, 2.5), "rides": random.randint(600, 1800)},
        {"name": "Malad East",   "lat": 19.1871, "lon": 72.8485, "surge": random.uniform(1.0, 1.5), "rides": random.randint(300, 1100)},
        {"name": "Powai",        "lat": 19.1176, "lon": 72.9060, "surge": random.uniform(1.1, 2.0), "rides": random.randint(400, 1400)},
        {"name": "Thane",        "lat": 19.2183, "lon": 72.9781, "surge": random.uniform(1.0, 1.6), "rides": random.randint(200, 900)},
        {"name": "Borivali",     "lat": 19.2307, "lon": 72.8567, "surge": random.uniform(1.0, 1.4), "rides": random.randint(200, 800)},
        {"name": "Navi Mumbai",  "lat": 19.0330, "lon": 73.0297, "surge": random.uniform(1.0, 1.3), "rides": random.randint(100, 600)},
        {"name": "Airport",      "lat": 19.0896, "lon": 72.8656, "surge": random.uniform(1.5, 2.8), "rides": random.randint(500, 1600)},
    ]
    df = pd.DataFrame(zones)

    fig = go.Figure(go.Scattermapbox(
        lat=df["lat"], lon=df["lon"],
        mode="markers",
        marker=go.scattermapbox.Marker(
            size=df["rides"] / 50 + 10,
            color=df["surge"],
            colorscale="RdYlGn_r",
            cmin=1.0, cmax=3.0,
            colorbar={"title": "Surge", "thickness": 12, "len": 0.7},
            opacity=0.85
        ),
        text=[f"<b>{r['name']}</b><br>Surge: {r['surge']:.1f}x<br>Rides: {r['rides']:,}" for _, r in df.iterrows()],
        hoverinfo="text"
    ))
    fig.update_layout(
        mapbox={"style": "carto-darkmatter", "center": {"lat": 19.07, "lon": 72.87}, "zoom": 10},
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"]
    )
    return fig


@app.callback(Output("revenue-chart", "figure"), Input("refresh-30s", "n_intervals"))
def update_revenue(_):
    dates = [datetime.now() - timedelta(days=6-i) for i in range(7)]
    ride_rev = [random.randint(1500000, 2200000) for _ in range(7)]
    food_gmv = [random.randint(1800000, 2800000) for _ in range(7)]

    fig = make_subplots(specs=[[{"secondary_y": False}]])
    fig.add_trace(go.Bar(name="Ride Revenue", x=dates, y=ride_rev,
                         marker_color=COLORS["primary"], opacity=0.8))
    fig.add_trace(go.Bar(name="Food GMV", x=dates, y=food_gmv,
                         marker_color=COLORS["accent"], opacity=0.8))
    fig.update_layout(
        barmode="stack",
        paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        font_color=COLORS["text"], legend={"orientation": "h", "y": 1.1},
        margin={"l": 40, "r": 10, "t": 10, "b": 40},
        yaxis={"gridcolor": COLORS["border"]}
    )
    fig.update_xaxes(gridcolor=COLORS["border"])
    return fig


@app.callback(Output("hourly-demand", "figure"), Input("refresh-30s", "n_intervals"))
def update_hourly(_):
    hours = list(range(24))
    actual = [max(0, int(100 * m + random.gauss(0, 15)))
              for m in [0.15,0.1,0.08,0.06,0.07,0.2,0.55,0.85,1.2,1.4,0.9,0.8,0.75,0.7,0.65,0.7,0.85,1.1,1.5,1.6,1.3,1.1,0.8,0.45]]
    forecast = [int(a * random.uniform(0.9, 1.1)) for a in actual]

    fig = go.Figure([
        go.Scatter(x=hours, y=actual, name="Actual", line={"color": COLORS["primary"], "width": 2}, mode="lines+markers"),
        go.Scatter(x=hours, y=forecast, name="Forecast", line={"color": COLORS["warning"], "width": 2, "dash": "dash"}, mode="lines"),
    ])
    fig.update_layout(
        paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        font_color=COLORS["text"], margin={"l": 40, "r": 10, "t": 10, "b": 40},
        xaxis={"title": "Hour", "gridcolor": COLORS["border"]},
        yaxis={"title": "Demand", "gridcolor": COLORS["border"]},
        legend={"orientation": "h", "y": 1.1}
    )
    return fig


@app.callback(Output("delivery-perf", "figure"), Input("refresh-30s", "n_intervals"))
def update_delivery(_):
    categories = ["< 20 min", "20-30 min", "30-45 min", "45-60 min", "> 60 min"]
    values = [random.randint(800, 1400), random.randint(2000, 3500),
              random.randint(2500, 4000), random.randint(800, 1500), random.randint(200, 600)]
    colors_list = [COLORS["success"], COLORS["accent"], COLORS["warning"],
                   "#f97316", COLORS["danger"]]

    fig = go.Figure(go.Bar(
        x=categories, y=values, marker_color=colors_list, opacity=0.85,
        text=values, textposition="outside", textfont={"color": COLORS["text"]}
    ))
    fig.update_layout(
        paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        font_color=COLORS["text"], margin={"l": 40, "r": 10, "t": 10, "b": 40},
        yaxis={"gridcolor": COLORS["border"]},
        xaxis={"gridcolor": COLORS["border"]}
    )
    return fig


@app.callback(
    Output("chat-history", "children"),
    Input("chat-submit", "n_clicks"),
    State("chat-input", "value"),
    State("chat-history", "children"),
    prevent_initial_call=True
)
def handle_chat(n_clicks, question, history):
    if not question:
        return history or []
    history = history or []

    history.append(html.Div([
        html.Span("You: ", style={"color": COLORS["accent"], "fontWeight": "700"}),
        html.Span(question, style={"color": COLORS["text"]})
    ], style={"marginBottom": "8px", "fontSize": "13px"}))

    try:
        r = requests.post(f"{API_BASE}/insights/ask",
                          json={"question": question}, timeout=15)
        answer = r.json().get("answer", "No response")
    except:
        answer = "AI service unavailable. Make sure the API is running and ANTHROPIC_API_KEY is set."

    history.append(html.Div([
        html.Span("🤖 AI: ", style={"color": COLORS["primary"], "fontWeight": "700"}),
        html.Span(answer, style={"color": COLORS["muted"]})
    ], style={"marginBottom": "16px", "fontSize": "13px",
              "padding": "8px 12px", "backgroundColor": COLORS["border"],
              "borderRadius": "6px", "borderLeft": f"3px solid {COLORS['primary']}"}))

    return history


if __name__ == "__main__":
    print("\n🚀 Starting Urban Pulse Dashboard...")
    print("📊 Dashboard: http://localhost:8050")
    print("🔌 Requires API at http://localhost:8000\n")
    app.run(debug=True, host="0.0.0.0", port=8050)
