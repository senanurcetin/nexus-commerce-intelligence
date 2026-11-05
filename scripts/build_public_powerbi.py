"""Create a portable four-page Power BI portfolio report from synthetic marts.

The semantic model embeds aggregate rows as Power Query #table literals.
Opening this PBIP requires no cloud login, absolute paths or local CSVs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from scripts.build_powerbi import build_project, read_sources, export_csv, MODEL_NAME, PAGES, SCHEMA_ROOT
from scripts.build_showcase import build as build_showcase, ROOT


def layout_public_pages(page_dir, pages):
    """Give the Commerce demo its own layout and keep its native interactions."""
    from scripts.powerbi_design import fill, literal, write

    card_labels = (
        (),
        ("Completed order-days", "Completed-line value", "Returned order-days"),
        ("Sessions", "Converted sessions", "Session conversion"),
        ("Revenue", "Advertising spend", "Contribution after ads"),
    )
    chart_titles = (
        ("Source registry",),
        ("Completed-line value by day", "Completed order-days"),
        ("Sessions by day", "Converted sessions"),
        ("Revenue by day", "Advertising spend"),
    )
    for index, page in enumerate(pages):
        folder = page_dir / page["id"] / "visuals"
        paths = {path.parent.name: path for path in folder.glob("*/visual.json")}
        visuals = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()}
        cards = sorted(
            (v for v in visuals.values() if v["visual"]["visualType"] == "cardVisual"),
            key=lambda v: v["position"]["tabOrder"],
        )
        charts = sorted(
            (v for v in visuals.values() if v["visual"].get("query")
             and v["visual"]["visualType"] not in {"cardVisual", "slicer"}),
            key=lambda v: v["position"]["tabOrder"],
        )
        logo = next(v for v in visuals.values() if v["visual"]["visualType"] == "image")
        logo["position"].update(x=1034, y=28, width=206, height=62)
        visuals["public_title"]["position"].update(x=36, y=49, width=920, height=52)
        visuals["public_context"]["position"].update(x=36, y=24, width=760, height=24)
        visuals["nexus_filter_1"]["position"].update(x=904, y=105, width=336, height=92)
        visuals["nexus_metric_note"]["position"].update(x=36, y=674, width=1204, height=38)

        scope = visuals["nexus_filter_scope"]
        scope["position"].update(x=36, y=117, width=820, height=65)
        for paragraph in scope["visual"]["objects"]["general"][0]["properties"]["paragraphs"]:
            paragraph["textRuns"][0]["textStyle"]["fontSize"] = "13px"
        if index == 0:
            charts[0]["position"].update(x=36, y=216, width=752, height=232)
            scope["position"].update(x=824, y=227, width=416, height=195)

        for card_index, card in enumerate(cards):
            width = (1204 - 20 * (len(cards) - 1)) / len(cards)
            card["position"].update(x=36 + card_index * (width + 20), y=214, width=width, height=136)
            projection = card["visual"]["query"]["queryState"]["Data"]["projections"][0]
            projection["displayName"] = card_labels[index][card_index]
            container = card["visual"]["visualContainerObjects"]
            container["title"] = [{"properties": {"show": literal(False)}}]
            container["border"] = [{"properties": {"show": literal(False)}}]
            container["padding"] = [{"properties": {
                side: literal(4) for side in ("top", "bottom", "left", "right")
            }}]

        for chart, title in zip(charts, chart_titles[index], strict=True):
            chart["visual"]["visualContainerObjects"]["title"][0]["properties"]["text"] = literal(title)
        if cards:
            charts[1]["visual"]["objects"]["dataPoint"] = [{"properties": {"defaultColor": fill("#A892F4")}}]
            for chart, (x, width) in zip(charts, ((36, 722), (778, 462)), strict=True):
                chart["position"].update(x=x, y=370, width=width, height=286)
                container = chart["visual"]["visualContainerObjects"]
                container["border"] = [{"properties": {"show": literal(False)}}]
                container["background"] = [{"properties": {
                    "show": literal(True), "color": fill("#101B30"), "transparency": literal(0)
                }}]
        for name, visual in visuals.items():
            write(paths[name], visual)


def create(root: Path = ROOT, out: Path | None = None) -> dict:
    root = root.resolve()
    out = (out or root / "target/powerbi-public").resolve()
    # The same strict synthetic-only boundary as the public website.
    build_showcase(root, root / "target/showcase")
    rows, _ = read_sources(root)
    # Only the two synthetic marts and their registry enter the public model.
    for table in rows:
        if table not in {"ECommerceOrders", "ECommerceSessions", "GreenweezFinance", "SourceRegistry"}:
            rows[table] = []
    rows["SourceRegistry"] = [row for row in rows["SourceRegistry"] if row["status"] == "synthetic"]
    for table in ("ECommerceOrders", "ECommerceSessions", "GreenweezFinance"):
        if not rows[table]:
            raise ValueError("Public report requires both complete synthetic sources")
    export_csv(out / "marts", rows)
    project = build_project(out, out / "marts", portable_rows=rows)
    # A standalone portfolio report exposes only pages backed by demo data.
    page_dir = project.parent / (MODEL_NAME + ".Report/definition/pages")
    public_pages = PAGES[:4]
    for page in PAGES[4:]:
        obsolete = (page_dir / page["id"]).resolve()
        if out not in obsolete.parents:
            raise ValueError("Generated page cleanup escaped the output directory")
        shutil.rmtree(obsolete)
    for page in public_pages:
        # Keep the public/synthetic qualification visible on every page.
        for name, text, y, size, color in (
            ("public_title", page["title"].split(" · ", 1)[-1], 49, "34px", "#EDF2F8"),
            ("public_context", "NEXUS COMMERCE   /   SYNTHETIC DATA PORTFOLIO", 24, "12px", "#8F9BFF"),
        ):
            textbox = {
                "$schema": SCHEMA_ROOT + "item/report/definition/visualContainer/2.7.0/schema.json",
                "name": name,
                "position": {"x": 290, "y": y, "z": 9500, "width": 950, "height": 34, "tabOrder": 95},
                "visual": {"visualType": "textbox", "objects": {"general": [{"properties": {
                    "paragraphs": [{"textRuns": [{"value": text, "textStyle": {
                        "fontFamily": "Segoe UI", "fontSize": size, "color": color}}]}]
                }}]}, "drillFilterOtherVisuals": True},
            }
            path = page_dir / page["id"] / "visuals" / name / "visual.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(textbox,indent=2)+"\n",encoding="utf-8")
    index = json.loads((page_dir / "pages.json").read_text(encoding="utf-8"))
    index["pageOrder"] = [page["id"] for page in public_pages]
    (page_dir / "pages.json").write_text(json.dumps(index, indent=2)+"\n", encoding="utf-8")
    # Remove the unused, machine-specific folder parameter entirely.
    model = project.parent / (MODEL_NAME + ".SemanticModel/definition/model.tmdl")
    active_tables = {"ECommerceOrders", "ECommerceSessions", "GreenweezFinance", "SourceRegistry"}
    for table_file in (model.parent / "tables").glob("*.tmdl"):
        if table_file.stem not in active_tables:
            table_file.unlink()
    model.write_text("model Model\n\tculture: en-US\n\tsourceQueryCulture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n", encoding="utf-8")
    from scripts.build_powerbi import TABLES
    from scripts.powerbi_design import apply
    configurations={
        public_pages[0]['id']:{'filters':[('SourceRegistry','source','Independent source')],
            'scope':'HOW TO READ THIS DEMO\nE-Commerce covers completed order-days and session conversion.\nGreenweez illustrates revenue, ad spend and contribution.\nThe source filter applies to the evidence table.',
            'note':'Synthetic demonstration only. Registry row counts describe exported aggregate records, not trading transactions or financial certification.'},
        public_pages[1]['id']:{'filters':[('ECommerceOrders','date','Synthetic order date')],
            'scope':'Date filters the charts and cards on this page.',
            'note':'Daily distinct orders sum to order-days, not period-unique orders. Returned-line value does not establish cash refunded.'},
        public_pages[2]['id']:{'filters':[('ECommerceSessions','date','Synthetic session date')],
            'scope':'Date filters session counts and the weighted conversion rate.',
            'note':'Converted sessions / sessions is recomputed from the selected counts. This synthetic historical denominator is separate from orders and GA4 lab events.'},
        public_pages[3]['id']:{'filters':[('GreenweezFinance','date','Synthetic finance date')],
            'scope':'Date filters the independent Greenweez illustrations.',
            'note':'Source units and documented missing-cost policies apply. Contribution after advertising is not audited net profit; unknown refund units are not subtracted.'}}
    design=apply(project,MODEL_NAME,public_pages,{t:TABLES[t] for t in active_tables},configurations)
    layout_public_pages(page_dir, public_pages)
    evidence = {"pages": [p["title"] for p in public_pages],
                     "exported_table_rows": {key: len(value) for key,value in rows.items()},
                     "powerbi_project": str(project),
                     "powerbi_desktop_accepted": False, "financial_claims_verified": False,
                     "visual_design":design,"portable_embedded_data": True, "provenance": "synthetic_dbt_seeds_only",
                     "statement": "Editable four-page portfolio report; Desktop rendering has not been verified."}
    (out / "build_evidence.json").write_text(json.dumps(evidence,indent=2)+"\n",encoding="utf-8")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = create(out=args.out)
    print(json.dumps({"pages": result["pages"], "project": result["powerbi_project"],
                      "portable_embedded_data": True},indent=2))
