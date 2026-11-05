"""NEXUS Commerce Intelligence | Greenweez dbt DuckDB bridge.

Source dbt project: integrations/greenweez (within the same NEXUS repository)
Reads ONLY vetted aggregate mart columns from an existing DuckDB dbt build.
Does not import raw order/customer data or assume a BigQuery connection.

Example (from NEXUS Commerce Intelligence repository root):
  pip install duckdb
  python -m scripts.greenweez_bridge --db "integrations/greenweez/target/gsheet_real.duckdb" --provenance external_unverified

Claims of independently audited/verified production origin are intentionally
not supported by this adapter. External sources remain labeled UNVERIFIED.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re

SOURCE = "greenweez_dbt_marts"
SCHEMA_VERSION = 1
PROVENANCE = frozenset(("synthetic_demo", "external_unverified"))
DEFAULT_OUTPUT = Path("target/greenweez_bridge/snapshot.json")
TABLE_COLUMNS = {
    "daily": (
        "date", "transactions", "revenue", "operational_margin",
        "ads_cost", "ads_margin", "ads_impression", "ads_clicks",
    ),
    "monthly": (
        "datemonth", "transactions", "revenue", "operational_margin",
        "ads_cost", "ads_margin", "ads_impression", "ads_clicks",
    ),
    "marketing_source": (
        "datemonth", "paid_source", "ads_cost", "impressions",
        "clicks", "cpc", "ctr", "spend_share",
    ),
    "refunds": (
        "datemonth", "orders", "revenue", "refund_amount",
        "orders_with_refund", "orders_refund_above_revenue",
        "refund_unit_verified", "net_revenue_after_refunds",
    ),
}
TABLE_NAMES = {
    "daily": "analytics_finance.finance_campaigns_day",
    "monthly": "analytics_finance.finance_campaigns_month",
    "marketing_source": "analytics_marketing.marketing_source_month",
    "refunds": "analytics_finance.finance_refunds_month",
}
REQUIRED = ("daily", "monthly")
NUMERIC = {
    "daily": frozenset(TABLE_COLUMNS["daily"]) - {"date"},
    "monthly": frozenset(TABLE_COLUMNS["monthly"]) - {"datemonth"},
    "marketing_source": frozenset(TABLE_COLUMNS["marketing_source"]) - {"datemonth", "paid_source"},
    "refunds": frozenset(TABLE_COLUMNS["refunds"]) - {"datemonth", "refund_unit_verified"},
}
WHOLE = {"transactions", "ads_impression", "ads_clicks", "impressions", "clicks", "orders", "orders_with_refund", "orders_refund_above_revenue"}
NONNEGATIVE = {"transactions", "ads_cost", "ads_impression", "ads_clicks", "impressions", "clicks", "orders", "orders_with_refund", "orders_refund_above_revenue", "refund_amount"}
RATIO = {"ctr", "spend_share"}
DECIMAL_TOLERANCE = 0.11


def _date(value: object, *, monthly: bool) -> str:
    if isinstance(value, datetime):
        if value.time().isoformat() != "00:00:00":
            raise ValueError("Expected a pure date at mart grain")
        value = value.date()
    if isinstance(value, date):
        result = value
    elif isinstance(value, str):
        result = date.fromisoformat(value)
    else:
        raise ValueError("Unexpected date type in Greenweez mart")
    if monthly and result.day != 1:
        raise ValueError("Monthly mart date must be first day of month")
    return result.isoformat()


def _number(value: object, field: str) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"Non-numeric {field} in Greenweez mart")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Nonfinite {field} in Greenweez mart")
    if field in WHOLE:
        if not number.is_integer() or number > 2**53 - 1:
            raise ValueError(f"Invalid integer count in {field}")
        number = int(number)
    if field in NONNEGATIVE and number < 0:
        raise ValueError(f"Negative {field}")
    if field in RATIO and not 0 <= number <= 1:
        raise ValueError(f"Invalid {field} ratio")
    return number


def _validate_rows(key: str, rows: list) -> list[dict]:
    if not isinstance(rows, list):
        raise ValueError(f"{key} must be a list")
    required = set(TABLE_COLUMNS[key])
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError(f"{key} unexpected field set")
        normalized = {}
        for field in TABLE_COLUMNS[key]:
            value = row[field]
            if field in ("date", "datemonth"):
                normalized[field] = _date(value, monthly=field == "datemonth")
            elif field == "paid_source":
                if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,40}", value):
                    raise ValueError("Invalid paid_source label")
                normalized[field] = value
            elif field == "refund_unit_verified":
                if not isinstance(value, bool):
                    raise ValueError("Refund verified flag must be boolean")
                normalized[field] = value
            else:
                normalized[field] = _number(value, field)
                if normalized[field] is None and field in {"transactions", "revenue", "operational_margin", "ads_cost", "ads_margin"}:
                    raise ValueError(f"Missing mandatory value {field}")
        unique_key = (
            normalized.get("date") or normalized["datemonth"],
            normalized.get("paid_source", ""),
        )
        if unique_key in seen:
            raise ValueError(f"Duplicate {key} mart grain")
        seen.add(unique_key)
        if key in ("daily", "monthly"):
            if abs(normalized["ads_margin"] - (normalized["operational_margin"] - normalized["ads_cost"])) > DECIMAL_TOLERANCE:
                raise ValueError(f"{key} ads_margin does not reconcile")
        if key == "refunds" and (
            normalized["refund_unit_verified"] or normalized["net_revenue_after_refunds"] is not None
        ):
            raise ValueError("Unverified refund amount must not yield net revenue")
        result.append(normalized)
    return sorted(result, key=lambda row: (row.get("date") or row["datemonth"], row.get("paid_source", "")))


def _reconcile(tables: dict[str, list[dict]]) -> None:
    daily_months = defaultdict(lambda: defaultdict(float))
    for item in tables["daily"]:
        prefix = item["date"][:7] + "-01"
        for col in ("transactions", "revenue", "ads_cost", "operational_margin", "ads_margin", "ads_clicks", "ads_impression"):
            if item[col] is not None:
                daily_months[prefix][col] += item[col]
    month_index = {row["datemonth"]: row for row in tables["monthly"]}
    if set(daily_months) != set(month_index):
        raise ValueError("Greenweez daily/monthly coverage mismatch")
    for key, total in daily_months.items():
        month = month_index[key]
        for col, amount in total.items():
            expected = month[col]
            if expected is None or abs(amount - expected) > DECIMAL_TOLERANCE:
                raise ValueError(f"Greenweez daily/monthly {col} fails reconciliation for {key}")
    sources = defaultdict(float)
    for row in tables["marketing_source"]:
        sources[row["datemonth"]] += row["ads_cost"]
    for month, spend in sources.items():
        if month not in month_index or abs(spend - month_index[month]["ads_cost"]) > DECIMAL_TOLERANCE:
            raise ValueError(f"Greenweez per-source spend does not reconcile for {month}")
    if not tables["daily"] or not tables["monthly"]:
        raise ValueError("Greenweez snapshot has no finance observations")


def validate_snapshot(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "source_system", "provenance", "generated_at_utc",
        "source_sha256", "tables", "row_counts",
    }:
        raise ValueError("Invalid Greenweez bridge manifest schema")
    if value["schema_version"] != SCHEMA_VERSION or value["source_system"] != SOURCE:
        raise ValueError("Unexpected Greenweez origin/schema")
    if value["provenance"] not in PROVENANCE:
        raise ValueError("Cannot claim verified or unknown Greenweez data provenance")
    if not isinstance(value["source_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["source_sha256"]):
        raise ValueError("Invalid source DB hash")
    try:
        when = datetime.fromisoformat(value["generated_at_utc"].replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValueError("Invalid generated_at_utc") from exc
    if when.tzinfo is None or when > datetime.now(timezone.utc):
        raise ValueError("Greenweez export timestamp invalid or in the future")
    tables = value["tables"]
    if not isinstance(tables, dict) or set(tables) != set(TABLE_COLUMNS):
        raise ValueError("Missing Greenweez mart dataset")
    normalized = {name: _validate_rows(name, rows) for name, rows in tables.items()}
    counts = {name: len(rows) for name, rows in normalized.items()}
    if not isinstance(value["row_counts"], dict) or value["row_counts"] != counts:
        raise ValueError("Greenweez row-count manifest mismatch")
    _reconcile(normalized)
    return {**value, "tables": normalized}


def load_snapshot(path: Path = DEFAULT_OUTPUT) -> dict | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return validate_snapshot(raw)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        raise ValueError(f"Greenweez snapshot rejected ({path.name}): {exc}") from exc


def _sha256(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as reader:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def export_from_duckdb(db: Path, dest: Path = DEFAULT_OUTPUT, provenance: str = "synthetic_demo") -> dict:
    """Read known Greenweez dbt marts from an existing local DB, never write to it."""
    if provenance not in PROVENANCE:
        raise ValueError("Source provenance must be synthetic_demo or external_unverified")
    db = db.resolve(strict=True)
    if not db.is_file():
        raise ValueError("Greenweez DuckDB source must be a file")
    import duckdb  # optional dependency; only needed when explicitly exporting
    con = duckdb.connect(str(db), read_only=True)
    try:
        existing = {(schema, table) for schema, table in con.execute(
            "select table_schema, table_name from information_schema.tables"
        ).fetchall()}
        for key in REQUIRED:
            if tuple(TABLE_NAMES[key].split(".")) not in existing:
                raise ValueError(f"Required Greenweez dbt mart missing: {TABLE_NAMES[key]}")
        tables = {}
        for key, name in TABLE_NAMES.items():
            fields = TABLE_COLUMNS[key]
            if tuple(name.split(".")) not in existing:
                tables[key] = []
                continue
            # All table names and fields are static contract-defined strings.
            cursor = con.execute(f"select {', '.join(fields)} from {name}")
            tables[key] = [dict(zip(fields, values)) for values in cursor.fetchall()]
    finally:
        con.close()
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "source_system": SOURCE,
        "provenance": provenance,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": _sha256(db),
        "tables": tables,
        "row_counts": {k: len(v) for k, v in tables.items()},
    }
    validated = validate_snapshot(snapshot)
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = dest.with_suffix(".tmp")
    staging.write_text(json.dumps(validated, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    staging.replace(dest)
    return validated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="Existing Greenweez dbt DuckDB path")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, type=Path)
    parser.add_argument("--provenance", choices=sorted(PROVENANCE), default="synthetic_demo",
                        help="External source is ALWAYS labeled unverified until independently reconciled")
    options = parser.parse_args()
    result = export_from_duckdb(options.db, options.output, options.provenance)
    print(f"Greenweez bridge: {result['provenance']}, source={SOURCE}, "
          f"daily_rows={result['row_counts']['daily']}, "
          f"monthly_rows={result['row_counts']['monthly']} (never combined with TheLook revenue)")
    print(f"Exported locally: {options.output}")


if __name__ == "__main__":
    main()
