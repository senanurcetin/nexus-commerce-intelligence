"""Generate NEXUS Power BI PBIP/PBIR/TMDL from source-validated local marts.

No .pbix is required, no invented transactions, no credentials, and no
cross-merchant sales joins. Outputs under gitignored target/powerbi/ by default.

Usage:
  python -m scripts.build_powerbi
  python -m scripts.build_powerbi --root . --out target/powerbi
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

from scripts.ecommerce_marts_bridge import load_snapshot as load_ecommerce
from scripts.greenweez_bridge import load_snapshot as load_greenweez
from scripts.greenweez_sheets_observed import load_observed
from scripts.greenweez_import_audit import load_import_audit, reporting_rows
from scripts.lab_ga4_events import load_lab_snapshot
from scripts.nexus_workspace import inspect_sources

ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "NEXUS_Commerce"
BRAND_LOGO_NAME = "NEXUS_Official_Transparent_Logo_20261017.png"
BRAND_THEME_NAME = "NEXUS_Commerce_20261017.json"
SCHEMA_ROOT = "https://developer.microsoft.com/json-schemas/fabric/"
TABLES = {
    "ECommerceOrders": [
        ("date", "dateTime"), ("completed_orders", "int64"),
        ("returned_orders", "int64"), ("completed_revenue", "double"),
        ("returned_line_revenue", "double"),
    ],
    "ECommerceSessions": [
        ("date", "dateTime"), ("sessions", "int64"),
        ("converted_sessions", "int64"), ("page_view_events", "int64"),
    ],
    "GreenweezFinance": [
        ("date", "dateTime"), ("transactions", "int64"),
        ("revenue", "double"), ("operational_margin", "double"),
        ("ads_cost", "double"), ("ads_margin", "double"),
    ],
    "GreenweezOrdersObserved": [
        ("date", "dateTime"), ("order_rows", "int64"),
        ("distinct_order_ids", "int64"), ("missing_order_ids", "int64"),
        ("missing_turnover_rows", "int64"),
        ("turnover_as_stored", "double"),
    ],
    "GreenweezCampaignObserved": [
        ("date", "dateTime"), ("paid_source", "string"),
        ("campaign_rows", "int64"), ("missing_cost_rows", "int64"),
        ("cost_as_stored", "double"), ("impressions", "int64"),
        ("clicks", "int64"),
    ],
    "GreenweezImportAudit": [
        ("table_name", "string"), ("source_project", "string"),
        ("source_dataset", "string"), ("row_count", "int64"),
        ("min_date", "dateTime"), ("max_date", "dateTime"),
        ("zero_amount_values", "int64"), ("negative_amount_values", "int64"),
        ("unmatched_shipping_orders", "int64"),
        ("unmatched_refund_orders", "int64"),
        ("provenance", "string"), ("finance_verified", "string"),
    ],
    "CommerceLabEvents": [
        ("date", "dateTime"), ("event_name", "string"), ("event_count", "int64"),
    ],
    "SourceRegistry": [
        ("source", "string"), ("status", "string"), ("rows", "int64"),
        ("provenance", "string"), ("interpretation", "string"),
    ],
}
MEASURES = {
    "ECommerceOrders": {
        "Completed Order-Days": ("IF(ISEMPTY(ECommerceOrders), BLANK(), SUM(ECommerceOrders[completed_orders]))", "#,0"),
        "Completed Line Revenue (source units)": ("IF(ISEMPTY(ECommerceOrders), BLANK(), SUM(ECommerceOrders[completed_revenue]))", "#,0.00"),
        "Returned Order-Days": ("IF(ISEMPTY(ECommerceOrders), BLANK(), SUM(ECommerceOrders[returned_orders]))", "#,0"),
    },
    "ECommerceSessions": {
        "Sessions (historical)": ("IF(ISEMPTY(ECommerceSessions), BLANK(), SUM(ECommerceSessions[sessions]))", "#,0"),
        "Converted Sessions": ("IF(ISEMPTY(ECommerceSessions), BLANK(), SUM(ECommerceSessions[converted_sessions]))", "#,0"),
        "Session Conversion Rate": ("DIVIDE(SUM(ECommerceSessions[converted_sessions]), SUM(ECommerceSessions[sessions]))", "0.0%"),
    },
    "GreenweezFinance": {
        "Greenweez Revenue (source units)": ("IF(ISEMPTY(GreenweezFinance), BLANK(), SUM(GreenweezFinance[revenue]))", "#,0.00"),
        "Greenweez Ad Cost (source units)": ("IF(ISEMPTY(GreenweezFinance), BLANK(), SUM(GreenweezFinance[ads_cost]))", "#,0.00"),
        "Greenweez Margin After Ads": ("IF(ISEMPTY(GreenweezFinance), BLANK(), SUM(GreenweezFinance[ads_margin]))", "#,0.00"),
    },
    "GreenweezOrdersObserved": {
        "Source Order Rows": ("IF(ISEMPTY(GreenweezOrdersObserved), BLANK(), SUM(GreenweezOrdersObserved[order_rows]))", "#,0"),
        "Observed Turnover Only (source units)": ("IF(ISEMPTY(GreenweezOrdersObserved), BLANK(), SUM(GreenweezOrdersObserved[turnover_as_stored]))", "#,0.00"),
        "Rows Missing Turnover": ("IF(ISEMPTY(GreenweezOrdersObserved), BLANK(), SUM(GreenweezOrdersObserved[missing_turnover_rows]))", "#,0"),
        "Observed Turnover Coverage": ("DIVIDE(SUM(GreenweezOrdersObserved[order_rows]) - SUM(GreenweezOrdersObserved[missing_turnover_rows]), SUM(GreenweezOrdersObserved[order_rows]))", "0.0%"),
    },
    "GreenweezCampaignObserved": {
        "Observed Campaign Cost (source units)": ("IF(ISEMPTY(GreenweezCampaignObserved), BLANK(), SUM(GreenweezCampaignObserved[cost_as_stored]))", "#,0.00"),
        "Observed Ad Clicks": ("IF(ISEMPTY(GreenweezCampaignObserved), BLANK(), SUM(GreenweezCampaignObserved[clicks]))", "#,0"),
    },
    "CommerceLabEvents": {
        "Lab Test Events (not orders)": ("IF(ISEMPTY(CommerceLabEvents), BLANK(), SUM(CommerceLabEvents[event_count]))", "#,0"),
    },
}
# Page IDs must be stable across regenerations and compatible with PBIR.
PAGES = [
    {"id": "a48e105ce7c41997c1b0", "title": "01 · Source Assurance",
     "cards": [], "charts": [
         ("tableEx", "SourceRegistry", ["source", "status", "rows", "provenance"], None, "Independent source evidence"),
     ]},
    {"id": "b785831efa4283780c12", "title": "02 · Historical E-Commerce",
     "cards": [("ECommerceOrders", "Completed Order-Days"), ("ECommerceOrders", "Completed Line Revenue (source units)"),
               ("ECommerceOrders", "Returned Order-Days")],
     "charts": [
         ("lineChart", "ECommerceOrders", ["date"], "Completed Line Revenue (source units)", "Daily completed-line revenue"),
         ("clusteredColumnChart", "ECommerceOrders", ["date"], "Completed Order-Days", "Completed order-days (daily distinct)"),
     ]},
    {"id": "c17f944dab306796b2e9", "title": "03 · E-Commerce Sessions",
     "cards": [("ECommerceSessions", "Sessions (historical)"),
               ("ECommerceSessions", "Converted Sessions"), ("ECommerceSessions", "Session Conversion Rate")],
     "charts": [
         ("lineChart", "ECommerceSessions", ["date"], "Sessions (historical)", "Historical daily sessions"),
         ("clusteredColumnChart", "ECommerceSessions", ["date"], "Converted Sessions", "Converted sessions"),
     ]},
    {"id": "d57a999fea49118cad34", "title": "04 · Greenweez Finance",
     "cards": [("GreenweezFinance", "Greenweez Revenue (source units)"),
               ("GreenweezFinance", "Greenweez Ad Cost (source units)"),
               ("GreenweezFinance", "Greenweez Margin After Ads")],
     "charts": [
         ("lineChart", "GreenweezFinance", ["date"], "Greenweez Revenue (source units)", "Daily Greenweez finance mart revenue"),
         ("clusteredColumnChart", "GreenweezFinance", ["date"], "Greenweez Ad Cost (source units)", "Greenweez daily ads spend"),
     ]},
    {"id": "e301df9d5ea80ea43210", "title": "05 · Greenweez Source Quality",
     "cards": [("GreenweezOrdersObserved", "Observed Turnover Only (source units)"),
               ("GreenweezOrdersObserved", "Rows Missing Turnover"),
               ("GreenweezOrdersObserved", "Observed Turnover Coverage")],
     "charts": [
         ("lineChart", "GreenweezOrdersObserved", ["date"], "Observed Turnover Only (source units)", "Nonblank turnover observations only"),
         ("clusteredColumnChart", "GreenweezCampaignObserved", ["paid_source"], "Observed Campaign Cost (source units)", "Source-platform campaign cost (unverified)"),
     ]},
    {"id": "ab197ab073123077bd68", "title": "06 · Greenweez Import Evidence",
     "cards": [], "charts": [
         ("tableEx", "GreenweezImportAudit",
          ["table_name", "row_count", "min_date", "max_date",
           "zero_amount_values", "negative_amount_values",
           "unmatched_shipping_orders", "unmatched_refund_orders",
           "provenance", "finance_verified"], None,
          "BigQuery source import evidence · NOT finance-verified"),
     ]},
    {"id": "f904a7041e7d64bd021c", "title": "07 · Commerce Lab Tests",
     "cards": [("CommerceLabEvents", "Lab Test Events (not orders)")],
     "charts": [
         ("clusteredColumnChart", "CommerceLabEvents", ["event_name"], "Lab Test Events (not orders)", "Opted-in test event counts"),
     ]},
]


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_sources(root: Path) -> tuple[dict[str, list[dict]], list[dict]]:
    """Use ONLY the validated local aggregates, never reinterpret raw identifiers."""
    result: dict[str, list[dict]] = {k: [] for k in TABLES}
    ecommerce = load_ecommerce(root / "target/ecommerce_bridge/snapshot.json")
    if ecommerce:
        result["ECommerceOrders"] = ecommerce["tables"]["orders"]
        result["ECommerceSessions"] = ecommerce["tables"]["sessions"]
    greenweez = load_greenweez(root / "target/greenweez_bridge/snapshot.json")
    if greenweez:
        result["GreenweezFinance"] = [
            {k: v for k, v in row.items() if k in {f for f, _ in TABLES["GreenweezFinance"]}}
            for row in greenweez["tables"]["daily"]
        ]
    observed = load_observed(root / "target/greenweez_bridge/google_sheets_observed.json")
    if observed:
        result["GreenweezOrdersObserved"] = observed["daily_orders"]
        result["GreenweezCampaignObserved"] = observed["daily_campaigns"]
    try:
        quality = load_import_audit(
            root / "integrations/greenweez/target/gsheet_real.duckdb")
    except (ValueError, OSError, ImportError):
        # Fail closed: invalid source evidence appears as INVALID in SourceRegistry.
        quality = None
    if quality:
        result["GreenweezImportAudit"] = reporting_rows(quality)
    lab = load_lab_snapshot(root / "target/google_measurement/lab_ga4_events.json")
    if lab:
        result["CommerceLabEvents"] = lab[0]
    statuses = inspect_sources(root)
    result["SourceRegistry"] = [
        {"source": v["label"], "status": v["status"], "rows": v["rows"],
         "provenance": v["provenance"] or "none", "interpretation": v["detail"]}
        for v in statuses
    ]
    return result, statuses


def export_csv(data_dir: Path, rows: dict[str, list[dict]]) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, fields in TABLES.items():
        path = data_dir / f"{name}.csv"
        cols = [v for v, _ in fields]
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            for row in rows[name]:
                writer.writerow({c: row.get(c, "") for c in cols})
        counts[name] = len(rows[name])
    return counts


def table_tmdl(name: str, fields: list[tuple[str, str]], rows: list[dict] | None = None, *, measures: dict | None = None) -> str:
    lines = [f"table {name}", ""]
    for field, kind in fields:
        lines.extend([
            f"\tcolumn {field}",
            f"\t\tdataType: {kind}",
            "\t\tsummarizeBy: none",
            f"\t\tsourceColumn: {field}",
            "",
        ])
    for measure_name, (formula, fmt) in (MEASURES if measures is None else measures).get(name, {}).items():
        lines.extend([
            f"\tmeasure '{measure_name}' = {formula}",
            f"\t\tformatString: {fmt}",
            "",
        ])
    # A single generated parameter, regenerated for each local checkout.
    type_map = {"dateTime": "type date", "int64": "Int64.Type",
                "double": "type number", "string": "type text"}
    conversions = ", ".join('{"' + field + '", ' + type_map[kind] + "}"
                            for field, kind in fields)
    m = [
        "let",
        f'    Raw = Csv.Document(File.Contents(pDataFolder & "/{name}.csv"), '
        '[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        "    Headers = Table.PromoteHeaders(Raw, [PromoteAllScalars=true]),",
        f"    Typed = Table.TransformColumnTypes(Headers, {{{conversions}}}, \"en-US\")",
        "in",
        "    Typed",
    ]
    if rows is not None:
        def literal(value: object) -> str:
            if value is None:
                return "null"
            if isinstance(value, (int, float)):
                return json.dumps(value, allow_nan=False)
            return '"' + str(value).replace('"', '""').replace('\n', '#(lf)').replace('\r', '#(cr)') + '"'
        headers = ", ".join(literal(field) for field, _ in fields)
        values = ",\n        ".join("{" + ", ".join(literal(row.get(field)) for field, _ in fields) + "}" for row in rows)
        m = ["let", f"    Raw = #table({{{headers}}}, {{{values}}}),",
             f"    Typed = Table.TransformColumnTypes(Raw, {{{conversions}}}, \"en-US\")",
             "in", "    Typed"]
    lines += [
        f"\tpartition {name} = m",
        "\t\tmode: import",
        "\t\tsource =",
    ]
    # Every physical line of a multiline Power Query expression must remain
    # inside the TMDL partition source indentation, including embedded rows.
    lines += ["\t\t\t" + line for part in m for line in part.splitlines()]
    return "\n".join(lines) + "\n"


def _field(table: str, name: str, measure: bool) -> dict:
    if measure:
        val = {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}
    else:
        val = {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}
    return {
        "field": val,
        "queryRef": f"{table}.{name}",
        "nativeQueryRef": name,
    }


def visual_json(visual_id: str, typ: str, table: str, columns: list[str],
                measure: str | None, title: str, x: int, y: int, width: int,
                height: int, index: int) -> dict:
    if typ == "cardVisual":
        roles = {"Data": {"projections": [_field(table, measure or "", True)]}}
    elif typ == "tableEx":
        roles = {"Values": {"projections": [_field(table, col, False) for col in columns]}}
    elif typ == "pivotTable":
        if len(columns) != 2 or not measure:
            raise ValueError("Matrix requires a row, column and measure")
        roles = {"Rows": {"projections": [_field(table, columns[0], False)]},
                 "Columns": {"projections": [_field(table, columns[1], False)]},
                 "Values": {"projections": [_field(table, measure, True)]}}
    else:
        roles = {
            "Category": {"projections": [_field(table, col, False) for col in columns]},
            "Y": {"projections": [_field(table, measure or "", True)]},
        }
    title_expr = {"expr": {"Literal": {"Value": "'" + title.replace("'", "''") + "'"}}}
    return {
        "$schema": SCHEMA_ROOT + "item/report/definition/visualContainer/2.7.0/schema.json",
        "name": visual_id,
        "position": {"x": x, "y": y, "z": 1000 + index,
                     "width": width, "height": height, "tabOrder": index},
        "visual": {
            "visualType": typ,
            "query": {"queryState": roles},
            "objects": {},
            "visualContainerObjects": {
                "title": [{"properties": {
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                    "text": title_expr,
                }}],
            },
            "drillFilterOtherVisuals": True,
        },
    }


def official_logo_visual() -> dict:
    """Power BI image visual sourced from the owner's original PNG in RegisteredResources."""
    item = {
        "name": {"expr": {"Literal": {"Value": "'NEXUS Official Transparent Logo'"}}},
        "url": {"expr": {"ResourcePackageItem": {
            "PackageName": "RegisteredResources",
            "PackageType": 1,
            "ItemName": BRAND_LOGO_NAME,
        }}},
        "scaling": {"expr": {"Literal": {"Value": "'Fit'"}}},
    }
    return {
        "$schema": SCHEMA_ROOT + "item/report/definition/visualContainer/2.7.0/schema.json",
        "name": "nexus_brand_logo",
        "position": {"x": 24, "y": 14, "z": 9000, "width": 242, "height": 79, "tabOrder": 90},
        "visual": {
            "visualType": "image",
            "objects": {
                "general": [{"properties": {}}],
                "image": [{"properties": {"sourceFile": {"image": item}}}],
            },
            "visualContainerObjects": {
                "title": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}]
            },
            "drillFilterOtherVisuals": True,
        },
    }


