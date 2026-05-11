-- Urban Pulse — PostgreSQL Operational Database Schema
-- Used for: live streaming aggregations, API caching, Airflow

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- ── Live Zone Aggregations (from Spark Streaming) ────────────────────────────
CREATE TABLE IF NOT EXISTS live_zone_rides (
    id              SERIAL PRIMARY KEY,
    window_start    TIMESTAMPTZ NOT NULL,
    window_end      TIMESTAMPTZ NOT NULL,
    pickup_zone     INT NOT NULL,
    ride_count      INT DEFAULT 0,
    avg_fare        DECIMAL(10,2),
    avg_surge       DECIMAL(5,3),
    max_surge       DECIMAL(5,3),
    revenue         DECIMAL(15,2),
    batch_id        BIGINT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_live_rides_zone_window ON live_zone_rides(pickup_zone, window_start DESC);

-- ── Live Zone Orders (from Spark Streaming) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS live_zone_orders (
    id                  SERIAL PRIMARY KEY,
    window_start        TIMESTAMPTZ NOT NULL,
    window_end          TIMESTAMPTZ NOT NULL,
    delivery_zone       INT NOT NULL,
    order_count         INT DEFAULT 0,
    gmv                 DECIMAL(15,2),
    avg_order_value     DECIMAL(10,2),
    avg_delivery_min    DECIMAL(6,2),
    active_restaurants  INT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_live_orders_zone_window ON live_zone_orders(delivery_zone, window_start DESC);

-- ── Anomaly Log ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS anomaly_log (
    id              SERIAL PRIMARY KEY,
    detected_at     TIMESTAMPTZ DEFAULT NOW(),
    entity_type     VARCHAR(20),   -- ride, order, driver
    entity_id       VARCHAR(50),
    anomaly_type    VARCHAR(50),
    severity        VARCHAR(10),   -- low, medium, high
    anomaly_score   DECIMAL(8,4),
    details         JSONB,
    is_resolved     BOOLEAN DEFAULT FALSE,
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX idx_anomaly_detected ON anomaly_log(detected_at DESC);
CREATE INDEX idx_anomaly_type ON anomaly_log(anomaly_type, is_resolved);

-- ── ML Predictions Cache ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ml_predictions_cache (
    id              SERIAL PRIMARY KEY,
    prediction_type VARCHAR(30),   -- surge, eta, demand
    input_hash      VARCHAR(64),   -- MD5 of input features
    input_data      JSONB,
    prediction      JSONB,
    model_version   VARCHAR(20),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ DEFAULT NOW() + INTERVAL '5 minutes'
);

CREATE INDEX idx_cache_lookup ON ml_predictions_cache(prediction_type, input_hash, expires_at);

-- ── Pipeline Run Log ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              SERIAL PRIMARY KEY,
    run_date        DATE NOT NULL,
    dag_id          VARCHAR(100),
    status          VARCHAR(20),   -- running, success, failed
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    records_processed BIGINT,
    error_message   TEXT,
    metadata        JSONB
);

-- ── Airflow DB (separate) ────────────────────────────────────────────────────
CREATE DATABASE airflow;
GRANT ALL PRIVILEGES ON DATABASE airflow TO postgres;

-- ── Sample Data for Testing ──────────────────────────────────────────────────
INSERT INTO live_zone_rides (window_start, window_end, pickup_zone, ride_count, avg_fare, avg_surge, max_surge, revenue)
SELECT
    NOW() - INTERVAL '1 hour' * s,
    NOW() - INTERVAL '1 hour' * s + INTERVAL '5 minutes',
    (RANDOM() * 11 + 1)::INT,
    (RANDOM() * 80 + 10)::INT,
    ROUND((RANDOM() * 200 + 80)::NUMERIC, 2),
    ROUND((RANDOM() * 1.5 + 1.0)::NUMERIC, 3),
    ROUND((RANDOM() * 2.0 + 1.0)::NUMERIC, 3),
    ROUND((RANDOM() * 15000 + 3000)::NUMERIC, 2)
FROM generate_series(0, 47) AS s;

COMMENT ON TABLE live_zone_rides IS 'Real-time zone ride aggregations from Spark Streaming (5-min windows)';
COMMENT ON TABLE anomaly_log IS 'ML-detected anomalies: fraud, GPS spoofing, unusual patterns';
COMMENT ON TABLE ml_predictions_cache IS 'Cached ML predictions to reduce model inference latency';
