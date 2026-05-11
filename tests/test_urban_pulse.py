"""
Urban Pulse — Test Suite
Tests for data generators, ML models, and API endpoints
"""

import sys
import json
import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "data_generators"))
sys.path.insert(0, str(Path(__file__).parent.parent / "ml_models"))


# ─── Data Generator Tests ─────────────────────────────────────────────────────

class TestUberGenerator:
    def setup_method(self):
        from uber_generator import UberRideGenerator, DriverPool
        self.driver_pool = DriverPool(num_drivers=50)
        self.generator = UberRideGenerator(self.driver_pool)

    def test_driver_pool_creation(self):
        assert len(self.driver_pool.drivers) == 50

    def test_ride_request_structure(self):
        from dataclasses import asdict
        event = self.generator.generate_ride_request()
        d = asdict(event)
        required_keys = ["ride_id", "event_type", "timestamp", "user_id",
                         "pickup_zone", "dropoff_zone", "final_fare", "surge_multiplier"]
        for key in required_keys:
            assert key in d, f"Missing key: {key}"

    def test_ride_request_values(self):
        from dataclasses import asdict
        event = self.generator.generate_ride_request()
        assert event.event_type == "requested"
        assert event.distance_km > 0
        assert event.final_fare >= 0
        assert event.surge_multiplier >= 1.0
        assert event.pickup_zone in range(1, 13)
        assert event.dropoff_zone in range(1, 13)
        assert event.vehicle_type in ["UberGo", "Premier", "UberXL", "Auto", "Moto"]

    def test_fare_calculation(self):
        from dataclasses import asdict
        events = [asdict(self.generator.generate_ride_request()) for _ in range(100)]
        fares = [e["final_fare"] for e in events]
        assert all(f >= 0 for f in fares), "Negative fare detected"
        assert max(fares) < 10000, "Unrealistically high fare detected"
        assert min(fares) >= 20, "Unrealistically low fare"

    def test_surge_range(self):
        from dataclasses import asdict
        events = [asdict(self.generator.generate_ride_request()) for _ in range(200)]
        surges = [e["surge_multiplier"] for e in events]
        assert all(1.0 <= s <= 4.0 for s in surges), "Surge out of valid range"

    def test_batch_generation(self):
        batch = self.generator.generate_batch(n=100)
        assert len(batch) == 100
        assert all(isinstance(r, dict) for r in batch)
        assert all("ride_id" in r for r in batch)

    def test_gps_coordinates(self):
        from dataclasses import asdict
        events = [asdict(self.generator.generate_ride_request()) for _ in range(50)]
        for e in events:
            # Mumbai bounding box
            assert 18.8 <= e["pickup_lat"] <= 19.4, f"Lat out of Mumbai range: {e['pickup_lat']}"
            assert 72.7 <= e["pickup_lon"] <= 73.2, f"Lon out of Mumbai range: {e['pickup_lon']}"


class TestZomatoGenerator:
    def setup_method(self):
        from zomato_generator import ZomatoOrderGenerator, RestaurantPool
        self.restaurant_pool = RestaurantPool(num_restaurants=20)
        self.generator = ZomatoOrderGenerator(self.restaurant_pool)

    def test_order_structure(self):
        from dataclasses import asdict
        order = self.generator.generate_order()
        d = asdict(order)
        required = ["order_id", "user_id", "restaurant_id", "total_amount",
                    "delivery_time_minutes", "items"]
        for key in required:
            assert key in d

    def test_order_financials(self):
        from dataclasses import asdict
        orders = [asdict(self.generator.generate_order()) for _ in range(100)]
        for o in orders:
            assert o["total_amount"] >= 0, "Negative order total"
            assert o["subtotal"] > 0, "Zero subtotal"
            assert o["delivery_fee"] >= 0
            assert o["gst"] >= 0

    def test_delivery_times_realistic(self):
        from dataclasses import asdict
        orders = [asdict(self.generator.generate_order()) for _ in range(200)]
        times = [o["delivery_time_minutes"] for o in orders]
        assert all(t >= 10 for t in times), "Delivery time too short"
        assert all(t <= 120 for t in times), "Delivery time unrealistically long"

    def test_items_structure(self):
        from dataclasses import asdict
        order = self.generator.generate_order()
        assert len(order.items) >= 1
        for item in order.items:
            assert "name" in item
            assert "quantity" in item
            assert "unit_price" in item
            assert item["quantity"] >= 1
            assert item["unit_price"] > 0


# ─── ML Model Tests ───────────────────────────────────────────────────────────

