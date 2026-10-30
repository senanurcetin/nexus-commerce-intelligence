"""Build a public, offline portfolio from explicitly synthetic dbt aggregates only.

External snapshots are deliberately rejected. No cloud queries or credentials.
Run after the two dbt builds and scripts.nexus_workspace import.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from scripts.ecommerce_marts_bridge import load_snapshot as load_ecommerce
from scripts.greenweez_bridge import load_snapshot as load_greenweez

ROOT = Path(__file__).resolve().parents[1]


def build(root: Path = ROOT, out: Path | None = None) -> dict:
    root = Path(root).resolve()
    out = (out or root / "target/showcase").resolve()
    ecommerce = load_ecommerce(root / "target/ecommerce_bridge/snapshot.json")
    greenweez = load_greenweez(root / "target/greenweez_bridge/snapshot.json")
    if not ecommerce or not greenweez:
        raise ValueError("Build and import both synthetic dbt projects first")
    if ecommerce["provenance"] != "synthetic_ci" or greenweez["provenance"] != "synthetic_demo":
        raise ValueError("Public showcase accepts synthetic provenance only; external data rejected")
    # Allow-list fields explicitly. No identifiers, customer details or account data.
    payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": "Synthetic dbt demonstration · not trading results",
        "sources": {
            "ecommerce": {"label": "Historical E-Commerce", "origin": ecommerce["provenance"],
                          "orders": ecommerce["tables"]["orders"],
                          "sessions": ecommerce["tables"]["sessions"]},
            "greenweez": {"label": "Greenweez Finance", "origin": greenweez["provenance"],
                          "daily": greenweez["tables"]["daily"],
                          "channels": greenweez["tables"]["marketing_source"]},
        },
    }
    # Finish validation/serialization before touching the previous build.
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    if out == root or root in out.parents and out == root / "showcase":
        raise ValueError("Output must not overwrite showcase sources")
    out.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "styles.css", "app.mjs", "metrics.mjs"):
        shutil.copyfile(ROOT / "showcase" / name, out / name)
    shutil.copyfile(ROOT / "branding/nexus_official_transparent.png", out / "nexus-logo.png")
    shutil.copyfile(ROOT / "storefront/favicon.svg", out / "favicon.svg")
    stage = out / "data.json.tmp"
    stage.write_text(encoded, encoding="utf-8")
    stage.replace(out / "data.json")
    return {"output": str(out), "provenance": payload["provenance"],
            "ecommerce_days": len(ecommerce["tables"]["orders"]),
            "greenweez_days": len(greenweez["tables"]["daily"])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.root, args.out), indent=2))


if __name__ == "__main__":
    main()
