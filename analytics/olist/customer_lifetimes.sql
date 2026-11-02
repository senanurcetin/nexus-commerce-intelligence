-- First and second DISTINCT purchase days, not split same-day orders.
-- First observed purchase uses all prior extract history before filtering origins.
-- Administrative follow-up ends on cutoff - 1 day, the last observed calendar day.
with days as (
    select distinct customer_unique_id, purchased_at::date as day
    from order_fact
    where order_status='delivered' and purchased_at < $cutoff and gmv>0
      and customer_unique_id is not null
), ranked as (
    select *, row_number() over(partition by customer_unique_id order by day) as n
    from days
), histories as (
    select customer_unique_id, min(day) as first_day,
           min(day) filter(where n=2) as second_day
    from ranked group by 1
)
select date_diff('day',first_day,coalesce(second_day, $cutoff::date - 1))::integer as duration,
       second_day is not null as event,
       date_diff('day',first_day,$cutoff::date - 1)::integer as available_days,
       count(*) as customers
from histories where first_day >= '2017-01-01'
group by 1,2,3 order by 1,2,3;
