-- Channel performance: revenue, orders, and conversion rate by marketing channel
-- Current-status revenue only; returned_item_value is not verified refund cash.
-- Run against fct_order_marketing + fct_marketing_web_performance

with orders as (
    select
        channel_group,
        traffic_source,
        -- Revenue already includes only current complete rows. Returned rows
        -- do not contribute to revenue; subtracting returned_revenue again
        -- would double-count return losses.
        sum(revenue)                                          as net_revenue,
        sum(returned_revenue)                                 as returned_item_value,
        count(distinct order_id)                              as total_orders,
        count(distinct case when is_completed_order = 1 then order_id end) as completed_orders,
        count(distinct case when is_returned_order  = 1 then order_id end) as returned_orders
    from {{ ref('fct_order_marketing') }}
    group by channel_group, traffic_source
),

sessions as (
    select
        channel_group,
        traffic_source,
        -- The mart grain is session_sk = (session_id, user_id); a session_id
        -- alone may be shared by more than one user.
        count(*)                                              as total_sessions,
        sum(is_converted)                                     as converted_sessions,
        round(avg(session_duration_minutes), 2)               as avg_session_duration_min,
        round(avg(page_view_events), 1)                       as avg_page_views
    from {{ ref('fct_marketing_web_performance') }}
    group by channel_group, traffic_source
),

final as (
    select
        coalesce(o.channel_group, s.channel_group)            as channel_group,
        coalesce(o.traffic_source, s.traffic_source)          as traffic_source,
        coalesce(s.total_sessions, 0)                         as sessions,
        coalesce(o.completed_orders, 0)                       as orders,
        round(coalesce(o.net_revenue, 0), 2)                  as net_revenue,
        case
            when coalesce(s.total_sessions, 0) > 0
            then round(coalesce(s.converted_sessions, 0) * 100.0 / s.total_sessions, 2)
            else null
        end                                                    as conversion_rate_pct,
        round(s.avg_session_duration_min, 2)                 as avg_session_duration_min,
        round(s.avg_page_views, 1)                           as avg_page_views,
        coalesce(o.returned_orders, 0)                        as returned_orders
    from orders o
    full outer join sessions s
        on o.channel_group  = s.channel_group
       and o.traffic_source = s.traffic_source
)

select *
from final
order by net_revenue desc, channel_group, traffic_source
