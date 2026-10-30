-- Known-cost contribution and coverage, not net profit or audited revenue.
-- The item fact deliberately omits cost; join the tested intermediate at its key.
with lines as (
    select f.category, f.revenue, i.cost,
           i.cost is not null and i.cost >= 0 as known_cost
    from {{ ref('fct_order_marketing') }} f
    left join {{ ref('int_orders_enriched') }} i
      on f.order_item_id = i.order_item_id and f.order_id = i.order_id
    where f.is_completed_order = 1
), grouped as (
    select coalesce(category,'Unknown category') as category,
        count(*) as completed_lines,
        sum(revenue) as completed_revenue,
        sum(case when known_cost then 1 else 0 end) as known_cost_completed_lines,
        sum(case when known_cost then revenue else 0 end) as known_cost_completed_revenue,
        sum(case when not known_cost then revenue else 0 end) as unknown_cost_completed_revenue,
        sum(case when known_cost then cost end) as known_unit_cost,
        sum(case when known_cost then revenue - cost end) as known_cost_product_contribution
    from lines group by coalesce(category,'Unknown category')
)
select *,
    100.0 * known_cost_completed_revenue / nullif(completed_revenue,0) as cost_revenue_coverage_pct,
    100.0 * known_cost_product_contribution / nullif(known_cost_completed_revenue,0) as known_cost_margin_pct
from grouped order by completed_revenue desc,category;