def build_project(base: Path, data_dir: Path, *, portable_rows: dict[str, list[dict]] | None = None,
                  tables: dict | None = None, measures: dict | None = None,
                  pages: list | None = None, model_name: str = MODEL_NAME) -> Path:
    tables = TABLES if tables is None else tables
    pages = PAGES if pages is None else pages
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", model_name):
        raise ValueError("Invalid model name")
    proj_dir = base / "project"
    model = proj_dir / (model_name + ".SemanticModel")
    report = proj_dir / (model_name + ".Report")
    # One project per source dataset, no cross-dataset relationships.
    _write_json(proj_dir / (model_name + ".pbip"), {
        "$schema": SCHEMA_ROOT + "pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": model_name + ".Report"}}],
        "settings": {"enableAutoRecovery": True},
    })
    _write_json(model / "definition.pbism", {
        "$schema": SCHEMA_ROOT + "item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2",
        "settings": {"qnaEnabled": False},
    })
    (model / "definition").mkdir(parents=True, exist_ok=True)
    (model / "definition/database.tmdl").write_text(
        f"database {model_name}\n\tcompatibilityLevel: 1600\n", encoding="utf-8",
    )
    # Power Query/M strings escape double-quotes as "" (not backslashes).
    absolute = str(data_dir.resolve())
    if '"' in absolute or "\n" in absolute:
        raise ValueError("Unsafe data directory path")
    (model / "definition/model.tmdl").write_text(
        "model Model\n\tculture: en-US\n\tsourceQueryCulture: en-US\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\n"
        'expression pDataFolder = "' + absolute + '" meta '
        '[IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n',
        encoding="utf-8",
    )
    for name, fields in tables.items():
        path = model / "definition" / "tables" / f"{name}.tmdl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(table_tmdl(name, fields, None if portable_rows is None else portable_rows[name], measures=measures), encoding="utf-8")
    _write_json(report / "definition.pbir", {
        "$schema": SCHEMA_ROOT + "item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": "../" + model_name + ".SemanticModel"}},
    })
    definition = report / "definition"
    _write_json(definition / "version.json", {
        "$schema": SCHEMA_ROOT + "item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    })
    # Bundle original NEXUS assets and apply the custom theme directly.
    # This ensures the brand is visible after Desktop opens the generated PBIP,
    # instead of requiring an additional manual theme import.
    resource_dir = report / "StaticResources" / "RegisteredResources"
    resource_dir.mkdir(parents=True, exist_ok=True)
    logo_file = ROOT / "branding" / "nexus_official_transparent.png"
    theme_file = ROOT / "powerbi" / "themes" / "nexus-commerce.json"
    if not logo_file.is_file() or not theme_file.is_file():
        raise FileNotFoundError("Official NEXUS logo or report theme is missing")
    shutil.copyfile(logo_file, resource_dir / BRAND_LOGO_NAME)
    theme = json.loads(theme_file.read_text(encoding="utf-8"))
    # Power BI's registered theme name must equal the asset filename.
    theme["name"] = BRAND_THEME_NAME
    _write_json(resource_dir / BRAND_THEME_NAME, theme)
    _write_json(definition / "report.json", {
        "$schema": SCHEMA_ROOT + "item/report/definition/report/3.0.0/schema.json",
        "settings": {},
        "annotations": [],
        "themeCollection": {
            "customTheme": {
                "name": BRAND_THEME_NAME,
                "type": "RegisteredResources",
                "reportVersionAtImport": {
                    "visual": "2.7.0", "report": "3.0.0", "page": "2.1.0",
                },
            },
        },
        "resourcePackages": [{
            "name": "RegisteredResources", "type": "RegisteredResources",
            "items": [
                {"name": BRAND_THEME_NAME, "path": BRAND_THEME_NAME, "type": "CustomTheme"},
                {"name": BRAND_LOGO_NAME, "path": BRAND_LOGO_NAME, "type": "Image"},
            ],
        }],
    })
    _write_json(definition / "pages/pages.json", {
        "$schema": SCHEMA_ROOT + "item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p["id"] for p in pages],
        "activePageName": pages[0]["id"],
    })
    for page in pages:
        pid = page["id"]
        page_dir = definition / "pages" / pid
        _write_json(page_dir / "page.json", {
            "$schema": SCHEMA_ROOT + "item/report/definition/page/2.1.0/schema.json",
            "name": pid, "displayName": page["title"],
            "displayOption": "FitToPage",
            "height": 720, "width": 1280,
            "objects": {
                "background": [{"properties": {
                    "color": {"solid": {"color": {"expr": {"Literal": {"Value": "'#080F20'"}}}}},
                    "transparency": {"expr": {"Literal": {"Value": "0D"}}},
                }}],
            },
        })
        _write_json(page_dir / "visuals/nexus_brand_logo/visual.json", official_logo_visual())
        index = 0
        for n, (table, measure) in enumerate(page["cards"]):
            vid = f"{index + 1:020x}"
            _write_json(page_dir / "visuals" / vid / "visual.json",
                        visual_json(vid, "cardVisual", table, [], measure,
                                    measure, 24 + n * 420, 107, 399, 140, index))
            index += 1
        for n, (typ, table, cols, measure, title) in enumerate(page["charts"]):
            vid = f"{index + 1:020x}"
            _write_json(page_dir / "visuals" / vid / "visual.json",
                        visual_json(vid, typ, table, cols, measure, title,
                                    24 + (n % 2) * 630, 275 if page["cards"] else 115,
                                    1220 if typ in {"tableEx", "pivotTable"} else 608, 400, index))
            index += 1
    return proj_dir / (model_name + ".pbip")


def build(root: Path = ROOT, out: Path | None = None) -> dict:
    root = root.resolve()
    out = (out or root / "target/powerbi").resolve()
    rows, status = read_sources(root)
    counts = export_csv(out / "marts", rows)
    pbip = build_project(out, out / "marts")
    evidence = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_states": [{"source": v["source"], "status": v["status"],
                           "rows": v["rows"], "business_verified": False}
                          for v in status],
        "exported_table_rows": counts,
        "pages": [p["title"] for p in PAGES],
        "powerbi_project": str(pbip),
        "data_directory": str(out / "marts"),
        "powerbi_desktop_accepted": False,
        "financial_claims_verified": False,
        "statement": "PBIP pipeline generated; open/refresh in Desktop required for final acceptance.",
    }
    _write_json(out / "build_evidence.json", evidence)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    evidence = build(args.root, args.out)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
