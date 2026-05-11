-- models/staging/stg_rides.sql
-- Cleans and standardizes raw ride data from Snowflake raw layer

{{
  config(
    materialized='view',
    tags=['staging', 'rides']
  )
}}

with source as (
    select * from {{ source('raw', 'FACT_RIDES') }}
),

cleaned as (
    select
        ride_id,
        event_id,
        event_type,
        event_date,
        event_ts::timestamp                         as event_timestamp,
        event_hour,
        event_day_of_week,
        is_weekend::boolean                         as is_weekend,

        -- Parties
        user_id,
        coalesce(driver_id, 'UNASSIGNED')           as driver_id,

        -- Location
        pickup_zone::int                            as pickup_zone_id,
        dropoff_zone::int                           as dropoff_zone_id,

        -- Trip details
        upper(trim(vehicle_type))                   as vehicle_type,
        round(distance_km::float, 2)                as distance_km,
        round(duration_minutes::float, 1)           as duration_minutes,

        -- Financials
        round(base_fare::float, 2)                  as base_fare,
        round(surge_multiplier::float, 2)           as surge_multiplier,
        round(final_fare::float, 2)                 as final_fare,
        round(fare_per_km::float, 2)                as fare_per_km,

        -- Payment
        upper(trim(payment_method))                 as payment_method,

        -- Ratings (validated)
        case
            when user_rating::float between 1 and 5 then round(user_rating::float, 1)
            else null
        end                                         as user_rating,
        case
            when driver_rating::float between 1 and 5 then round(driver_rating::float, 1)
            else null
        end                                         as driver_rating,

        -- Status
        event_type = 'cancelled'                    as is_cancelled,
        surge_multiplier::float > 1.0               as is_surge_ride,
        cancellation_reason,

        -- Context
        weather_condition,
        is_peak_hour::boolean                       as is_peak_hour,
        speed_kmh

    from source
    where
        ride_id is not null
        and event_date >= '{{ var("start_date") }}'
        and distance_km::float > 0
        and final_fare::float >= 0
)

select * from cleaned
