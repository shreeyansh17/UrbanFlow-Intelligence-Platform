-- models/staging/stg_orders.sql
{{ config(materialized='view', tags=['staging', 'orders']) }}

with source as (
    select * from {{ source('raw', 'FACT_ORDERS') }}
),
cleaned as (
    select
        order_id,
        event_date,
        event_ts::timestamp             as event_timestamp,
        event_hour,
        is_weekend::boolean             as is_weekend,
        user_id,
        restaurant_id,
        restaurant_zone::int            as restaurant_zone_id,
        delivery_zone::int              as delivery_zone_id,
        delivery_lat::float             as delivery_lat,
        delivery_lon::float             as delivery_lon,
        item_count::int                 as item_count,
        round(subtotal::float, 2)       as subtotal,
        round(delivery_fee::float, 2)   as delivery_fee,
        round(platform_fee::float, 2)   as platform_fee,
        round(gst::float, 2)            as gst,
        round(discount::float, 2)       as discount,
        round(total_amount::float, 2)   as total_amount,
        round(avg_item_value::float, 2) as avg_item_value,
        upper(trim(payment_method))     as payment_method,
        delivery_distance_km::float     as delivery_distance_km,
        prep_time_minutes::int          as prep_time_minutes,
        delivery_time_minutes::int      as delivery_time_minutes,
        total_time_minutes::int         as total_time_minutes,
        delivery_agent_id,
        case when food_rating::float between 1 and 5 then round(food_rating::float, 1) else null end as food_rating,
        case when delivery_rating::float between 1 and 5 then round(delivery_rating::float, 1) else null end as delivery_rating,
        weather_condition,
        is_peak_hour::boolean           as is_peak_hour,
        promo_code,
        is_discounted::boolean          as is_discounted,
        is_rain_order::boolean          as is_rain_order,
        delivery_speed_tier
    from source
    where order_id is not null
      and event_date >= '{{ var("start_date") }}'
      and total_amount >= 0
)
select * from cleaned
