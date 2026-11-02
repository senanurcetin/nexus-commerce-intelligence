-- Placed-order count, not final delivered volume. Never select on future status.
with calendar as (
    select day::date as day from generate_series(
        $start::date, $end::date - interval '1 day', interval '1 day') t(day)
), observed as (
    select order_purchase_timestamp::date as day,count(*) as placed_orders
    from raw_orders where order_purchase_timestamp >= $start
      and order_purchase_timestamp < $end group by 1
)
select c.day,coalesce(o.placed_orders,0)::bigint as placed_orders
from calendar c left join observed o using(day) order by c.day;
