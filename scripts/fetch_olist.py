"""Fetch four official public Olist inputs with an authenticated Kaggle CLI.

No cloud warehouse query, paid resource or browser access. All downloads are
kept in ignored target/olist. Existing source CSVs are preserved.
"""
from pathlib import Path
import argparse
import subprocess
import zipfile

from scripts.advanced_olist import FILES, ROOT


def fetch(*, products: bool=False) -> None:
    folder=ROOT/'target/olist'
    raw=folder/'raw'
    raw.mkdir(parents=True,exist_ok=True)
    subprocess.run(['kaggle','datasets','metadata','olistbr/brazilian-ecommerce','-p',str(folder)],check=True)
    filenames=[filename for filename,_ in FILES.values()]
    if products: filenames+=['olist_products_dataset.csv','product_category_name_translation.csv']
    for filename in filenames:
        if (raw/filename).exists():
            continue
        subprocess.run(['kaggle','datasets','download','-d','olistbr/brazilian-ecommerce',
                        '-f',filename,'-p',str(raw),'--quiet'],check=True)
        if not (raw/filename).exists():
            with zipfile.ZipFile(raw/(filename+'.zip')) as archive:
                members=[member for member in archive.infolist() if not member.is_dir()]
                if len(members)!=1 or members[0].filename!=filename:
                    raise ValueError('Unexpected source archive member')
                with archive.open(members[0]) as source, (raw/filename).open('xb') as destination:
                    import shutil
                    shutil.copyfileobj(source,destination)
    print(f'{len(filenames)} official source CSVs available under target/olist/raw; no raw rows printed.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--products',action='store_true',help='Also download products and category translation')
    fetch(products=parser.parse_args().products)
