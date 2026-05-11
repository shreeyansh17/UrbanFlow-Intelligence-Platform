"""
Urban Pulse — Anomaly Detection
Isolation Forest + Statistical methods to detect:
- Fraudulent rides (GPS spoofing, fare manipulation)
- Unusual delivery patterns
- Driver behavior anomalies
- Sudden demand spikes
"""

import json
import pickle
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from loguru import logger
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report
import warnings
warnings.filterwarnings("ignore")

MODEL_DIR = Path("../models/saved")
MODEL_DIR.mkdir(parents=True, exist_ok=True)


class RideAnomalyDetector:
    """
    Detects anomalous rides using Isolation Forest.
    Anomaly types: GPS spoofing, fare fraud, impossible speed, etc.
    """

    FEATURE_COLS = [
        "distance_km", "duration_minutes", "final_fare",
        "fare_per_km", "speed_kmh", "surge_multiplier",
        "hour", "pickup_zone", "dropoff_zone"
    ]

    def __init__(self, contamination: float = 0.05):
        self.contamination = contamination
        self.model = IsolationForest(
            n_estimators=200,
            contamination=contamination,
            max_samples="auto",
            random_state=42,
            n_jobs=-1,
            verbose=0
        )
        self.scaler = StandardScaler()
        self.threshold = None
        self.metrics = {}

    def _add_rule_based_flags(self, df: pd.DataFrame) -> pd.DataFrame:
        """Hard rule-based anomaly flags (domain knowledge)"""
        df = df.copy()
        df["event_ts"] = pd.to_datetime(df["timestamp"])
        df["hour"] = df["event_ts"].dt.hour

        df["flag_impossible_speed"] = (df["speed_kmh"] > 120).astype(int)
        df["flag_zero_distance"]    = (df["distance_km"] < 0.1).astype(int)
        df["flag_fare_too_low"]     = (df["final_fare"] < 20).astype(int)
        df["flag_fare_too_high"]    = (df["final_fare"] > 3000).astype(int)
        df["flag_midnight_surge"]   = ((df["hour"].isin([2, 3, 4])) & (df["surge_multiplier"] > 2.5)).astype(int)

        df["rule_anomaly_score"] = (
            df["flag_impossible_speed"] * 3 +
            df["flag_zero_distance"] * 3 +
            df["flag_fare_too_high"] * 2 +
            df["flag_fare_too_low"] * 1 +
            df["flag_midnight_surge"] * 1
        )
        df["is_rule_anomaly"] = (df["rule_anomaly_score"] >= 2).astype(int)
        return df

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["event_ts"] = pd.to_datetime(df["timestamp"])
        df["hour"] = df["event_ts"].dt.hour
        df["fare_per_km"] = df["final_fare"] / (df["distance_km"] + 1e-5)
        df["speed_kmh"] = df["distance_km"] / (df["duration_minutes"] / 60 + 1e-5)
        df = self._add_rule_based_flags(df)
        return df

    def train(self, df: pd.DataFrame):
        df = self.prepare(df)

        # Remove extreme obvious anomalies for cleaner training
        clean = df[df["is_rule_anomaly"] == 0]
        X = clean[self.FEATURE_COLS].fillna(clean[self.FEATURE_COLS].median())

        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled)

        # Score threshold
        scores = self.model.score_samples(X_scaled)
        self.threshold = np.percentile(scores, 5)

        self.metrics = {
            "n_training_samples": len(X),
            "contamination": self.contamination,
            "anomaly_threshold": float(self.threshold),
            "trained_at": datetime.now().isoformat()
        }
        logger.success(f"Anomaly detector trained on {len(X):,} samples | Threshold: {self.threshold:.3f}")

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.prepare(df)
        X = df[self.FEATURE_COLS].fillna(0)
        X_scaled = self.scaler.transform(X)

        df["anomaly_score"] = self.model.score_samples(X_scaled)
        df["is_ml_anomaly"] = (df["anomaly_score"] < self.threshold).astype(int)

        # Combined flag
        df["is_anomaly"] = ((df["is_ml_anomaly"] == 1) | (df["is_rule_anomaly"] == 1)).astype(int)
        df["anomaly_type"] = "normal"
        df.loc[df["flag_impossible_speed"] == 1, "anomaly_type"] = "impossible_speed"
        df.loc[df["flag_zero_distance"] == 1,    "anomaly_type"] = "zero_distance"
        df.loc[df["flag_fare_too_high"] == 1,    "anomaly_type"] = "fare_manipulation"
        df.loc[df["is_ml_anomaly"] == 1,         "anomaly_type"] = "ml_detected"

        anomaly_count = df["is_anomaly"].sum()
        logger.info(f"Detected {anomaly_count} anomalies ({anomaly_count/len(df)*100:.1f}%) in {len(df)} records")
        return df

    def get_anomaly_summary(self, df: pd.DataFrame) -> dict:
        anomalies = df[df["is_anomaly"] == 1]
        return {
            "total_records": len(df),
            "total_anomalies": len(anomalies),
            "anomaly_rate_pct": round(len(anomalies) / len(df) * 100, 2),
            "by_type": anomalies["anomaly_type"].value_counts().to_dict(),
            "estimated_fraud_loss": round(anomalies["final_fare"].sum(), 2),
            "top_suspicious_zones": anomalies["pickup_zone"].value_counts().head(5).to_dict()
        }

    def save(self, path: str = None):
        path = path or str(MODEL_DIR / "anomaly_detector.pkl")
        with open(path, "wb") as f:
            pickle.dump(self, f)
        with open(path.replace(".pkl", "_metrics.json"), "w") as f:
            json.dump(self.metrics, f, indent=2)
        logger.success(f"Anomaly detector saved → {path}")

    @classmethod
    def load(cls, path: str = None):
        path = path or str(MODEL_DIR / "anomaly_detector.pkl")
        with open(path, "rb") as f:
            return pickle.load(f)


