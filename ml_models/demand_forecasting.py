"""
Urban Pulse — Demand Forecasting Model
Facebook Prophet for 7-day ride & order demand prediction per zone
"""

import json
import pickle
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger
from prophet import Prophet
from prophet.diagnostics import cross_validation, performance_metrics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings("ignore")

MODEL_DIR = Path("../models/saved")
MODEL_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR = Path("../models/plots")
PLOTS_DIR.mkdir(parents=True, exist_ok=True)


class DemandForecastModel:
    """
    Forecasts hourly ride/order demand per zone using Facebook Prophet.
    Handles seasonality: daily, weekly, monthly, and Indian holidays.
    """

    def __init__(self, platform: str = "uber"):
        self.platform = platform  # "uber" or "zomato"
        self.models = {}          # zone_id -> Prophet model
        self.forecasts = {}       # zone_id -> forecast df
        self.metrics = {}

    def prepare_zone_data(self, df: pd.DataFrame, zone_id: int) -> pd.DataFrame:
        """Prepare Prophet-format time series for one zone"""
        df["event_ts"] = pd.to_datetime(df["timestamp"])

        if self.platform == "uber":
            zone_col = "pickup_zone"
            value_col = "ride_id"
        else:
            zone_col = "delivery_zone"
            value_col = "order_id"

        zone_df = df[df[zone_col] == zone_id].copy()

        # Resample to hourly counts
        ts = (
            zone_df.set_index("event_ts")
            .resample("h")[value_col]
            .count()
            .reset_index()
        )
        ts.columns = ["ds", "y"]
        ts = ts[ts["y"] > 0]  # Remove zero-demand hours

        logger.info(f"Zone {zone_id}: {len(ts)} hourly data points")
        return ts

    def add_indian_holidays(self, model: Prophet) -> Prophet:
        """Add major Indian holidays as regressors"""
        holidays = pd.DataFrame({
            "holiday": [
                "republic_day", "holi", "independence_day",
                "gandhi_jayanti", "diwali", "christmas", "new_year"
            ],
            "ds": pd.to_datetime([
                "2024-01-26", "2024-03-25", "2024-08-15",
                "2024-10-02", "2024-11-01", "2024-12-25", "2025-01-01"
            ]),
            "lower_window": -1,
            "upper_window": 1,
        })
        model.holidays = holidays
        return model

    def train_zone_model(self, ts: pd.DataFrame, zone_id: int) -> Prophet:
        """Train Prophet model for a single zone"""
        model = Prophet(
            changepoint_prior_scale=0.1,
            seasonality_prior_scale=10.0,
            holidays_prior_scale=10.0,
            seasonality_mode="multiplicative",
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=True,
            interval_width=0.90,
        )

        # Custom hourly seasonality
        model.add_seasonality(
            name="hourly",
            period=1,
            fourier_order=8,
        )

        model = self.add_indian_holidays(model)
        model.fit(ts)
        logger.success(f"Zone {zone_id} model trained on {len(ts)} points")
        return model

    def train_all_zones(self, df: pd.DataFrame, zones: list = None):
        if zones is None:
            zones = list(range(1, 13))

        logger.info(f"Training demand forecast for {len(zones)} zones...")

        for zone_id in zones:
            try:
                ts = self.prepare_zone_data(df, zone_id)
                if len(ts) < 48:
                    logger.warning(f"Zone {zone_id}: insufficient data ({len(ts)} points), skipping")
                    continue

                model = self.train_zone_model(ts, zone_id)
                self.models[zone_id] = model

            except Exception as e:
                logger.error(f"Zone {zone_id} training failed: {e}")

        logger.success(f"Trained {len(self.models)}/{len(zones)} zone models")

    def forecast(self, zone_id: int, periods: int = 168) -> pd.DataFrame:
        """Forecast next `periods` hours (default: 7 days)"""
        if zone_id not in self.models:
            raise ValueError(f"No model for zone {zone_id}")

        model = self.models[zone_id]
        future = model.make_future_dataframe(periods=periods, freq="h")
        forecast = model.predict(future)

        # Keep only future predictions
        last_train = model.history["ds"].max()
        forecast = forecast[forecast["ds"] > last_train].copy()
        forecast["zone_id"] = zone_id
        forecast["yhat"] = forecast["yhat"].clip(lower=0).round().astype(int)
        forecast["yhat_lower"] = forecast["yhat_lower"].clip(lower=0).round().astype(int)
        forecast["yhat_upper"] = forecast["yhat_upper"].clip(lower=0).round().astype(int)

        self.forecasts[zone_id] = forecast
        return forecast

    def forecast_all_zones(self, periods: int = 168) -> pd.DataFrame:
        """Forecast all trained zones and return combined DataFrame"""
        all_forecasts = []
        for zone_id in self.models:
            try:
                fc = self.forecast(zone_id, periods)
                all_forecasts.append(fc[["ds", "zone_id", "yhat", "yhat_lower", "yhat_upper",
                                         "trend", "weekly", "daily"]])
            except Exception as e:
                logger.error(f"Forecast failed for zone {zone_id}: {e}")

        combined = pd.concat(all_forecasts, ignore_index=True)
        logger.success(f"Generated {len(combined):,} hourly forecasts across {len(self.models)} zones")
        return combined

    def evaluate(self, zone_id: int) -> dict:
        """Cross-validate a zone model and return MAPE"""
        if zone_id not in self.models:
            return {}

        model = self.models[zone_id]
        try:
            cv_results = cross_validation(
                model, initial="30 days", period="7 days", horizon="7 days"
            )
            perf = performance_metrics(cv_results)
            mape = perf["mape"].mean()
            rmse = perf["rmse"].mean()

            self.metrics[zone_id] = {
                "mape": round(mape, 4),
                "rmse": round(rmse, 2),
                "zone_id": zone_id
            }
            logger.info(f"Zone {zone_id} → MAPE: {mape:.2%}, RMSE: {rmse:.1f}")
            return self.metrics[zone_id]
        except Exception as e:
            logger.warning(f"CV failed for zone {zone_id}: {e}")
            return {}

    def plot_zone_forecast(self, zone_id: int):
        if zone_id not in self.models or zone_id not in self.forecasts:
            return

        model = self.models[zone_id]
        fc = self.forecasts[zone_id]

        fig, axes = plt.subplots(2, 1, figsize=(14, 8))

        # Forecast plot
        ax = axes[0]
        history = model.history
        ax.plot(history["ds"], history["y"], "k.", alpha=0.3, label="Actual")
        ax.plot(fc["ds"], fc["yhat"], "b-", label="Forecast")
        ax.fill_between(fc["ds"], fc["yhat_lower"], fc["yhat_upper"],
                        alpha=0.3, color="blue", label="90% CI")
        ax.set_title(f"Zone {zone_id} — {self.platform.title()} Demand Forecast (7 days)")
        ax.set_ylabel("Demand (events/hour)")
        ax.legend()
        ax.grid(alpha=0.3)

        # Weekly pattern
        ax2 = axes[1]
        weekly = fc.groupby(fc["ds"].dt.dayofweek)["yhat"].mean()
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        ax2.bar(days, weekly.values, color="steelblue", alpha=0.7)
        ax2.set_title("Forecasted Weekly Demand Pattern")
        ax2.set_ylabel("Avg Hourly Demand")
        ax2.grid(alpha=0.3, axis="y")

        plt.tight_layout()
        path = PLOTS_DIR / f"forecast_zone_{zone_id}_{self.platform}.png"
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        logger.info(f"Plot saved: {path}")

    def get_peak_hours(self, zone_id: int) -> dict:
        """Return predicted peak hours for the next 7 days"""
        if zone_id not in self.forecasts:
            self.forecast(zone_id)
        fc = self.forecasts[zone_id].copy()
        fc["hour"] = fc["ds"].dt.hour
        hourly_avg = fc.groupby("hour")["yhat"].mean().sort_values(ascending=False)

        return {
            "top_3_peak_hours": hourly_avg.head(3).index.tolist(),
            "lowest_demand_hour": int(hourly_avg.idxmin()),
            "peak_demand": int(hourly_avg.max()),
            "off_peak_demand": int(hourly_avg.min()),
        }

    def save(self, path: str = None):
        path = path or str(MODEL_DIR / f"demand_forecast_{self.platform}.pkl")
        with open(path, "wb") as f:
            pickle.dump(self, f)
        with open(path.replace(".pkl", "_metrics.json"), "w") as f:
            json.dump(self.metrics, f, indent=2)
        logger.success(f"Saved demand forecast model → {path}")

    @classmethod
    def load(cls, platform: str = "uber"):
        path = str(MODEL_DIR / f"demand_forecast_{platform}.pkl")
        with open(path, "rb") as f:
            return pickle.load(f)


if __name__ == "__main__":
    import sys
    sys.path.append("../data_generators")
    from uber_generator import UberRideGenerator
    from zomato_generator import ZomatoOrderGenerator

    # Train Uber model
    logger.info("Generating training data...")
    uber_gen = UberRideGenerator()
    uber_df = pd.DataFrame(uber_gen.generate_batch(n=30_000))

    model = DemandForecastModel(platform="uber")
    model.train_all_zones(uber_df, zones=[1, 2, 3, 4, 5])

    # Forecast & evaluate
    forecasts = model.forecast_all_zones(periods=168)
    print(f"\nForecast sample:\n{forecasts.head(10)}")

    for zone_id in [1, 2]:
        model.evaluate(zone_id)
        model.plot_zone_forecast(zone_id)
        peaks = model.get_peak_hours(zone_id)
        print(f"\nZone {zone_id} Peak Hours: {peaks}")

    model.save()
    logger.success("Demand forecast model complete!")
