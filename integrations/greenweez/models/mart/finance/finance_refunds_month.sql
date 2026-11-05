{{ config(enabled=var('source_system', 'gwz_raw') == 'fvt_gsheet', tags=['fvt_gsheet']) }}

{% if var('refund_unit_verified', false) is not sameas false or var('refund_amount_scale', 1.0) != 1.0 %}
    {{ exceptions.raise_compiler_error('Greenweez refund meaning and unit require source evidence before verification or scaling.') }}
{% endif %}

-- Keep the observed value separate from revenue while its meaning and unit are unknown.
with orders as (
    select
        o.date_date,
        o.revenue,
        r.refund_amount as refund_raw
    from {{ ref('stg_gsheet__orders') }} as o
    left join {{ ref('stg_gsheet__refund') }} as r
        on o.orders_id = r.orders_id
)

select
    {{ month_start('date_date') }} as datemonth,
    count(*) as orders,
    round(sum(revenue), 2) as revenue,
    round(sum(coalesce(refund_raw, 0)), 2) as refund_amount_raw,
    round(sum(coalesce(refund_raw, 0)), 2) as refund_amount,
    sum(case when refund_raw > 0 then 1 else 0 end) as orders_with_refund,
    sum(case when refund_raw > revenue then 1 else 0 end) as orders_refund_above_revenue,
    round({{ dbt_utils.safe_divide('sum(coalesce(refund_raw, 0))', 'sum(revenue)') }}, 4) as refund_to_revenue,
    false as refund_unit_verified,
    cast(null as {{ dbt.type_numeric() }}) as net_revenue_after_refunds
from orders
group by datemonth
