-- models/staging/dim_zone.sql
{{ config(materialized='table', tags=['dimension']) }}
select * from {{ ref('dim_zone_seed') }}
