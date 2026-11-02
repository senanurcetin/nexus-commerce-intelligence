-- As-of delivered purchases only: no future delivery status used for eligibility.
-- Exact frequency and fixed recency policy keep tied customers together.
with customers as (
    select customer_unique_id,
           date_diff('day', max(purchased_at)::date, $cutoff::date) as recency_days,
           count(*) as frequency, sum(gmv) as monetary
    from order_fact where order_status = 'delivered' and purchased_at < $cutoff
      and delivered_at < $cutoff and delivered_at >= purchased_at
      and customer_unique_id is not null and gmv > 0
    group by customer_unique_id
), tagged as (
    select *, case
      when frequency >= 2 and recency_days <= 90 then 'Repeat / recent'
      when frequency >= 2 then 'Repeat / lapsed'
      when recency_days <= 90 then 'Single / recent'
      else 'Single / lapsed' end as segment
    from customers
)
select segment, count(*) as customers, sum(frequency) as orders,
       sum(monetary) as gmv, avg(recency_days) as mean_recency_days,
       avg(frequency) as mean_frequency, avg(monetary) as mean_monetary
from tagged group by segment order by segment;
