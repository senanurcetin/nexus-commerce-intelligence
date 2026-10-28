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
]
CONTEXT = {
    "olist_value":"PUBLIC OLIST / 2017–July 2018 purchase window / Item GMV excludes freight; not net revenue",
    "olist_cohorts":"PUBLIC OLIST / Retrospective delivered status / Original cohort denominator; no lifetime acquisition claim",
    "olist_segments":"PUBLIC OLIST / As of 2018-08-01 / Earlier observed purchase history included / Demonstration policy",
    "olist_decomposition":"PUBLIC OLIST / Orders × items per order × value per item / Adjacent complete purchase months",
    "olist_delivery":"PUBLIC OLIST / Customer-cluster bootstrap 95% interval / Fixed overall contrast; does not follow month filters",
    "olist_repeat_timing":"PUBLIC OLIST / Distinct purchase days / Last observation 2018-07-31 / Independent censoring unverified",
    "olist_portfolio":"PUBLIC OLIST / Fixed full-window cards; quarter selections do not recompute them / Unknown categories retained",
}


def create(source: Path, out: Path, extension: Path | None=None) -> Path:
    extension=extension or source
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
    receipt={"source_evidence_sha256":hashlib.sha256((source/"evidence.json").read_bytes()).hexdigest(),
             "pages":len(PAGES),"aggregate_rows":{k:len(v) for k,v in rows.items()},
             "extension_evidence_sha256":hashlib.sha256((extension/'extension_evidence.json').read_bytes()).hexdigest(),
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
        "Confidence cards refer to the full sample and do not follow monthly selections.\n\n"
        "Desktop rendering, refresh and DAX execution are unverified. "
        "Open the entire PBIP folder in a compatible Power BI Desktop installation.\n",
        encoding="utf-8")
    (project.parent/"analysis_evidence.json").write_text(json.dumps(evidence,indent=2)+"\n",encoding="utf-8")
    (project.parent/'extension_evidence.json').write_text(json.dumps(extra,indent=2)+'\n',encoding='utf-8')
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
    parser.add_argument("--package",type=Path)
    args=parser.parse_args()
    path=create(args.source,args.out,args.extension)
    if args.package: package(path,args.package)
    print(path)
