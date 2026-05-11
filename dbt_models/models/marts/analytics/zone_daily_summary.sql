-- models/marts/analytics/zone_daily_summary.sql
-- Business-ready zone-level daily KPIs (rides + orders combined)
-- This is the primary model for Power BI dashboards

{{
  config(
    materialized='table',
    tags=['mart', 'analytics', 'dashboard'],
    post_hook="alter table {{ this }} cluster by (event_date, zone_id)"
  )
}}

with daily_rides as (
    select
        event_date,
        pickup_zone_id                              as zone_id,
        count(ride_id)                              as total_ride_requests,
        sum(case when not is_cancelled then 1 end)  as completed_rides,
        sum(case when is_cancelled then 1 end)      as cancelled_rides,
        round(avg(final_fare), 2)                   as avg_ride_fare,
        round(sum(final_fare), 2)                   as total_ride_revenue,
        round(avg(surge_multiplier), 3)             as avg_surge_multiplier,
        round(avg(distance_km), 2)                  as avg_ride_distance,
        round(avg(duration_minutes), 1)             as avg_ride_duration,
        count_if(is_surge_ride)                     as surge_ride_count,
        count_if(is_peak_hour)                      as peak_hour_rides,
        count_if(weather_condition = 'Rain')        as rain_rides,
        count_if(payment_method = 'UPI')            as upi_rides,
        count_if(payment_method = 'Cash')           as cash_rides,
        count(distinct user_id)                     as unique_ride_users

    from {{ ref('stg_rides') }}
    group by 1, 2
),

daily_orders as (
    select
        event_date,
        delivery_zone_id                            as zone_id,
        count(order_id)                             as total_orders,
        round(sum(total_amount), 2)                 as total_gmv,
        round(avg(total_amount), 2)                 as avg_order_value,
        round(avg(delivery_time_minutes), 1)        as avg_delivery_time,
        round(avg(total_time_minutes), 1)           as avg_total_time,
        count_if(is_rain_order)                     as rain_orders,
        count_if(is_discounted)                     as discounted_orders,
        count_if(is_peak_hour)                      as peak_hour_orders,
        count(distinct user_id)                     as unique_order_users,
        count(distinct restaurant_id)               as active_restaurants,
        round(avg(food_rating), 2)                  as avg_food_rating,
        round(avg(delivery_rating), 2)              as avg_delivery_rating

    from {{ ref('stg_orders') }}
    group by 1, 2
),

zone_info as (
    select * from {{ ref('dim_zone') }}
)

select
    -- Dimensions
    coalesce(r.event_date, o.event_date)            as event_date,
    coalesce(r.zone_id, o.zone_id)                  as zone_id,
    z.zone_name,
    z.zone_type,
    z.density,
    z.latitude,
    z.longitude,

    -- Ride KPIs
    coalesce(r.total_ride_requests, 0)              as total_ride_requests,
    coalesce(r.completed_rides, 0)                  as completed_rides,
    coalesce(r.cancelled_rides, 0)                  as cancelled_rides,
    coalesce(r.total_ride_revenue, 0)               as ride_revenue,
    coalesce(r.avg_ride_fare, 0)                    as avg_ride_fare,
    coalesce(r.avg_surge_multiplier, 1.0)           as avg_surge_multiplier,
    coalesce(r.surge_ride_count, 0)                 as surge_rides,
    coalesce(r.unique_ride_users, 0)                as unique_ride_users,
    case
        when coalesce(r.total_ride_requests, 0) > 0
        then round(r.completed_rides / r.total_ride_requests * 100, 1)
        else 0
    end                                             as ride_completion_rate_pct,

    -- Order KPIs
    coalesce(o.total_orders, 0)                     as total_food_orders,
    coalesce(o.total_gmv, 0)                        as food_gmv,
    coalesce(o.avg_order_value, 0)                  as avg_order_value,
    coalesce(o.avg_delivery_time, 0)                as avg_delivery_time_min,
    coalesce(o.avg_total_time, 0)                   as avg_total_time_min,
    coalesce(o.active_restaurants, 0)               as active_restaurants,
    coalesce(o.unique_order_users, 0)               as unique_order_users,
    coalesce(o.avg_food_rating, 0)                  as avg_food_rating,
    coalesce(o.avg_delivery_rating, 0)              as avg_delivery_rating,

    -- Combined KPIs
    coalesce(r.total_ride_revenue, 0)
        + coalesce(o.total_gmv, 0)                  as total_platform_revenue,
    coalesce(r.unique_ride_users, 0)
        + coalesce(o.unique_order_users, 0)         as total_unique_users,
    coalesce(r.rain_rides, 0)
        + coalesce(o.rain_orders, 0)                as rain_events,

    -- Metadata
    current_timestamp()                             as dbt_updated_at

from daily_rides r
full outer join daily_orders o
    on r.event_date = o.event_date
    and r.zone_id = o.zone_id
left join zone_info z
    on coalesce(r.zone_id, o.zone_id) = z.zone_id

order by event_date desc, total_platform_revenue desc
