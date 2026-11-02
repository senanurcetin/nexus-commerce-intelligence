-- Ordered, closed, same-session funnel. Grain: (session_id, user_id).
-- A cart must follow a page view; a purchase must follow that cart.
-- Channel attribution comes from the session mart, never an event-level join.
with event_positions as (
    select session_id, user_id, event_type,
        row_number() over (
            partition by session_id, user_id
            order by event_created_at, sequence_number, event_id
        ) as event_position
    from {{ ref('int_events_enriched') }}
    where session_id is not null
),
views as (
    select session_id, user_id,
           min(case when event_type = 'page_view' then event_position end) as view_position
    from event_positions
    group by session_id, user_id
),
carts as (
    select v.session_id, v.user_id, v.view_position,
           min(e.event_position) as cart_position
    from views v
    left join event_positions e
      on e.session_id = v.session_id
     and (e.user_id = v.user_id or (e.user_id is null and v.user_id is null))
     and e.event_type = 'cart' and e.event_position > v.view_position
    group by v.session_id, v.user_id, v.view_position
),
purchases as (
    select c.session_id, c.user_id, c.view_position, c.cart_position,
           min(e.event_position) as purchase_position
    from carts c
    left join event_positions e
      on e.session_id = c.session_id
     and (e.user_id = c.user_id or (e.user_id is null and c.user_id is null))
     and e.event_type = 'purchase' and e.event_position > c.cart_position
    group by c.session_id, c.user_id, c.view_position, c.cart_position
),
attributed as (
    select s.channel_group, p.view_position, p.cart_position, p.purchase_position
    from purchases p
    join {{ ref('fct_marketing_web_performance') }} s
      on s.session_id = p.session_id
     and (s.user_id = p.user_id or (s.user_id is null and p.user_id is null))
),
summary as (
    select channel_group, count(*) as total_sessions,
           sum(case when view_position is not null then 1 else 0 end) as page_view_sessions,
           sum(case when cart_position is not null then 1 else 0 end) as cart_sessions,
           sum(case when purchase_position is not null then 1 else 0 end) as purchase_sessions
    from attributed
    group by channel_group
)
select *,
       round(cart_sessions * 100.0 / nullif(page_view_sessions, 0), 1) as view_to_cart_pct,
       round(purchase_sessions * 100.0 / nullif(cart_sessions, 0), 1) as cart_to_purchase_pct,
       round(purchase_sessions * 100.0 / nullif(page_view_sessions, 0), 1) as overall_cvr_pct
from summary
order by overall_cvr_pct desc nulls last, channel_group
