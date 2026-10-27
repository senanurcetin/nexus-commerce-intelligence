"""Rebuild the portfolio locally: dbt -> validated marts -> analysis -> web + BI.

No browser, cloud credentials or hosted jobs. Dependencies must be installed.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deps", action="store_true", help="Download pinned dbt-utils packages first")
    parser.add_argument("--skip-dbt", action="store_true", help="Reuse already built local dbt databases")
    args = parser.parse_args()
    dbt = shutil.which("dbt")
    if not dbt and not args.skip_dbt:
        raise SystemExit("Install the pinned analysis dependencies first: pip install -r requirements-dev.txt")
    env = {**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    def call(command: list[str], cwd: Path = ROOT):
        subprocess.run(command, cwd=cwd, env=env, check=True)
    if not args.skip_dbt:
        for folder in (ROOT, ROOT / "integrations/greenweez"):
            profile = ["--profiles-dir", ".github/dbt-profiles"]
            if args.deps:
                call([dbt,"deps",*profile],folder)
            call([dbt,"seed",*profile],folder)
            # Source tests refer to external BigQuery catalogues. Local seed
            # contracts and model-level tests run separately and remain offline.
            call([dbt,"build",*profile,"--exclude","resource_type:seed","source:*"],folder)
    call([sys.executable,"-m","scripts.ecommerce_marts_bridge","--db","target/ci.duckdb","--provenance","synthetic_ci"])
    call([sys.executable,"-m","scripts.greenweez_bridge","--db","integrations/greenweez/target/ci.duckdb","--provenance","synthetic_demo"])
    call([sys.executable,"-m","scripts.run_analysis"])
    call([sys.executable,"-m","scripts.build_public_powerbi"])
    print("Built: target/analysis/REPORT.md, target/showcase/, target/powerbi-public/project/")


if __name__ == "__main__":
    main()
