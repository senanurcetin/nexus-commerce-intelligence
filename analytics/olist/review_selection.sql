-- Fixed mature cohort, no review availability or score enters eligibility.
create or replace temp table review_cohort as
select order_id, customer_unique_id, delivered_at,
       delivered_at::date > estimated_at::date as late
from order_fact
where order_status = 'delivered' and gmv > 0
  and customer_unique_id is not null
  and purchased_at >= $start and purchased_at < $cutoff
  and delivered_at >= purchased_at
  and estimated_at >= purchased_at::date
  and delivered_at + $maximum_window * interval '1 day' < $cutoff;

-- This policy deliberately uses raw review history, not latest-review order_fact.
create or replace temp table review_observations as
with windows as (select unnest($windows) as window_days), candidates as (
    select c.order_id, c.customer_unique_id, c.late, w.window_days,
           r.review_score,
           row_number() over (partition by c.order_id, w.window_days order by
               r.review_answer_timestamp asc nulls last,
               r.review_creation_date asc nulls last,
               r.review_id asc nulls last, r.review_score asc nulls last) as priority
    from review_cohort c cross join windows w
    left join raw_reviews r on r.order_id = c.order_id
      and r.review_answer_timestamp >= c.delivered_at
      and r.review_answer_timestamp <= c.delivered_at + w.window_days * interval '1 day'
      and r.review_answer_timestamp < $cutoff
)
select order_id, customer_unique_id, late, window_days,
       review_score is not null as responded,
       coalesce(review_score <= $poor_max, false) as poor
from candidates where priority = 1;