class ZoneAnomalyDetector:
    """
    Detects unusual demand spikes at zone level using statistical methods.
    Uses z-score and IQR fencing on rolling historical baselines.
    """

    def __init__(self, window: int = 7, z_threshold: float = 3.0):
        self.window = window
        self.z_threshold = z_threshold
        self.baselines = {}

    def build_baselines(self, zone_hourly: pd.DataFrame):
        """Compute mean + std for each (zone, hour, day_of_week) combination"""
        for (zone, hour, dow), group in zone_hourly.groupby(["pickup_zone", "event_hour", "event_day_of_week"]):
            demand = group["total_rides"]
            self.baselines[(zone, hour, dow)] = {
                "mean": demand.mean(),
                "std": max(demand.std(), 1),
                "q1": demand.quantile(0.25),
                "q3": demand.quantile(0.75)
            }
        logger.info(f"Built baselines for {len(self.baselines)} zone-hour-dow combinations")

    def detect_spikes(self, current_demand: pd.DataFrame) -> pd.DataFrame:
        """Flag rows where demand deviates > z_threshold std from baseline"""
        results = []
        for _, row in current_demand.iterrows():
            key = (row.get("pickup_zone"), row.get("event_hour"), row.get("event_day_of_week"))
            baseline = self.baselines.get(key)
            if baseline:
                z_score = abs(row["total_rides"] - baseline["mean"]) / baseline["std"]
                iqr = baseline["q3"] - baseline["q1"]
                is_spike = (
                    z_score > self.z_threshold or
                    row["total_rides"] > baseline["q3"] + 1.5 * iqr
                )
            else:
                z_score = 0
                is_spike = False

            results.append({
                **row.to_dict(),
                "z_score": round(z_score, 2),
                "is_demand_spike": int(is_spike),
                "spike_severity": "high" if z_score > 4 else "medium" if z_score > 3 else "normal"
            })

        return pd.DataFrame(results)


if __name__ == "__main__":
    import sys
    sys.path.append("../data_generators")
    from uber_generator import UberRideGenerator

    gen = UberRideGenerator()
    df = pd.DataFrame(gen.generate_batch(n=20_000))

    # Inject synthetic anomalies for testing
    anomaly_indices = df.sample(n=500).index
    df.loc[anomaly_indices[:100], "speed_kmh"] = np.random.uniform(130, 200, 100)
    df.loc[anomaly_indices[100:200], "final_fare"] = np.random.uniform(5000, 15000, 100)
    df.loc[anomaly_indices[200:300], "distance_km"] = 0.01

    detector = RideAnomalyDetector(contamination=0.05)
    detector.train(df)
    result = detector.predict(df)

    summary = detector.get_anomaly_summary(result)
    print(f"\n{'='*50}")
    print("ANOMALY DETECTION SUMMARY")
    print(json.dumps(summary, indent=2))

    detector.save()
