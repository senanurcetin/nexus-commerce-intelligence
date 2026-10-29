"""Evidence-based NEXUS Power BI acceptance preflight.

Checks static design/model artifacts and distinguishes those from an actual
Power BI Desktop render/refresh. NEVER upgrades a missing .pbix/.pbip into a
passed release, even when dbt CI and theme syntax pass.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DAX = (
    "Completed Item Value", "Period-Distinct Completed Orders",
    "Completed Value per Completed Order", "Revenue per Completed Purchasing User",
    "Returned Item Share", "Known-Cost Completed Item Value",
    "Known-Cost Product Contribution", "Known-Cost Product Margin Rate",
    "Completed-Value Cost Coverage", "Historical Sessions", "Historical Event Session Conversion",
)
POWERBI_SUFFIXES = {".pbix", ".pbip", ".pbit", ".pbir"}
EXPECTED_THEME = {
    "background": "#080F20",
    "foreground": "#EDF5FF",
    "tableAccent": "#47DFF2",
}


def audit(root: Path, report_file: Path | None = None) -> dict:
    theme_path = root / "powerbi" / "themes" / "nexus-commerce.json"
    dax_path = root / "docs" / "dax-measures.md"
    checks = {}
    try:
        theme = json.loads(theme_path.read_text(encoding="utf-8"))
        checks["theme_json"] = (
            all(theme.get(k) == v for k, v in EXPECTED_THEME.items())
            and len(theme.get("dataColors", [])) >= 6
            and isinstance(theme.get("visualStyles"), dict)
        )
    except (FileNotFoundError, ValueError):
        checks["theme_json"] = False

    try:
        dax_text = dax_path.read_text(encoding="utf-8")
        checks["dax_documentation"] = all(
            re.search(r"(?m)^" + re.escape(name) + r"\s*=", dax_text)
            for name in REQUIRED_DAX
        )
        qa = (root / "docs" / "POWER_BI_VISUAL_QA.md").read_text(encoding="utf-8")
        checks["dax_semantics"] = (
            "signup_traffic_source" in qa
            and "fct_marketing_web_performance.traffic_source" in qa
            and 'DIVIDE([Known-CostProductContribution],[Known-CostCompletedItemValue])' in re.sub(r'\s+','',dax_text)
            and 'RELATED(dim_products[cost])>=0' in re.sub(r'\s+','',dax_text)
        )
    except FileNotFoundError:
        checks["dax_documentation"] = checks["dax_semantics"] = False

    found = []
    if report_file is not None:
        path = Path(report_file)
        if path.exists() and (path.suffix.lower() in POWERBI_SUFFIXES or path.is_dir()):
            found.append(str(path))
    else:
        for base in (root / "powerbi", root / "reports"):
            if base.is_dir():
                found.extend(str(p) for p in base.rglob("*")
                             if p.suffix.lower() in POWERBI_SUFFIXES)
    # Shipped editable projects are inside pinned portable archives, rather than
    # committed as expanded working directories. Count only validated packages.
    if report_file is None or Path(report_file).suffix.lower()=='.zip':
        from scripts.release_audit import audit as audit_delivery
        delivery=audit_delivery(root)
        for check in delivery['checks']:
            if check['passed'] and check['name'] in {'synthetic_powerbi_archive','public_research_archive'}:
                archive=root/check['details']['file']
                if report_file is None or archive.resolve()==Path(report_file).resolve():
                    found.append(str(archive)+' (validated editable PBIP inside archive)')
    checks["editable_report_present"] = bool(found)
    # The presence of a report does not establish Desktop refresh or fidelity.
    checks["actual_desktop_render"] = False
    checks["actual_data_refresh"] = False
    checks["page_visual_acceptance"] = False
    checks["financial_reconciliation"] = False
    checks["desktop_and_mobile_qa"] = False
    return {
        "schema_version": 1,
        "release_decision": "HOLD",
        "readiness_note": (
            "Source-level Power BI design/measure preflight only; report must "
            "be opened/refreshed and its visuals verified independently in Desktop."
        ),
        "checks": checks,
        "report_candidates": found[:20],
        "open_gates": [k for k, v in checks.items() if not v],
        "source_independence": (
            "Greenweez, historical E-Commerce and Commerce Lab test GA4 "
            "are never combined into a single merchant turnover measure."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.root, args.report)
    formatted = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(formatted + "\n", encoding="utf-8")
    print(formatted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
