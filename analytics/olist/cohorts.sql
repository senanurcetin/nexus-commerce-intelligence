-- Retrospective delivered-purchase cohorts, first OBSERVED purchase in the extract.
-- Include pre-2017 history when assigning cohorts. No inferred lifetime acquisition.
-- Parameters are the first EXCLUDED purchase timestamp and first displayed cohort.
with eligible as (
    select customer_unique_id, date_trunc('month', purchased_at)::date as month
    from order_fact
    where order_status = 'delivered' and purchased_at < $cutoff
      and customer_unique_id is not null and gmv > 0
), firsts as (
    select customer_unique_id, min(month) as cohort from eligible group by 1
), sizes as (
    select cohort, count(*) as customers from firsts
    where cohort >= $cohort_start group by 1
), activity as (
    select f.cohort, date_diff('month', f.cohort, e.month) as period,
           count(distinct e.customer_unique_id) as active
    from eligible e join firsts f using (customer_unique_id) group by 1,2
), grid as (
    select s.*, p.period,
           s.cohort + p.period * interval '1 month' < $cutoff as observable
    from sizes s cross join range(0, $periods) p(period)
)
select g.cohort, g.period, g.customers, g.observable,
       case when observable then coalesce(a.active,0) end as active,
       case when observable then coalesce(a.active,0)::double / customers end as retention
from grid g left join activity a using (cohort,period)
order by cohort,period;
