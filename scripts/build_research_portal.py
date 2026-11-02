"""Build a separate public-history research surface from the pinned Olist ZIP.

No raw dataset, private account, cloud read, network asset or browser is used.
Every number is projected from the validated research receipts/aggregate CSVs.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
UI_FILES=('index.html','research.css','research.mjs','research-metrics.mjs')
WEBSITE_PROVENANCE='synthetic_commerce_and_separate_historical_public_olist'
RECEIPTS=('evidence.json','extension_evidence.json','operations_evidence.json','review_selection_evidence.json','forecast_evidence.json')
FIGURES=(('cohort_retention.png','gmv_decomposition.png','customer_policies.png','delivery_sensitivity.png'),
         ('repeat_purchase_survival.png','category_portfolio.png'),('delivery_matched_months.png','delivery_rate_mix.png'),
         ('review_bounds.png','review_sensitivity_grid.png'),('forecast_temporal.png','forecast_benchmarks.png'))
REPORTS=('REPORT.md','CUSTOMER_PORTFOLIO.md','DELIVERY_OPERATIONS.md','REVIEW_SELECTION.md','FORECAST_VALIDATION.md')


def encoded(value):return (json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode('utf-8')


def payload(files,archive_sha):
    receipts=[json.loads(files[name]) for name in RECEIPTS]
    base,customer,operations,review,forecast=receipts
    s=base['summary'];r=customer['summary']['repeat'];o=operations['summary'];p=next(x for x in review['summary'] if x['window_days']==30)
    def rows(name):return list(csv.DictReader(io.StringIO(files[name].decode('utf-8'))))
    forecasts=[{**{k:row[k] for k in ('day','origin','method')},**{k:float(row[k]) for k in ('actual_orders','prediction','lower','upper')}}
               for row in rows('forecast_daily.csv') if row['phase']=='evaluation']
    methods={m['method'] for m in forecast['metrics']}
    if len(forecasts)!=840 or methods!={'seasonal_naive','weekday_mean_28','ridge_calendar_180','past_mae_selector'}:
        raise ValueError('Portal requires the documented four-method 210-day forecast comparison')
    if any(x['method'] not in methods or x['lower']>x['upper'] for x in forecasts):raise ValueError('Invalid forecast projection')
    reference=None
    for method in sorted(methods):
        selected=[r for r in forecasts if r['method']==method]
        values={r['day']:r['actual_orders'] for r in selected}
        if len(selected)!=210 or len(values)!=210 or reference is not None and values!=reference:
            raise ValueError('Forecast methods do not share identical evaluation dates and actual counts')
        reference=values
    groups={}
    for row in rows('review_groups.csv'):
        if row['window_days']=='30':groups['late' if row['late']=='True' else 'on_time']={
            'poor':int(row['poor_ratings']),'observed':int(row['observed_ratings']),'total':int(row['eligible_orders'])}
    primary=next(x for x in forecast['paired_uncertainty'] if x['block_weeks']==4)
    forecast_conclusion=('The selector shows positive historical improvement under the primary block setting; future validation is still required.' if primary['ci_low']>0 else
                         'The selector underperforms seasonal naive under the primary paired comparison.' if primary['ci_high']<0 else
                         'The declared selector does not demonstrate superiority over seasonal naive in the primary paired comparison.')
    definitions=[
        ('core','Repeat, value & attribution','Where does observed repeat purchasing narrow?',
         f"Month-1 repeat purchasing is {s['weighted_m1_retention']:.2%} across {s['m1_cohorts']} fully observable cohorts.",
         'Use original cohort denominators and investigate repeat journeys before proposing retention interventions.',
         f"{s['orders']:,} delivered orders; January 2017–July 2018 purchase window.",
         'Observation-aware cohorts · as-of RFM · exact Shapley decomposition',
         'Historical delivered-status selection; no causal marketing effect, cash refund or current performance claim.'),
        ('customer','Purchase timing & portfolio','How does another purchase day accumulate over time?',
         f"At 90 days, pooled repeat-day probability is {r['repeat_day_90']['km_repeat_probability']:.2%}; the mature-origin rate is {r['repeat_day_90']['mature_repeat_rate']:.2%}.",
         'Compare time-to-repeat with mature cohorts; keep product concentration separate from market competition.',
         f"{r['origins']:,} observed customer origins; {customer['summary']['portfolio']['observed_products']:,} observed products.",
         'Kaplan–Meier · independently checked Greenwood intervals · concentration',
         'Independent censoring and marketplace completeness are unverified. These rates do not measure churn.'),
        ('operations','Comparable delivery','Did experience change across the same calendar months?',
         f"Late delivered-order rates rise from {o['full_rate_2017']:.2%} to {o['full_rate_2018']:.2%} across matched January–July windows.",
         'Start root-cause review in high-burden states and contributing month/state cells; retain non-delivery guardrails.',
         f"{o['orders_2017']+o['orders_2018']:,} eligible delivered orders; January–July 2017 versus 2018.",
         'Customer-cluster uncertainty · common-support coverage · Kitagawa rate/mix',
         'Delivered-only descriptive comparison. State burden is not a quality ranking and decomposition is not causal.'),
        ('review','Review selection sensitivity','Could unavailable ratings change the observed direction?',
         f"The 30-day available-case difference is {p['complete_case_difference']*100:+.2f} pp; the sharp full-rating range is {p['bound_low']*100:+.2f} to {p['bound_high']*100:+.2f} pp.",
         'Keep rating availability and timing exclusions beside the observed association; its sign is not robust to unrestricted missing-rating assumptions.',
         f"{p['eligible_orders']:,} mature delivered orders; common 7/30/90-day follow-up cohort.",
         'First eligible answer · sharp binary-outcome bounds · pattern-mixture sensitivity',
         'Unavailable ratings include existing pre-delivery-only answers. Sharp ranges are not confidence intervals or causal effects.'),
        ('forecast','Temporal forecasting','Does past-only method selection improve next-week forecasts?',
         forecast_conclusion,
         'Keep the seasonal baseline as a reference; obtain new future validation before promoting a more complex method.',
         f"{forecast['placed_orders']:,} ALL placed orders / {forecast['series_days']} calendar days; 30 non-overlapping evaluation weeks.",
         'Past-only selection & calibration · leakage falsification · paired block uncertainty',
         'All order statuses enter this target. Rolling reference bands have no guaranteed temporal coverage or live deployment validity.')]
    studies=[dict(zip(('id','title','question','finding','decision','population','methods','limits'),item),
                  report='evidence/'+REPORTS[i],figures=['evidence/'+f for f in FIGURES[i]],receipt='evidence/'+RECEIPTS[i]) for i,item in enumerate(definitions)]
    return {'version':1,'provenance':'historical_public_olist','synthetic':False,
        'source':base['source'],'license':'CC-BY-NC-SA-4.0','archive_sha256':archive_sha,
        'source_orders':base['quality']['order_fact_rows'],'studies':studies,
        'forecast':{'rows':forecasts,'metrics':forecast['metrics'],'uncertainty':forecast['paired_uncertainty']},
        'review':{'groups':groups,'summary':p},'desktop_render_verified':False,'browser_render_verified':False}


def assets(root:Path=ROOT):
    # Import lazily: release_audit also validates this generated surface.
    from scripts.release_audit import load_pinned,research_bundle,native_project
    root=root.resolve();manifest=json.loads((root/'powerbi/olist-package-manifest.json').read_text())
    files,info=load_pinned(root,'powerbi/NEXUS_Olist_Research.zip',manifest)
    research_bundle(root,files,manifest)
    native_project(files,'NEXUS_Olist_Research',9,16,(root/'branding/nexus_official_transparent.png').read_bytes())
    result={name:(root/'showcase/research'/name).read_bytes().replace(b'\r\n',b'\n') for name in UI_FILES}
    result['data.json']=encoded(payload(files,info['sha256']))
    names=set(REPORTS)|set(RECEIPTS)|{f for group in FIGURES for f in group}|{
        'SOURCE_AND_LICENSE.md','olist_review_protocol.json','review_selection.sql','olist_forecast_protocol.json','daily_order_volume.sql'}
    for receipt in RECEIPTS:
        e=json.loads(files[receipt]);names.update(e.get('aggregate_sha256',e.get('export_sha256',{})))
    for name in sorted(names):result['evidence/'+name]=files[name]
    result['NEXUS_Olist_Research.zip']=(root/'powerbi/NEXUS_Olist_Research.zip').read_bytes()
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in result.items()}
    result['portal-manifest.json']=encoded({'provenance':'historical_public_olist','license':'CC-BY-NC-SA-4.0',
        'source_archive_sha256':info['sha256'],'files_sha256':hashes,'browser_render_verified':False})
    return result