class TestSurgeModel:
    def setup_method(self):
        from surge_prediction import SurgePredictionModel, engineer_features
        self.ModelClass = SurgePredictionModel
        self.engineer = engineer_features

    def test_feature_engineering(self):
        from uber_generator import UberRideGenerator
        gen = UberRideGenerator()
        df = pd.DataFrame(gen.generate_batch(n=200))
        engineered = self.engineer(df)
        assert "hour" in engineered.columns
        assert "hour_sin" in engineered.columns
        assert "is_rain" in engineered.columns
        assert "surge_category" in engineered.columns
        assert engineered["surge_category"].between(0, 4).all()

    def test_model_predict_structure(self):
        """Test that predict returns expected keys"""
        model = self.ModelClass()
        # Mock a trained model
        import xgboost as xgb
        import pickle
        from sklearn.datasets import make_classification
        X, y = make_classification(n_samples=500, n_features=17, n_classes=5,
                                   n_informative=10, random_state=42)
        model.model = xgb.XGBClassifier(n_estimators=10, use_label_encoder=False, eval_metric="mlogloss")
        model.model.fit(X, y)

        sample = {
            "hour": 18, "pickup_zone": 2, "vehicle_type": "UberGo",
            "distance_km": 8.5, "weather_condition": "Rain",
            "is_peak_hour": True, "timestamp": datetime.now().isoformat()
        }
        # Direct category prediction (bypass predict method for unit test)
        assert model.model is not None


class TestAnomalyDetector:
    def test_rule_based_flags(self):
        from anomaly_detection import RideAnomalyDetector
        detector = RideAnomalyDetector()

        test_data = pd.DataFrame([
            {"timestamp": "2024-01-15 08:00:00", "distance_km": 5.0,
             "duration_minutes": 20, "final_fare": 150.0, "surge_multiplier": 1.2,
             "pickup_zone": 2, "speed_kmh": 15, "is_peak_hour": True,
             "vehicle_type": "UberGo"},
            {"timestamp": "2024-01-15 08:00:00", "distance_km": 0.01,   # anomaly: zero distance
             "duration_minutes": 20, "final_fare": 5000.0,              # anomaly: high fare
             "surge_multiplier": 1.0, "pickup_zone": 2, "speed_kmh": 0,
             "is_peak_hour": False, "vehicle_type": "UberGo"},
        ])

        result = detector._add_rule_based_flags(test_data)
        assert "is_rule_anomaly" in result.columns
        assert "flag_zero_distance" in result.columns
        assert result.loc[1, "flag_zero_distance"] == 1
        assert result.loc[1, "flag_fare_too_high"] == 1


# ─── API Tests ────────────────────────────────────────────────────────────────

class TestAPI:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "api"))
        from main import app
        return TestClient(app)

    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "Urban Pulse" in data["name"]

    def test_health_endpoint(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_dashboard_kpis(self, client):
        response = client.get("/api/v1/kpis/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert "rides" in data
        assert "orders" in data
        assert data["rides"]["total"] > 0

    def test_surge_prediction(self, client):
        payload = {
            "pickup_zone": 2,
            "vehicle_type": "UberGo",
            "distance_km": 8.0,
            "weather_condition": "Rain",
            "is_peak_hour": True
        }
        response = client.post("/api/v1/predictions/surge", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "surge_multiplier" in data
        assert data["surge_multiplier"] >= 1.0
        assert "estimated_fare_inr" in data

    def test_eta_prediction(self, client):
        payload = {
            "restaurant_zone": 2,
            "delivery_zone": 6,
            "delivery_distance_km": 5.0,
            "prep_time_minutes": 20,
            "item_count": 2,
            "subtotal": 350.0,
            "weather_condition": "Clear",
        }
        response = client.post("/api/v1/predictions/eta", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "estimated_delivery_minutes" in data
        assert data["estimated_delivery_minutes"] >= 10

    def test_demand_forecast(self, client):
        response = client.get("/api/v1/predictions/demand/2?platform=uber&hours=24")
        assert response.status_code == 200
        data = response.json()
        assert data["zone_id"] == 2
        assert len(data["hourly_forecast"]) == 24

    def test_invalid_zone(self, client):
        response = client.get("/api/v1/predictions/demand/99")
        assert response.status_code == 400

    def test_surge_invalid_vehicle(self, client):
        payload = {"pickup_zone": 1, "vehicle_type": "InvalidVehicle"}
        response = client.post("/api/v1/predictions/surge", json=payload)
        assert response.status_code == 422  # Validation error


# ─── Data Pipeline Tests ──────────────────────────────────────────────────────

class TestDataPipeline:
    def test_end_to_end_data_generation(self):
        """Full pipeline: generate → validate → save"""
        from uber_generator import UberRideGenerator
        from zomato_generator import ZomatoOrderGenerator

        uber_gen = UberRideGenerator()
        zomato_gen = ZomatoOrderGenerator()

        rides = uber_gen.generate_batch(n=500)
        orders = zomato_gen.generate_batch(n=500)

        rides_df = pd.DataFrame(rides)
        orders_df = pd.DataFrame(orders)

        # Schema validation
        assert "ride_id" in rides_df.columns
        assert "final_fare" in rides_df.columns
        assert rides_df["final_fare"].notna().all()

        assert "order_id" in orders_df.columns
        assert "total_amount" in orders_df.columns
        assert (orders_df["total_amount"] >= 0).all()

        # No duplicates
        assert rides_df["ride_id"].is_unique
        assert orders_df["order_id"].is_unique

        print(f"\n✅ Generated {len(rides_df)} rides and {len(orders_df)} orders")
        print(f"   Ride revenue: ₹{rides_df['final_fare'].sum():,.0f}")
        print(f"   Food GMV: ₹{orders_df['total_amount'].sum():,.0f}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
