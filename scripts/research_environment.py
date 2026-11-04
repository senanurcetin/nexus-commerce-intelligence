"""Record and optionally require the hash-locked Python 3.11 research environment."""
from __future__ import annotations
import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import sys

from packaging.requirements import Requirement

ROOT=Path(__file__).resolve().parents[1]
LOCK=ROOT/'requirements-research.lock'


def inspect():
    versions={};mismatches=[]
    for line in LOCK.read_text(encoding='utf-8').splitlines():
        if not line or line[0].isspace() or line.startswith('#'):continue
        req=Requirement(line.removesuffix('\\').strip())
        if req.marker and not req.marker.evaluate():continue
        expected=next(iter(req.specifier)).version
        try:actual=metadata.version(req.name)
        except metadata.PackageNotFoundError:actual=None
        versions[req.name]={'expected':expected,'installed':actual}
        if actual!=expected:mismatches.append(req.name)
    compatible=sys.version_info[:2]==(3,11)
    return {'python':platform.python_version(),'implementation':platform.python_implementation(),
        'platform':platform.system(),'python_311':compatible,
        'lock_sha256':hashlib.sha256(LOCK.read_bytes()).hexdigest(),
        'requirements_input_sha256':hashlib.sha256((ROOT/'requirements-research.in').read_bytes()).hexdigest(),
        'packages':versions,'mismatched_or_missing_packages':mismatches,
        'matches_research_lock':compatible and not mismatches,
        'scope':'Research only; does not lock dbt, dashboard, Node, .NET, OS fonts or native Power BI.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--require-lock',action='store_true');a=p.parse_args()
    result=inspect();print(json.dumps(result,indent=2))
    if a.require_lock and not result['matches_research_lock']:raise SystemExit(2)
