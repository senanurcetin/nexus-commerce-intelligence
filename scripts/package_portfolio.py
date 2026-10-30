"""Package only the public, synthetic portfolio builds with stable ZIP metadata."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from scripts.build_public_powerbi import create
from scripts.build_showcase import ROOT


def archive(folder: Path, output: Path) -> dict:
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=output.with_suffix(".zip.tmp")
    names=[]
    with ZipFile(stage,"w",compression=ZIP_DEFLATED) as handle:
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            name=path.relative_to(folder).as_posix()
            info=ZipInfo(name,date_time=(2026,1,1,0,0,0))
            info.compress_type=ZIP_DEFLATED
            info.external_attr=0o644 << 16
            handle.writestr(info,path.read_bytes())
            names.append(name)
    stage.replace(output)
    return {"file":output.name,"sha256":hashlib.sha256(output.read_bytes()).hexdigest(),
            "bytes":output.stat().st_size,"entries":len(names),"provenance":"synthetic_dbt_seeds_only"}


def package(root: Path = ROOT) -> dict:
    root=root.resolve()
    create(root)
    result={"powerbi":archive(root/"target/powerbi-public/project",root/"powerbi/NEXUS_Commerce_Demo.zip"),
            "website":archive(root/"target/showcase",root/"showcase/NEXUS_Commerce_Web_Demo.zip"),
            "desktop_render_verified":False,"browser_interaction_verified":False}
    (root/"powerbi/package-manifest.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(package(),indent=2))
