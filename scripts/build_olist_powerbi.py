"""Build an independent portable Olist PBIP using validated PUBLIC aggregates."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import zipfile

from scripts.build_powerbi import ROOT, SCHEMA_ROOT, build_project

NAME = "NEXUS_Olist_Research"
TABLES = {
    "Monthly": [("month","dateTime"),("orders","int64"),("items","int64"),("gmv","double"),("freight","double"),("items_per_order","double"),("value_per_item","double")],
    "Cohorts": [("cohort","dateTime"),("period","int64"),("customers","int64"),("active","int64"),("retention","double")],
    "Segments": [("segment","string"),("customers","int64"),("orders","int64"),("gmv","double"),("mean_recency_days","double"),("mean_frequency","double"),("mean_monetary","double")],
    "Decomposition": [("month","dateTime"),("gmv_change","double"),("order_volume","double"),("basket_size","double"),("unit_value","double")],
    "Delivery": [("month","dateTime"),("late","string"),("orders","int64"),("poor","int64")],
    "Association": [("risk_difference","double"),("ci_low","double"),("ci_high","double"),("customers","int64"),("iterations","int64")],
    "RepeatCurve": [("day","int64"),("at_risk","int64"),("events","int64"),("censored","int64"),("repeat_probability","double"),("ci_low","double"),("ci_high","double"),("risk_share","double")],
    "RepeatHorizons": [("day","int64"),("mature_customers","int64"),("mature_repeats","int64"),("mature_repeat_rate","double"),("km_repeat_probability","double"),("at_risk","int64"),("ci_low","double"),("ci_high","double")],
    "CategoryPortfolio": [("category","string"),("item_lines","int64"),("category_order_incidences","int64"),("observed_products","int64"),("gmv","double"),("gmv_share","double"),("cumulative_share","double")],
    "ProductConcentration": [("observed_products","int64"),("gmv","double"),("top_1_share","double"),("top_10_share","double"),("top_100_share","double"),("hhi","double"),("effective_product_count","double")],
    "QuarterConcentration": [("quarter","dateTime"),("observed_products","int64"),("gmv","double"),("top_1_share","double"),("top_10_share","double"),("top_100_share","double"),("hhi","double"),("effective_product_count","double")],
    "OperationsMonthly": [("year","int64"),("month","int64"),("orders","int64"),("late_orders","int64"),("late_rate","double"),("median_transit_days","double"),("p90_transit_days","double")],
    "OperationsStates": [("state","string"),("orders","int64"),("late_orders","int64"),("late_rate","double"),("delivered_late_gmv","double"),("p90_transit_days","double"),("late_order_share","double")],
    "OperationsSummary": [(field,"double") for field in ("full_rate_2017","full_rate_2018","full_rate_change","full_change_ci_low","full_change_ci_high","common_rate_change","within_contribution","mix_contribution","common_coverage_2017","common_coverage_2018","pooled_standardized_rate_2017","pooled_standardized_rate_2018")],
    "ForecastDaily": [("day","dateTime"),("actual_orders","int64"),("prediction","double"),("lower","double"),("upper","double")],
    "ForecastMetrics": [("method","string"),("mae","double"),("rmse","double"),("wape","double"),("mase","double"),("day_coverage","double"),("week_coverage","double"),("mean_width","double"),("interval_score","double")],
}
MEASURES = {
    "Monthly": {"Item GMV (source units)":("SUM(Monthly[gmv])","#,0.00"),
                "Delivered Orders":("SUM(Monthly[orders])","#,0"),
                "GMV per Order":("DIVIDE(SUM(Monthly[gmv]),SUM(Monthly[orders]))","#,0.00")},
    "Cohorts": {"Weighted Retention":("IF(HASONEVALUE(Cohorts[period]), DIVIDE(SUM(Cohorts[active]), SUM(Cohorts[customers])), BLANK())","0.00%")},
    "Segments": {"Customers":("SUM(Segments[customers])","#,0")},
    "Delivery": {"Poor Review Rate":("DIVIDE(SUM(Delivery[poor]), SUM(Delivery[orders]))","0.0%")},
    "Association": {"Late minus On-Time":("MAX(Association[risk_difference])","0.0%"),
                    "95% Lower":("MAX(Association[ci_low])","0.0%"),
                    "95% Upper":("MAX(Association[ci_high])","0.0%")},
    "RepeatCurve": {"Repeat Probability":("IF(HASONEVALUE(RepeatCurve[day]), MAX(RepeatCurve[repeat_probability]))","0.00%"),
                    "Pointwise 95% Lower":("IF(HASONEVALUE(RepeatCurve[day]), MAX(RepeatCurve[ci_low]))","0.00%"),
                    "Pointwise 95% Upper":("IF(HASONEVALUE(RepeatCurve[day]), MAX(RepeatCurve[ci_high]))","0.00%")},
    "RepeatHorizons": {"Mature Repeat Rate":("IF(HASONEVALUE(RepeatHorizons[day]), MAX(RepeatHorizons[mature_repeat_rate]))","0.00%")},
    "CategoryPortfolio": {"Category GMV":("SUM(CategoryPortfolio[gmv])","#,0.00")},
    "ProductConcentration": {"Observed Products":("MAX(ProductConcentration[observed_products])","#,0"),
                             "Top 10 Product Share":("MAX(ProductConcentration[top_10_share])","0.00%"),
                             "Effective Product Count":("MAX(ProductConcentration[effective_product_count])","#,0.0")},
    "QuarterConcentration": {"Quarter Top 10 Share":("IF(HASONEVALUE(QuarterConcentration[quarter]), MAX(QuarterConcentration[top_10_share]))","0.00%")},
    "OperationsMonthly": {"2017 Late Rate":("CALCULATE(DIVIDE(SUM(OperationsMonthly[late_orders]), SUM(OperationsMonthly[orders])), OperationsMonthly[year] = 2017)","0.00%"),
                          "2018 Late Rate":("CALCULATE(DIVIDE(SUM(OperationsMonthly[late_orders]), SUM(OperationsMonthly[orders])), OperationsMonthly[year] = 2018)","0.00%")},
    "OperationsStates": {"2018 Late Orders":("SUM(OperationsStates[late_orders])","#,0")},
    "OperationsSummary": {"2017 Jan-Jul Rate":("MAX(OperationsSummary[full_rate_2017])","0.00%"),
                          "2018 Jan-Jul Rate":("MAX(OperationsSummary[full_rate_2018])","0.00%"),
                          "Rate Change (pp)":("100 * MAX(OperationsSummary[full_rate_change])","0.00")},
    "ForecastDaily": {label:(f'IF(HASONEVALUE(ForecastDaily[day]), MAX(ForecastDaily[{field}]))','#,0.0') for label,field in (
        ('Observed Placed Orders','actual_orders'),('Selected Forecast','prediction'),('Reference Lower','lower'),('Reference Upper','upper'))},
    "ForecastMetrics": {"Benchmark MAE":('MAX(ForecastMetrics[mae])','0.00'),
        "Selector MAE":('CALCULATE(MAX(ForecastMetrics[mae]), ForecastMetrics[method] = "past_mae_selector")','0.00'),
        "Selector Week Coverage":('CALCULATE(MAX(ForecastMetrics[week_coverage]), ForecastMetrics[method] = "past_mae_selector")','0.0%'),
        "Selector Mean Width":('CALCULATE(MAX(ForecastMetrics[mean_width]), ForecastMetrics[method] = "past_mae_selector")','0.0')},
}
PAGES = [
    {"id":"olist_value","title":"Olist | Value and order volume", "cards":[("Monthly",m) for m in MEASURES["Monthly"]],
     "charts":[("lineChart","Monthly",["month"],"Item GMV (source units)","Delivered item GMV by purchase month"),
               ("lineChart","Monthly",["month"],"Delivered Orders","Delivered orders by purchase month")]},
    {"id":"olist_cohorts","title":"Olist | Observed repeat-purchase cohorts","cards":[],
     "charts":[("pivotTable","Cohorts",["cohort","period"],"Weighted Retention","Observed cells only; future periods blank; M0 = 100% by construction")]},
    {"id":"olist_segments","title":"Olist | As-of customer policies","cards":[("Segments","Customers")],
     "charts":[("tableEx","Segments",["segment","customers","orders","gmv","mean_recency_days"],None,"90-day recency policy; 1 versus 2+ orders; delivered before cutoff")]},
    {"id":"olist_decomposition","title":"Olist | Exact GMV change decomposition","cards":[],
     "charts":[("tableEx","Decomposition",["month","gmv_change","order_volume","basket_size","unit_value"],None,"Six-ordering Shapley contributions in source units; accounting identity, not causal effects")]},
    {"id":"olist_delivery","title":"Olist | Delivery and poor reviews","cards":[("Association",m) for m in MEASURES["Association"]],
     "charts":[("tableEx","Delivery",["month","late","orders","poor"],None,"Poor = score 1–2; reviews answered after delivery; association, not causation")]},
    {"id":"olist_repeat_timing","title":"Olist | Time to another purchase day","cards":[],
     "charts":[("lineChart","RepeatCurve",["day"],"Repeat Probability","Pooled Kaplan–Meier with pointwise 95% limits; first 180 days"),
               ("lineChart","RepeatHorizons",["day"],"Mature Repeat Rate","Direct rates at 30/60/90/180 days; different mature origin populations")]},
    {"id":"olist_portfolio","title":"Olist | Product value concentration","cards":[("ProductConcentration",m) for m in MEASURES["ProductConcentration"]],
     "charts":[("clusteredBarChart","CategoryPortfolio",["category"],"Category GMV","Category item GMV; category-order incidences are not additive orders"),
               ("lineChart","QuarterConcentration",["quarter"],"Quarter Top 10 Share","Complete quarters only; within-portfolio measure, not market power")]},
    {"id":"olist_operations","title":"Olist | Comparable delivery experience","cards":[("OperationsSummary",m) for m in MEASURES["OperationsSummary"]],
     "charts":[("lineChart","OperationsMonthly",["month"],"2017 Late Rate","January-July in both years; full eligible delivered-order populations"),
               ("clusteredBarChart","OperationsStates",["state"],"2018 Late Orders","2018 observed late-order burden by state; counts, not quality ranking")]},
    {"id":"olist_forecasting","title":"Olist | Temporal forecasting validation","cards":[('ForecastMetrics',m) for m in ('Selector MAE','Selector Week Coverage','Selector Mean Width')],
     "charts":[('lineChart','ForecastDaily',['day'],'Selected Forecast','2018 held-out days: actual, forecast and rolling reference limits'),
               ('clusteredBarChart','ForecastMetrics',['method'],'Benchmark MAE','Same-date MAE comparison; lower is better; no test-set tuning')]},
]
CONTEXT = {
    "olist_value":"PUBLIC OLIST / 2017–July 2018 purchase window / Item GMV excludes freight; not net revenue",
    "olist_cohorts":"PUBLIC OLIST / Retrospective delivered status / Original cohort denominator; no lifetime acquisition claim",
    "olist_segments":"PUBLIC OLIST / As of 2018-08-01 / Earlier observed purchase history included / Demonstration policy",
    "olist_decomposition":"PUBLIC OLIST / Orders × items per order × value per item / Adjacent complete purchase months",
    "olist_delivery":"PUBLIC OLIST / Customer-cluster bootstrap 95% interval / Fixed overall contrast; does not follow month filters",
    "olist_repeat_timing":"PUBLIC OLIST / Distinct purchase days / Last observation 2018-07-31 / Independent censoring unverified",
    "olist_portfolio":"PUBLIC OLIST / Fixed full-window cards; quarter selections do not recompute them / Unknown categories retained",
    "olist_operations":"PUBLIC OLIST / Fixed Jan-Jul cards / Details and uncertainty in DELIVERY_OPERATIONS.md / Delivered-only, not causal",
    "olist_forecasting":"PUBLIC OLIST / ALL placed orders / Past-only selection / Fixed benchmark cards / No guaranteed temporal coverage",
}


def create(source: Path, out: Path, extension: Path | None=None, operations: Path | None=None, reviews: Path | None=None, forecast: Path | None=None) -> Path:
    extension=extension or source
    operations=operations or source
    reviews=reviews or source
    forecast=forecast or source
    evidence=json.loads((source/"evidence.json").read_text(encoding="utf-8"))
    extra=json.loads((extension/'extension_evidence.json').read_text(encoding='utf-8'))
    if extra.get('source_kind')!='historical_public_olist_extension' or extra['summary']['repeat']['last_observed_day']!='2018-07-31':
        raise ValueError('Only the documented public Olist extension accepted')
    if {k:v['sha256'] for k,v in extra['quality']['files'].items()}!={k:v['sha256'] for k,v in evidence['quality']['files'].items()}:
        raise ValueError('Base and extension source snapshots differ')
    if extra.get('order_fact_sql_sha256')!=evidence['sql_sha256']['order_fact.sql']:
        raise ValueError('Base and extension order fact definitions differ')
    if not math.isclose(extra['summary']['portfolio']['gmv'],evidence['summary']['gmv_source_units'],rel_tol=0,abs_tol=.005):
        raise ValueError('Base and extension purchase-window GMV differs')
    ops=json.loads((operations/'operations_evidence.json').read_text(encoding='utf-8'))
    if ops.get('source_kind')!='historical_public_olist_operations':raise ValueError('Only public Olist operations accepted')
    if {k:v['sha256'] for k,v in ops['quality']['files'].items()}!={k:v['sha256'] for k,v in evidence['quality']['files'].items()}:
        raise ValueError('Operations source snapshots differ')
    if ops.get('order_fact_sql_sha256')!=evidence['sql_sha256']['order_fact.sql']:
        raise ValueError('Operations order fact definitions differ')
    review=json.loads((reviews/'review_selection_evidence.json').read_text(encoding='utf-8'))
    if review.get('source_kind')!='historical_public_olist_review_selection' or review.get('synthetic') is not False:
        raise ValueError('Only public Olist review selection accepted')
    if {k:v['sha256'] for k,v in review['quality']['files'].items()}!={k:v['sha256'] for k,v in evidence['quality']['files'].items()}:
        raise ValueError('Review selection source snapshots differ')
    if review.get('order_fact_sql_sha256')!=evidence['sql_sha256']['order_fact.sql']:
        raise ValueError('Review selection order fact definitions differ')
    for filename,key in (('olist_review_protocol.json','protocol_sha256'),('review_selection.sql','query_sha256')):
        if hashlib.sha256((reviews/filename).read_bytes()).hexdigest()!=review[key]:
            raise ValueError('Review selection protocol/query hash mismatch: '+filename)
    prediction=json.loads((forecast/'forecast_evidence.json').read_text(encoding='utf-8'))
    if prediction.get('source_kind')!='historical_public_olist_forecast' or prediction.get('synthetic') is not False:
        raise ValueError('Only public Olist forecast accepted')
    if prediction['quality']['files']!=evidence['quality']['files']:
        raise ValueError('Forecast source snapshots differ')
    if prediction.get('order_fact_sql_sha256')!=evidence['sql_sha256']['order_fact.sql']:
        raise ValueError('Forecast order fact definitions differ')
    for filename,key in (('olist_forecast_protocol.json','protocol_sha256'),('daily_order_volume.sql','query_sha256')):
        if hashlib.sha256((forecast/filename).read_bytes()).hexdigest()!=prediction[key]:
            raise ValueError('Forecast protocol/query hash mismatch: '+filename)
    if evidence.get("source_kind")!="historical_public_olist" or evidence.get("synthetic") is not False:
        raise ValueError("Only content-addressed public Olist aggregates accepted")
    if evidence["summary"]["cutoff"]!="2018-08-01":
        raise ValueError("This report's page labels require the documented 2018-08-01 cutoff")
    rows={}
    for name,filename in (("Monthly","monthly"),("Cohorts","cohorts"),("Segments","segments"),("Decomposition","decomposition"),("Delivery","delivery_months")):
        path=source/(filename+".csv")
        if hashlib.sha256(path.read_bytes()).hexdigest()!=evidence["export_sha256"][path.name]:
            raise ValueError("Aggregate file hash mismatch: "+path.name)
        with path.open(encoding="utf-8",newline="") as stream:
            records=list(csv.DictReader(stream))
        if name=="Cohorts":
            records=[r for r in records if r["observable"]=="True"]
        rows[name]=[{field: (None if r[field]=="" else int(float(r[field])) if kind=="int64" else float(r[field]) if kind=="double" else r[field])
                     for field,kind in TABLES[name]} for r in records]
    rows["Association"]=[{field:evidence["summary"]["delivery_association"][field] for field,_ in TABLES["Association"]}]
    for name,filename in (("RepeatCurve","repeat_curve"),("RepeatHorizons","repeat_horizons"),("CategoryPortfolio","category_portfolio"),("ProductConcentration","product_concentration"),("QuarterConcentration","quarter_concentration")):
        path=extension/(filename+'.csv')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=extra['aggregate_sha256'][path.name]:
            raise ValueError('Extension aggregate file hash mismatch: '+path.name)
        with path.open(encoding='utf-8',newline='') as stream: records=list(csv.DictReader(stream))
        rows[name]=[{field:(None if r[field]=='' else int(float(r[field])) if kind=='int64' else float(r[field]) if kind=='double' else r[field])
                     for field,kind in TABLES[name]} for r in records]
    for name,filename in (("OperationsMonthly","operations_monthly"),("OperationsStates","operations_states"),("OperationsSummary","operations_summary")):
        path=operations/(filename+'.csv')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=ops['aggregate_sha256'][path.name]:
            raise ValueError('Operations aggregate file hash mismatch: '+path.name)
        with path.open(encoding='utf-8',newline='') as stream: records=list(csv.DictReader(stream))
        rows[name]=[{field:(None if r[field]=='' else int(float(r[field])) if kind=='int64' else float(r[field]) if kind=='double' else r[field])
                     for field,kind in TABLES[name]} for r in records]
    for name,filename in (('ForecastDaily','forecast_daily'),('ForecastMetrics','forecast_metrics')):
        path=forecast/(filename+'.csv')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=prediction['aggregate_sha256'][path.name]:
            raise ValueError('Forecast aggregate file hash mismatch: '+path.name)
        with path.open(encoding='utf-8',newline='') as stream:records=list(csv.DictReader(stream))
        if name=='ForecastDaily':records=[r for r in records if r['phase']=='evaluation' and r['method']=='past_mae_selector']
        rows[name]=[{field:(None if r[field]=='' else int(float(r[field])) if kind=='int64' else float(r[field]) if kind=='double' else r[field]) for field,kind in TABLES[name]} for r in records]
    project=build_project(out,out/"unused",portable_rows=rows,tables=TABLES,measures=MEASURES,pages=PAGES,model_name=NAME)
    model=project.parent/(NAME+".SemanticModel/definition/model.tmdl")
    model.write_text("model Model\n\tculture: en-US\n\tsourceQueryCulture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n",encoding="utf-8")
    for page in PAGES:
        for key,value,y,size,color in (("title",page["title"],20,"22px","#EDF2F8"),
                                       ("context",CONTEXT[page["id"]],62,"10px","#8F9BFF")):
            visual={"$schema":SCHEMA_ROOT+"item/report/definition/visualContainer/2.7.0/schema.json",
                "name":key,"position":{"x":290,"y":y,"z":9500,"width":950,"height":34,"tabOrder":95},
                "visual":{"visualType":"textbox","objects":{"general":[{"properties":{"paragraphs":[{"textRuns":[{"value":value,"textStyle":{"fontFamily":"Segoe UI","fontSize":size,"color":color}}]}]}}]},"drillFilterOtherVisuals":True}}
            path=project.parent/(NAME+".Report/definition/pages")/page["id"]/"visuals"/key/"visual.json"
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(visual,indent=2)+"\n",encoding="utf-8")
    # Three named measures preserve the published estimate and pointwise limits.
    visual=project.parent/(NAME+'.Report/definition/pages/olist_repeat_timing/visuals/00000000000000000001/visual.json')
    spec=json.loads(visual.read_text())
    from scripts.build_powerbi import _field
    spec['visual']['query']['queryState']['Y']['projections']=[_field('RepeatCurve',m,True) for m in MEASURES['RepeatCurve']]
    visual.write_text(json.dumps(spec,indent=2)+'\n',encoding='utf-8')
    visual=project.parent/(NAME+'.Report/definition/pages/olist_forecasting/visuals/00000000000000000004/visual.json')
    spec=json.loads(visual.read_text())
    spec['visual']['query']['queryState']['Y']['projections']=[_field('ForecastDaily',m,True) for m in MEASURES['ForecastDaily']]
    visual.write_text(json.dumps(spec,indent=2)+'\n',encoding='utf-8')
    visual=project.parent/(NAME+'.Report/definition/pages/olist_operations/visuals/00000000000000000004/visual.json')
    spec=json.loads(visual.read_text())
    spec['visual']['query']['queryState']['Y']['projections']=[_field('OperationsMonthly',m,True) for m in MEASURES['OperationsMonthly']]
    visual.write_text(json.dumps(spec,indent=2)+'\n',encoding='utf-8')
    receipt={"source_evidence_sha256":hashlib.sha256((source/"evidence.json").read_bytes()).hexdigest(),
             "pages":len(PAGES),"aggregate_rows":{k:len(v) for k,v in rows.items()},
             "extension_evidence_sha256":hashlib.sha256((extension/'extension_evidence.json').read_bytes()).hexdigest(),
             "operations_evidence_sha256":hashlib.sha256((operations/'operations_evidence.json').read_bytes()).hexdigest(),
             "review_selection_evidence_sha256":hashlib.sha256((reviews/'review_selection_evidence.json').read_bytes()).hexdigest(),
             "forecast_evidence_sha256":hashlib.sha256((forecast/'forecast_evidence.json').read_bytes()).hexdigest(),
             "synthetic":False,"desktop_render_verified":False,"dax_engine_executed":False,
             "note":"Association cards are full-sample estimates, independent of monthly table selections."}
    (out/"build_evidence.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    (project.parent/"SOURCE_AND_LICENSE.md").write_text(
        "# NEXUS Olist Research\n\n"
        "Source: Brazilian E-Commerce Public Dataset by Olist, "
        "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce\n\n"
        "Olist-derived aggregates and this data-containing report: CC BY-NC-SA 4.0 "
        "(https://creativecommons.org/licenses/by-nc-sa/4.0/). "
        "NEXUS prepared the analytical transformations; this is a non-commercial portfolio study, "
        "not endorsed by Olist. Source and calculation fingerprints accompany this package.\n\n"
        "Purchase window: January 2017 through July 2018. As-of customer policies include earlier observed history. "
        "Item GMV is in source price units, excludes freight and is not net revenue or profit. "
        "Late-delivery contrasts use post-delivery review answers and are selected-sample associations, not causal effects. "
        "Repeat timing uses distinct purchase days with administrative censoring; pointwise intervals do not validate independent censoring. "
        "Product concentration is within this portfolio, not a market-wide competition measure. "
        "Operations compares January-July in both years, without a review-response filter. "
        "Rate/mix contributions are descriptive, and late-delivered GMV is not revenue lost. "
        "The fourth bundled study, REVIEW_SELECTION.md, analyzes unavailable ratings with a different mature cohort; "
        "its sharp ranges are not confidence intervals or causal effects. It is a companion report, not a native BI page. "
        "The forecasting page counts all placed orders, including non-deliveries; its temporal calibration has no guaranteed coverage. "
        "Confidence cards refer to the full sample and do not follow monthly selections.\n\n"
        "Desktop rendering, refresh and DAX execution are unverified. "
        "Open the entire PBIP folder in a compatible Power BI Desktop installation.\n",
        encoding="utf-8")
    (project.parent/'analysis_evidence.json').unlink(missing_ok=True)  # Superseded generated filename.
    (project.parent/"evidence.json").write_text(json.dumps(evidence,indent=2)+"\n",encoding="utf-8")
    (project.parent/'extension_evidence.json').write_text(json.dumps(extra,indent=2)+'\n',encoding='utf-8')
    (project.parent/'operations_evidence.json').write_text(json.dumps(ops,indent=2)+'\n',encoding='utf-8')
    (project.parent/'review_selection_evidence.json').write_text(json.dumps(review,indent=2)+'\n',encoding='utf-8')
    (project.parent/'forecast_evidence.json').write_text(json.dumps(prediction,indent=2)+'\n',encoding='utf-8')
    # Include the inspectable reports and their referenced images/CSV evidence.
    for folder,receipt,names,media in (
        (source,evidence['export_sha256'],('cohorts','segments','monthly','decomposition','delivery_months','delivery_states','delivery_common_support'),
         ('REPORT.md','cohort_retention.png','gmv_decomposition.png','customer_policies.png','delivery_sensitivity.png')),
        (extension,extra['aggregate_sha256'],('repeat_ledger','repeat_curve','repeat_horizons','category_portfolio','product_concentration','quarter_concentration'),
         ('CUSTOMER_PORTFOLIO.md','repeat_purchase_survival.png','category_portfolio.png')),
        (operations,ops['aggregate_sha256'],('operations_monthly','operations_states','operations_strata','operations_summary','operations_month_contributions'),
         ('DELIVERY_OPERATIONS.md','delivery_matched_months.png','delivery_rate_mix.png')),
        (reviews,review['aggregate_sha256'],('review_groups','review_summary','review_sensitivity','review_tipping','review_availability'),
         ('REVIEW_SELECTION.md','review_bounds.png','review_sensitivity_grid.png','olist_review_protocol.json','review_selection.sql')),
        (forecast,prediction['aggregate_sha256'],('forecast_volume','forecast_daily','forecast_folds','forecast_metrics','forecast_uncertainty'),
         ('FORECAST_VALIDATION.md','forecast_temporal.png','forecast_benchmarks.png','olist_forecast_protocol.json','daily_order_volume.sql')),
    ):
        for name in names:
            filename=name+'.csv';data=(folder/filename).read_bytes()
            if hashlib.sha256(data).hexdigest()!=receipt[filename]:
                raise ValueError('Packaged aggregate file hash mismatch: '+filename)
            (project.parent/filename).write_bytes(data)
        for filename in media:(project.parent/filename).write_bytes((folder/filename).read_bytes())
    return project


def package(project: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination,"w",zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(project.parent.rglob("*")):
            if path.is_file():
                info=zipfile.ZipInfo(path.relative_to(project.parent).as_posix(),date_time=(2026,10,27,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                archive.writestr(info,path.read_bytes())


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=ROOT/"docs/advanced-analysis")
    parser.add_argument("--out",type=Path,default=ROOT/"target/powerbi-olist")
    parser.add_argument('--extension',type=Path,help='Extension aggregates; defaults to the same folder as --source')
    parser.add_argument('--operations',type=Path,help='Operations aggregates; defaults to the same folder as --source')
    parser.add_argument('--reviews',type=Path,help='Review-selection aggregates; defaults to the same folder as --source')
    parser.add_argument('--forecast',type=Path,help='Forecast aggregates; defaults to the same folder as --source')
    parser.add_argument("--package",type=Path)
    args=parser.parse_args()
    path=create(args.source,args.out,args.extension,args.operations,args.reviews,args.forecast)
    if args.package: package(path,args.package)
    print(path)
