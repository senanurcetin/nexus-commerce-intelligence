"""Generate a source-separated decision readout from committed analytical receipts."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INPUTS=('docs/advanced-analysis/evidence.json','docs/advanced-analysis/extension_evidence.json',
    'docs/advanced-analysis/operations_evidence.json','docs/advanced-analysis/review_selection_evidence.json',
    'docs/advanced-analysis/forecast_evidence.json','docs/core-source/status.json','contracts/financial_semantics.json',
    'docs/core-source/operations.json')


def render(root=ROOT):
    data=[json.loads((root/name).read_text(encoding='utf-8')) for name in INPUTS]
    base,repeat,operations,review,forecast,core,semantics,core_operations=data
    from scripts.core_operations import validate
    validate(core_operations, core)
    observed_operations = core_operations['summary']
    if base.get('source_kind')!='historical_public_olist' or base.get('synthetic') is not False:
        raise ValueError('Historical public Olist evidence required')
    if any(e['quality']['files']!=base['quality']['files'] for e in data[1:5]):raise ValueError('Mixed Olist source snapshots')
    if any(core['gates'][key] is not True for key in ('ecommerce_unique_item_and_product_keys','greenweez_unique_order_component_keys','independent_raw_amount_reconciliation')):
        raise ValueError('Source engineering acceptance changed; re-review the readout')
    if review['protocol']['primary_window_days']!=30 or forecast['protocol']['primary_method']!='past_mae_selector' or forecast['protocol']['primary_bootstrap_block_weeks']!=4:
        raise ValueError('Primary analytical protocol changed; re-review the readout')
    if semantics['domains']['greenweez']['refund']['subtract_from_turnover_allowed'] is not False:
        raise ValueError('Financial acceptance policy changed; re-review the readout')
    if any(core['gates'][key] is not False for key in ('currency_verified','refund_meaning_verified','transaction_time_cogs_verified','original_real_business_origin_verified')):
        raise ValueError('Financial/business acceptance gates changed; re-review the readout')
    s=base['summary'];r=repeat['summary']['repeat']['repeat_day_90'];o=operations['summary']
    primary=[row for row in review['summary'] if row['window_days']==30]
    if len(primary)!=1:raise ValueError('Exactly one primary 30-day rating window required')
    p=primary[0];metrics={row['method']:row for row in forecast['metrics']}
    if len(metrics)!=len(forecast['metrics']):raise ValueError('Duplicate forecasting methods')
    selector=metrics['past_mae_selector'];baseline=metrics['seasonal_naive']
    blocks=[row for row in forecast['paired_uncertainty'] if row['block_weeks']==4]
    if len(blocks)!=1:raise ValueError('Exactly one primary four-week paired interval required')
    b=blocks[0]
    supported=b['ci_low']>0
    forecast_decision=('Historical paired interval supports a positive improvement; future utility acceptance remains open.' if supported
        else 'No demonstrated primary selector improvement. Retain the seasonal reference for future validation.')
    rating_decision=('The unrestricted missing-rating range includes zero; its direction is not identified under those assumptions.'
        if p['bound_low']<=0<=p['bound_high'] else 'The unrestricted missing-rating range excludes zero; observational confounding remains unresolved.')
    ledger={'schema_version':1,'purpose':'noncommercial_portfolio_decision_readout',
        'input_hash_basis':'canonical_json_utf8_sorted_keys',
        'inputs_sha256':{name:hashlib.sha256(json.dumps(item,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest() for name,item in zip(INPUTS,data)},
        'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
        'historical_public_olist':{'source_orders':base['quality']['order_fact_rows'],'m1_repeat_rate':s['weighted_m1_retention'],
            'km_90_day_repeat_probability':r['km_repeat_probability'],'delivery_rate_change':o['full_rate_change'],
            'rating_30_day_difference':p['complete_case_difference'],'rating_bound_low':p['bound_low'],'rating_bound_high':p['bound_high'],
            'selector_mae':selector['mae'],'baseline_mae':baseline['mae'],'paired_improvement_ci':[b['ci_low'],b['ci_high']],
            'selector_superiority_demonstrated':supported},
        'private_core_observation':{'financial_acceptance':'HOLD','public_financial_amounts_included':False,
            'operational_item_rows': observed_operations['item_rows'],
            'reversed_delivery_rows': observed_operations['reversed_delivery_rows'],
            'duration_eligible_rows': observed_operations['duration_eligible_rows']},
        'causal_effect_or_operational_utility_certified':False,'native_bi_acceptance':'HOLD'}
    text=f'''# NEXUS: executive analytical readout

The portfolio demonstrates source reconciliation, uncertainty analysis and decision discipline. Its evidence supports targeted investigation and future validation. It does not establish current business performance, causal intervention benefits or deployable forecasts. Historical public Olist, private main-source observations and synthetic demo fixtures are separate populations; their orders, customers and totals must not be added.

## Decisions supported by the evidence

| Question | Recorded evidence | Decision now | Evidence required before a stronger decision |
| --- | --- | --- | --- |
| Can the main E-Commerce/Greenweez finance fields support a profit claim? | Private observation covers {core['tables']['ecommerce.order_items']['rows']:,} item rows and {core['tables']['greenweez.gwz_finance_orders_orders']['rows']:,} Greenweez orders; key/reconciliation checks pass, but origin, currency, refund meaning and transaction-time COGS remain unverified. | HOLD profit and refund-adjusted revenue claims. Retain source fields and complete-component coverage. | Authoritative field/unit definitions and historical cost/refund evidence; successful accounting reconciliation on the same population. |
| Can the observed E-Commerce timestamps support delivery-duration analysis? | {observed_operations['item_rows']:,} item rows span {observed_operations['distinct_order_keys']:,} distinct order keys. {observed_operations['reversed_delivery_rows']:,} rows have delivery before creation. {observed_operations['duration_eligible_rows']:,}/{observed_operations['terminal_item_rows']:,} Complete/Returned items satisfy the timestamp eligibility rule. | Investigate reversed chronology. Calculate duration only on eligible item rows and report excluded coverage. Keep current-status composition at its recorded grain. | Source event definitions and corrected timestamp lineage. Acceptance requires zero reversed rows after validated source correction, with original snapshots preserved. |
| Does Olist support a recurring-customer revenue projection? | Weighted observed month-1 repeat is {s['weighted_m1_retention']:.2%}; 90-day distinct-purchase-day KM repeat is {r['km_repeat_probability']:.2%} among {repeat['summary']['repeat']['origins']:,} origins. These have different calendars and denominators. | Investigate repeat-purchase economics and follow-up feasibility; do not infer churn, CLV or customer intent. | A decision-specific acquisition/retention design, costs, complete follow-up and appropriate new data. No numeric ROI threshold can be inferred here. |
| Where should delivery investigation start? | Matched January–July delivered-order late rates are {o['full_rate_2017']:.2%} in 2017 and {o['full_rate_2018']:.2%} in 2018: {o['full_rate_change']*100:+.2f} pp, cluster interval {o['full_change_ci_low']*100:+.2f} to {o['full_change_ci_high']*100:+.2f} pp. Common support retains {o['common_coverage_2017']:.2%}/{o['common_coverage_2018']:.2%}. | Start record-level diagnosis in high-burden cells, retaining cancellation/non-delivery and geography guardrails. Burden is not a service-quality ranking. | Shipment/process timestamps and exposure denominators; prospective comparable evaluation before claiming an intervention effect. |
| Is the poor-rating contrast robust to unavailable ratings? | The 30-day available-case late-minus-on-time difference is {p['complete_case_difference']*100:+.2f} pp. Sharp hypothetical full-rating bounds are {p['bound_low']*100:+.2f} to {p['bound_high']*100:+.2f} pp across {p['eligible_orders']:,} mature orders. | {rating_decision} | Availability and timing evidence, justified missing-outcome assumptions and a causal design for intervention claims. Bounds are not confidence intervals. |
| Should the selected forecasting policy replace the baseline? | Over {forecast['evaluation_weeks']} held-out weeks, selector MAE is {selector['mae']:.2f} versus {baseline['mae']:.2f} orders/day; paired four-week block improvement interval {b['ci_low']:+.2f} to {b['ci_high']:+.2f}. Empirical week coverage is {selector['week_coverage']:.2%}, with mean band width {selector['mean_width']:.2f} orders/day. | {forecast_decision} Coverage alone is inadequate when bands are wide. | New future outcomes, reliable as-of availability and a predeclared operational loss/band-width budget. Do not select an apparent historical winner after inspecting all methods. |

The preceding decisions are proposed portfolio governance, not executed business actions. There is no measured incremental revenue, intervention ROI or business owner approval. All statistical results are retrospective and population-specific. Sampling intervals do not resolve missing-data identification, confounding or original-source authenticity.

## Acceptance sequence

1. Resolve core source provenance and finance semantics before interpreting margins as business profit. Unknown fields remain unknown; no refund subtraction or zero-cost imputation closes this gate.
2. Translate an actual decision into a declared loss, measurement population, observation schedule and acceptance budget before testing a new model or intervention. The historical extract cannot supply those business preferences.
3. Evaluate a frozen policy on genuinely new future data, with baseline, uncertainty, coverage and interval width together. Positive historical accuracy alone is insufficient.
4. Independently execute native BI refresh/DAX and presentation acceptance before claiming verified interactive delivery. Structural checks, TOM parsing and HTTP/MIME checks remain separate evidence.

No capital, paid resource, payment product or commercial launch is introduced. The project is an English-language analytical portfolio. Public Olist-derived findings retain CC BY-NC-SA 4.0 and [Olist attribution](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce); no endorsement is implied. Private source amounts are excluded.

## Evidence and maintenance

[Core-source acceptance](core-source/README.md) · [Base Olist study](advanced-analysis/REPORT.md) · [Repeat/portfolio study](advanced-analysis/CUSTOMER_PORTFOLIO.md) · [Delivery diagnosis](advanced-analysis/DELIVERY_OPERATIONS.md) · [Rating sensitivity](advanced-analysis/REVIEW_SELECTION.md) · [Forecast validation](advanced-analysis/FORECAST_VALIDATION.md) · [Reproduction](RESEARCH_REPRODUCIBILITY.md) · [Machine-readable decision evidence](executive_readout.json).

Regenerate with `python -m scripts.executive_readout`. This reads committed receipts only: it performs no cloud reads, inference service calls, browser actions or new statistical estimation. Canonical JSON input hashes make stale readouts detectable across Windows/Linux line endings and formatting; the implementation hash normalizes CRLF to LF. Unsupported source, duplicate primary windows, mixed Olist snapshots or changed financial acceptance policy are rejected.
'''
    return text,ledger


def build(root=ROOT,out=None):
    text,ledger=render(root);out=out or root/'docs';out.mkdir(parents=True,exist_ok=True)
    (out/'EXECUTIVE_READOUT.md').write_text(text,encoding='utf-8')
    (out/'executive_readout.json').write_text(json.dumps(ledger,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return ledger


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path);a=p.parse_args()
    result=build(out=a.out);print(json.dumps({'inputs':len(result['inputs_sha256']),'native_bi_acceptance':'HOLD'}))
