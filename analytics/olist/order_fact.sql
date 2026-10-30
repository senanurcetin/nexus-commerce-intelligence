-- One row per order. Aggregate the many sides BEFORE joining them.
-- Reviews: latest answer timestamp, then creation time, ID and score break ties.
create or replace table order_fact as
with items as (
    select order_id, count(*)::integer as items, sum(price) as gmv,
           sum(freight_value) as freight
    from raw_items group by order_id
), reviews as (
    select order_id, review_score, review_creation_date, review_answer_timestamp
    from raw_reviews
    qualify row_number() over (partition by order_id order by
        review_answer_timestamp desc nulls last, review_creation_date desc nulls last,
        review_id desc, review_score desc) = 1
)
select o.order_id, c.customer_unique_id, c.customer_state, o.order_status,
       o.order_purchase_timestamp as purchased_at,
       o.order_delivered_customer_date as delivered_at,
       o.order_estimated_delivery_date as estimated_at,
       i.items, i.gmv, i.freight, r.review_score,
       r.review_creation_date, r.review_answer_timestamp
from raw_orders o
left join raw_customers c using (customer_id)
left join items i using (order_id)
left join reviews r using (order_id);
