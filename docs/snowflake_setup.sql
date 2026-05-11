-- ============================================================
-- Urban Pulse — Snowflake Setup Script
-- Run this ONCE to set up your Snowflake environment
-- ============================================================

-- 1. Create Database & Schemas
CREATE DATABASE IF NOT EXISTS URBAN_PULSE;
USE DATABASE URBAN_PULSE;

CREATE SCHEMA IF NOT EXISTS RAW;        -- Raw ingested data
CREATE SCHEMA IF NOT EXISTS STAGING;    -- dbt staging views
CREATE SCHEMA IF NOT EXISTS MARTS;      -- Business-ready tables
CREATE SCHEMA IF NOT EXISTS ML;         -- ML feature tables

-- 2. Warehouse
CREATE WAREHOUSE IF NOT EXISTS COMPUTE_WH
    WAREHOUSE_SIZE = 'X-SMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    COMMENT = 'Urban Pulse main compute warehouse';

-- 3. Role
CREATE ROLE IF NOT EXISTS URBAN_PULSE_ROLE;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE URBAN_PULSE_ROLE;
GRANT ALL ON DATABASE URBAN_PULSE TO ROLE URBAN_PULSE_ROLE;

-- 4. Raw Tables (Spark writes here)
CREATE OR REPLACE TABLE RAW.FACT_RIDES (
    RIDE_ID             VARCHAR(50)     NOT NULL,
    EVENT_ID            VARCHAR(50),
    EVENT_TYPE          VARCHAR(20),
    EVENT_DATE          DATE,
    EVENT_TS            TIMESTAMP_NTZ,
    EVENT_HOUR          INT,
    EVENT_DAY_OF_WEEK   INT,
    IS_WEEKEND          BOOLEAN,
    USER_ID             VARCHAR(50),
    DRIVER_ID           VARCHAR(50),
    PICKUP_ZONE         INT,
    DROPOFF_ZONE        INT,
    VEHICLE_TYPE        VARCHAR(20),
    DISTANCE_KM         FLOAT,
    DURATION_MINUTES    FLOAT,
    BASE_FARE           FLOAT,
    SURGE_MULTIPLIER    FLOAT,
    FINAL_FARE          FLOAT,
    FARE_PER_KM         FLOAT,
    PAYMENT_METHOD      VARCHAR(20),
    USER_RATING         FLOAT,
    DRIVER_RATING       FLOAT,
    IS_CANCELLED        BOOLEAN,
    IS_SURGE            BOOLEAN,
    CANCELLATION_REASON VARCHAR(50),
    WEATHER_CONDITION   VARCHAR(20),
    IS_PEAK_HOUR        BOOLEAN,
    SPEED_KMH           FLOAT,
    LOADED_AT           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
CLUSTER BY (EVENT_DATE, PICKUP_ZONE);

CREATE OR REPLACE TABLE RAW.FACT_ORDERS (
    ORDER_ID                VARCHAR(50)     NOT NULL,
    EVENT_DATE              DATE,
    EVENT_TS                TIMESTAMP_NTZ,
    EVENT_HOUR              INT,
    IS_WEEKEND              BOOLEAN,
    USER_ID                 VARCHAR(50),
    RESTAURANT_ID           VARCHAR(50),
    RESTAURANT_ZONE         INT,
    DELIVERY_ZONE           INT,
    DELIVERY_LAT            FLOAT,
    DELIVERY_LON            FLOAT,
    ITEM_COUNT              INT,
    SUBTOTAL                FLOAT,
    DELIVERY_FEE            FLOAT,
    PLATFORM_FEE            FLOAT,
    GST                     FLOAT,
    DISCOUNT                FLOAT,
    TOTAL_AMOUNT            FLOAT,
    AVG_ITEM_VALUE          FLOAT,
    PAYMENT_METHOD          VARCHAR(20),
    DELIVERY_DISTANCE_KM    FLOAT,
    PREP_TIME_MINUTES       INT,
    DELIVERY_TIME_MINUTES   INT,
    TOTAL_TIME_MINUTES      INT,
    DELIVERY_AGENT_ID       VARCHAR(50),
    FOOD_RATING             FLOAT,
    DELIVERY_RATING         FLOAT,
    WEATHER_CONDITION       VARCHAR(20),
    IS_PEAK_HOUR            BOOLEAN,
    PROMO_CODE              VARCHAR(20),
    IS_DISCOUNTED           BOOLEAN,
    IS_RAIN_ORDER           BOOLEAN,
    DELIVERY_SPEED_TIER     VARCHAR(10),
    LOADED_AT               TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
CLUSTER BY (EVENT_DATE, DELIVERY_ZONE);

-- 5. Dimension Tables
CREATE OR REPLACE TABLE MARTS.DIM_ZONE (
    ZONE_ID     INT PRIMARY KEY,
    ZONE_NAME   VARCHAR(50),
    LATITUDE    FLOAT,
    LONGITUDE   FLOAT,
    ZONE_TYPE   VARCHAR(20),
    DENSITY     VARCHAR(20)
);

INSERT INTO MARTS.DIM_ZONE VALUES
(1,  'Andheri West',  19.1197, 72.8466, 'residential', 'high'),
(2,  'Bandra Kurla',  19.0596, 72.8650, 'business',    'very_high'),
(3,  'Colaba',        18.9067, 72.8147, 'tourist',     'medium'),
(4,  'Dadar',         19.0178, 72.8478, 'mixed',       'high'),
(5,  'Juhu',          19.1075, 72.8263, 'premium',     'medium'),
(6,  'Lower Parel',   18.9956, 72.8258, 'business',    'high'),
(7,  'Malad East',    19.1871, 72.8485, 'residential', 'very_high'),
(8,  'Powai',         19.1176, 72.9060, 'tech_hub',    'high'),
(9,  'Thane',         19.2183, 72.9781, 'suburban',    'high'),
(10, 'Borivali',      19.2307, 72.8567, 'residential', 'very_high'),
(11, 'Navi Mumbai',   19.0330, 73.0297, 'planned',     'medium'),
(12, 'Airport Zone',  19.0896, 72.8656, 'transit',     'medium');

-- 6. Key Analytics Views
CREATE OR REPLACE VIEW MARTS.VW_DAILY_PLATFORM_SUMMARY AS
SELECT
    r.EVENT_DATE,
    SUM(r.FINAL_FARE)               AS RIDE_REVENUE,
    COUNT(DISTINCT r.RIDE_ID)       AS TOTAL_RIDES,
    AVG(r.SURGE_MULTIPLIER)         AS AVG_SURGE,
    SUM(o.TOTAL_AMOUNT)             AS FOOD_GMV,
    COUNT(DISTINCT o.ORDER_ID)      AS TOTAL_ORDERS,
    SUM(r.FINAL_FARE) + SUM(o.TOTAL_AMOUNT) AS COMBINED_REVENUE
FROM RAW.FACT_RIDES r
LEFT JOIN RAW.FACT_ORDERS o ON r.EVENT_DATE = o.EVENT_DATE
GROUP BY r.EVENT_DATE
ORDER BY r.EVENT_DATE DESC;

-- 7. File Formats for Parquet Loading
CREATE OR REPLACE FILE FORMAT URBAN_PULSE.RAW.PARQUET_FORMAT
    TYPE = 'PARQUET'
    SNAPPY_COMPRESSION = TRUE;

-- Done!
SELECT 'Urban Pulse Snowflake setup complete! 🚀' AS STATUS;
