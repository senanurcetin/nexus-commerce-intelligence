{{ config(enabled=var('source_system', 'gwz_raw') == 'gwz_raw') }}
-- Raw product-line branch only. Never impute missing costs to zero here.
-- Preserve the established finance model and report its coverage separately.
with lines as (
    select s.orders_id,s.date_date,s.revenue,s.quantity,p.purchase_price,
        s.revenue is not null and s.quantity is not null and s.quantity >= 0
        and p.purchase_price is not null and p.purchase_price >= 0 as known_cost
    from {{ ref('stg_raw__sales') }} s
    left join {{ ref('stg_raw__product') }} p using(products_id)
), orders as (
    select orders_id,date_date,count(*) as sales_lines,
        sum(case when known_cost then 1 else 0 end) as priced_lines,
        sum(case when known_cost then revenue else 0 end) as known_cost_line_revenue,
        sum(case when not known_cost then revenue else 0 end) as unknown_cost_line_revenue,
        sum(case when revenue is null then 1 else 0 end) as missing_revenue_lines,
        sum(case when known_cost then revenue - quantity * purchase_price end) as known_cost_product_contribution
    from lines group by orders_id,date_date
), coverage as (
    select o.*,
        case when o.priced_lines=o.sales_lines then 'fully_priced'
             when o.priced_lines=0 then 'unpriced' else 'partly_priced' end as product_cost_coverage,
        case when s.orders_id is not null and s.shipping_fee >= 0 and s.log_cost >= 0 and s.ship_cost >= 0
             then 'complete' else 'missing_or_invalid' end as shipping_coverage,
        f.revenue,f.margin as reported_product_margin,f.operational_margin as reported_operational_margin
    from orders o join {{ ref('int_orders_operational') }} f using(orders_id,date_date)
    left join {{ ref('stg_raw__ship') }} s using(orders_id)
)
select product_cost_coverage,shipping_coverage,
    count(*) as orders,sum(sales_lines) as sales_lines,
    sum(sales_lines-priced_lines) as unpriced_lines,
    sum(missing_revenue_lines) as missing_revenue_lines,
    sum(revenue) as revenue,
    sum(known_cost_line_revenue) as known_cost_line_revenue,
    sum(unknown_cost_line_revenue) as unknown_cost_line_revenue,
    sum(known_cost_product_contribution) as known_cost_product_contribution,
    sum(reported_product_margin) as reported_product_margin,
    sum(reported_operational_margin) as reported_operational_margin,
    sum(case when product_cost_coverage='fully_priced' and shipping_coverage='complete'
             then reported_operational_margin end) as complete_components_operational_margin
from coverage group by product_cost_coverage,shipping_coverage
order by product_cost_coverage,shipping_coverage;
