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
            ("public_title", page["title"], 20, "22px", "#EDF2F8"),
            ("public_context", "SYNTHETIC dbt DEMONSTRATION  /  Source units  /  Not trading results", 62, "11px", "#8F9BFF"),
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
    evidence = {"pages": [p["title"] for p in public_pages],
                     "exported_table_rows": {key: len(value) for key,value in rows.items()},
                     "powerbi_project": str(project),
                     "powerbi_desktop_accepted": False, "financial_claims_verified": False,
                     "portable_embedded_data": True, "provenance": "synthetic_dbt_seeds_only",
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
