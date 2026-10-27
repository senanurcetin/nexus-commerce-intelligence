"""Validate PBIP/PBIR JSON against Microsoft's published schemas.

This checks file contracts, not Power BI Desktop rendering or DAX execution.
Schema downloads are cached under gitignored target/schemas/official.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from urllib.error import HTTPError
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from jsonschema import RefResolver
from jsonschema.validators import validator_for

ROOT = Path(__file__).resolve().parents[1]


def validate(project: Path) -> int:
    cache = ROOT / "target/schemas/official"
    cache.mkdir(parents=True, exist_ok=True)
    store = {}
    def fetch(url):
        if url in store:
            return store[url]
        if urlsplit(url).hostname != "developer.microsoft.com" or not url.startswith("https://"):
            raise ValueError("Only official Microsoft HTTPS schemas are supported")
        key = hashlib.sha256(url.encode()).hexdigest()+".json"
        path = cache/key
        if not path.exists():
            try:
                with urlopen(url,timeout=25) as response:
                    body=response.read(2_000_001)
            except HTTPError as exc:
                raise ValueError(f"Microsoft schema unavailable ({exc.code}): {url}") from None
            if len(body)>2_000_000:
                raise ValueError("Unexpected schema download size")
            parsed=json.loads(body)
            path.write_text(json.dumps(parsed),encoding="utf-8")
        store[url]=json.loads(path.read_text(encoding="utf-8"))
        # Some Microsoft embedded schemas publish an $id with a dot while
        # their actual download uses a hyphen. Resolve internal refs to the
        # canonical ID without making a second request to a nonexistent URL.
        if store[url].get("$id"):
            store[store[url]["$id"]] = store[url]
        return store[url]
    count=0
    for path in sorted(project.rglob("*")):
        if path.suffix not in {".json",".pbip",".pbir",".pbism"}:
            continue
        item=json.loads(path.read_text(encoding="utf-8"))
        url=item.get("$schema")
        if not url:
            continue  # Power BI theme format uses a separate schema contract.
        schema=store.get(url) or fetch(url)
        resolver=RefResolver.from_schema(schema,store=store,handlers={"https":fetch})
        errors=list(validator_for(schema)(schema,resolver=resolver).iter_errors(item))
        if errors:
            raise ValueError(str(path.relative_to(project))+": "+errors[0].message[:300])
        count+=1
    if not count:
        raise ValueError("No Power BI schema-bearing artifacts found")
    return count


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project",type=Path,default=ROOT/"target/powerbi-public/project")
    args=parser.parse_args()
    print("Microsoft schema validation passed:",validate(args.project),"artifacts; Desktop rendering remains unverified")
