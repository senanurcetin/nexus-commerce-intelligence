-- Does session conversion actually differ by traffic source?
--
-- The dashboard ranks channels by conversion. That ranking is only meaningful if
-- the gaps are larger than sampling noise, so this tests it rather than assuming
-- it. Chi-square test of independence: the null hypothesis is that every source
-- converts at the pooled rate and the observed spread is noise.
--
--   Reject the null when chi_square_total exceeds the critical value for its
--   degrees of freedom. With df = 4 and alpha = 0.05 that is 9.49.
--
-- Execute against the selected snapshot; do not reuse historical statistics.
-- Approximation requires all expected converted AND non-converted cells >= 5.
-- A non-significant result is insufficient evidence of a difference, not proof
-- of equivalent rates. Observational traffic is not an experiment.
--
-- Run with:
--   dbt compile --select path:analyses/channel_conversion_significance.sql
-- then execute the compiled SQL in the warehouse.

with by_source as (

    select
        traffic_source,
        channel_group,
        count(*) as sessions,
        sum(case when is_converted = 1 then 1 else 0 end) as conversions
    from {{ ref('fct_marketing_web_performance') }}
    group by traffic_source, channel_group

),

pooled as (

    select
        cast(sum(conversions) as {{ dbt.type_float() }}) / nullif(sum(sessions), 0) as pooled_rate
    from by_source

),

contributions as (

    select
        b.traffic_source,
        b.channel_group,
        b.sessions,
        b.conversions,
        cast(b.conversions as {{ dbt.type_float() }}) / nullif(b.sessions, 0) as conversion_rate,

        b.sessions * p.pooled_rate as expected_conversions,
        b.sessions * (1 - p.pooled_rate) as expected_nonconversions,

        -- This source's contribution to the statistic: the converted cell plus
        -- the non-converted cell, each (observed - expected)^2 / expected.
        power(b.conversions - b.sessions * p.pooled_rate, 2)
            / nullif(b.sessions * p.pooled_rate, 0)
        + power((b.sessions - b.conversions) - b.sessions * (1 - p.pooled_rate), 2)
            / nullif(b.sessions * (1 - p.pooled_rate), 0) as chi_square_contribution

    from by_source b
    cross join pooled p

)

select
    traffic_source,
    channel_group,
    sessions,
    conversions,
    round(conversion_rate * 100, 2) as conversion_rate_pct,
    round(expected_conversions, 0) as expected_conversions,
    round(expected_nonconversions, 0) as expected_nonconversions,
    round(chi_square_contribution, 2) as chi_square_contribution,

    round(sum(chi_square_contribution) over (), 2) as chi_square_total,
    count(*) over () - 1 as degrees_of_freedom,
    case when count(*) over () >= 2
          and min(expected_conversions) over () >= 5
          and min(expected_nonconversions) over () >= 5
         then true else false end as chi_square_approximation_supported

from contributions
order by conversion_rate desc
