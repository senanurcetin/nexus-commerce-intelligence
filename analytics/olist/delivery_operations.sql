-- Retrospective delivered-order experience, independent of review response.
-- Compare January-July in BOTH years; never compare 12 months with seven.
create or replace table operations_orders as
select order_id, customer_unique_id, coalesce(customer_state,'Unknown state') as state,
       year(purchased_at)::integer as year, month(purchased_at)::integer as month,
       delivered_at::date > estimated_at::date as late, gmv,
       date_diff('second',purchased_at,delivered_at)/86400.0 as transit_days
from order_fact
where order_status='delivered' and gmv>0 and customer_unique_id is not null
  and year(purchased_at) in (2017,2018) and month(purchased_at) between 1 and 7
  and delivered_at >= purchased_at and estimated_at >= purchased_at::date;
