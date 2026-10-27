"""Build an independent portable Olist PBIP using validated PUBLIC aggregates."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
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
]
CONTEXT = {
    "olist_value":"PUBLIC OLIST / 2017–July 2018 purchase window / Item GMV excludes freight; not net revenue",
    "olist_cohorts":"PUBLIC OLIST / Retrospective delivered status / Original cohort denominator; no lifetime acquisition claim",
    "olist_segments":"PUBLIC OLIST / As of 2018-08-01 / Earlier observed purchase history included / Demonstration policy",
    "olist_decomposition":"PUBLIC OLIST / Orders × items per order × value per item / Adjacent complete purchase months",
    "olist_delivery":"PUBLIC OLIST / Customer-cluster bootstrap 95% interval / Fixed overall contrast; does not follow month filters",
}


def create(source: Path, out: Path) -> Path:
    evidence=json.loads((source/"evidence.json").read_text(encoding="utf-8"))
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
    receipt={"source_evidence_sha256":hashlib.sha256((source/"evidence.json").read_bytes()).hexdigest(),
             "pages":len(PAGES),"aggregate_rows":{k:len(v) for k,v in rows.items()},
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
        "Confidence cards refer to the full sample and do not follow monthly selections.\n\n"
        "Desktop rendering, refresh and DAX execution are unverified. "
        "Open the entire PBIP folder in a compatible Power BI Desktop installation.\n",
        encoding="utf-8")
    (project.parent/"analysis_evidence.json").write_text(json.dumps(evidence,indent=2)+"\n",encoding="utf-8")
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
    parser.add_argument("--package",type=Path)
    args=parser.parse_args()
    path=create(args.source,args.out)
    if args.package: package(path,args.package)
    print(path)
