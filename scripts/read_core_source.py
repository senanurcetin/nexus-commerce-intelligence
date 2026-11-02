"""Bounded read-only warehouse snapshot through REST tabledata.list, never SQL.

Only pinned source aliases and a non-PII field allowlist are accepted. Raw rows
stay under ignored target/. No query/extract job, Storage Read API, mutation or
service-account key is used. Existing query byte caps are not changed.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import tempfile
from urllib.error import HTTPError,URLError
from urllib.parse import urlencode
from urllib.request import Request,urlopen

from scripts.cloud_source_readiness import PINNED
from scripts.ecommerce_bigquery_preflight import token

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/'contracts/core_source_read.json'
PRIVATE_ROOT=ROOT/'target/core_source'
API='https://bigquery.googleapis.com/bigquery/v2'
MAX_BYTES=100_000_000
MAX_ROWS=250_000
FINGERPRINT=('etag','lastModifiedTime','numRows','schema','type')


def fingerprint(meta):
    return hashlib.sha256(json.dumps({k:meta.get(k) for k in FINGERPRINT},sort_keys=True).encode()).hexdigest()


class RestReader:
    def __init__(self,access_token,maximum_bytes=MAX_BYTES):
        if type(maximum_bytes) is not int or not 1<=maximum_bytes<=MAX_BYTES:raise ValueError('Response cap must not exceed 100 MB')
        self._token=access_token;self.maximum_bytes=maximum_bytes;self.bytes_read=0;self.requests=0

    def get(self,path,params=None):
        # There is deliberately no arbitrary URL, POST, jobs or Storage endpoint.
        allowed={source_path(alias)+suffix for alias in json.loads(CONTRACT.read_text())['tables'] for suffix in ('','/data')}
        if path not in allowed:
            raise ValueError('Only fixed BigQuery table GET paths are accepted')
        if path.endswith('/data'):
            contract=json.loads(CONTRACT.read_text())
            alias=next(a for a in contract['tables'] if path==source_path(a)+'/data')
            selected=(params or {}).get('selectedFields','').split(',')
            size=(params or {}).get('maxResults')
            if (not params or set(params)-{'selectedFields','maxResults','pageToken'}
                or len(selected)!=len(set(selected)) or set(selected)!=set(contract['tables'][alias])
                or type(size) is not int or not 1<=size<=10000):
                raise ValueError('Only the approved field projection and bounded page size are accepted')
        elif params:raise ValueError('Metadata GET parameters are fixed')
        url=API+path+('?' + urlencode(params) if params else '')
        remaining=self.maximum_bytes-self.bytes_read
        if remaining<=0:raise ValueError('Response-byte budget exhausted')
        req=Request(url,headers={'Authorization':'Bearer '+self._token,'Accept':'application/json'},method='GET')
        try:
            with urlopen(req,timeout=30) as response:raw=response.read(remaining+1)
        except HTTPError as e:raise RuntimeError('Source table GET returned HTTP '+str(e.code)) from None
        except URLError:raise RuntimeError('Source table GET connection failed') from None
        self.bytes_read+=len(raw);self.requests+=1
        if self.bytes_read>self.maximum_bytes:raise ValueError('Source response-byte budget exceeded')
        result=json.loads(raw)
        if not isinstance(result,dict):raise ValueError('Unexpected table API response')
        return result


def source_path(alias):
    domain,name=alias.split('.',1)
    source=PINNED['ecommerce' if domain=='ecommerce' else 'greenweez_gsheet']
    if alias not in json.loads(CONTRACT.read_text())['tables']:raise ValueError('Unapproved source table')
    return f'/projects/{source[0]}/datasets/{source[1]}/tables/{name}'


def fields_for(meta,approved):
    if meta.get('type')!='TABLE' or int(meta.get('numRows',-1))<0 or not meta.get('etag') or not meta.get('lastModifiedTime'):
        raise ValueError('Stable ordinary-table metadata required')
    fields=meta.get('schema',{}).get('fields',[])
    chosen=[f for f in fields if f.get('name') in approved]
    if {f.get('name') for f in chosen}!=set(approved):raise ValueError('Required source columns are missing')
    if any(f.get('mode')=='REPEATED' or f.get('type') not in {'STRING','INTEGER','FLOAT','NUMERIC','BIGNUMERIC','DATE','DATETIME','TIMESTAMP','BOOLEAN'} for f in chosen):
        raise ValueError('Only approved scalar columns can be read')
    return chosen  # Preserve source schema order and request that exact order.


def read_table(reader,path,meta,fields,output,maximum_rows=MAX_ROWS,page_rows=10000):
    expected=int(meta['numRows'])
    if type(page_rows) is not int or not 1<=page_rows<=10000:raise ValueError('Page size must be between 1 and 10000')
    if type(maximum_rows) is not int or not 1<=maximum_rows<=MAX_ROWS or expected>maximum_rows:raise ValueError('Source table exceeds the row budget')
    names=[f['name'] for f in fields];count=0;cursor=None;seen=set();pages=0
    with output.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream,lineterminator='\n');writer.writerow(names)
        while True:
            params={'selectedFields':','.join(names),'maxResults':page_rows}
            if cursor:params['pageToken']=cursor
            result=reader.get(path+'/data',params)
            if int(result.get('totalRows',-1))!=expected:raise ValueError('Source row count changed during pagination')
            rows=result.get('rows',[])
            if not isinstance(rows,list):raise ValueError('Invalid source rows')
            if count+len(rows)>expected or count+len(rows)>maximum_rows:raise ValueError('Source pagination exceeded its declared population')
            for row in rows:
                if not isinstance(row,dict):raise ValueError('Unexpected source row shape')
                cells=row.get('f',[])
                if len(cells)!=len(fields) or any(not isinstance(c,dict) or set(c)!={'v'} or isinstance(c['v'],(dict,list)) for c in cells):
                    raise ValueError('Unexpected source row shape')
                writer.writerow([c['v'] for c in cells])
            count+=len(rows);pages+=1;next_cursor=result.get('pageToken')
            if not next_cursor:break
            if not rows or next_cursor in seen:raise ValueError('Empty or repeated source pagination cursor')
            seen.add(next_cursor);cursor=next_cursor
    if count!=expected:raise ValueError('Source pagination ended before all rows were read')
    return {'rows':count,'pages':pages,'columns':fields,'csv_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'source_metadata_sha256':fingerprint(meta),'source_last_modified_ms':meta['lastModifiedTime']}


def snapshot(reader,out:Path=PRIVATE_ROOT,contract_path:Path=CONTRACT):
    out=out.resolve();private=PRIVATE_ROOT.resolve()
    if out!=private and private not in out.parents:raise ValueError('Raw snapshots must remain under ignored target/core_source')
    contract=json.loads(contract_path.read_text(encoding='utf-8'))
    canonical=json.loads(CONTRACT.read_text(encoding='utf-8'))
    if contract!=canonical or contract['query_jobs_allowed'] is not False or contract['storage_read_api_allowed'] is not False:
        raise ValueError('Only the fixed no-query source contract is accepted')
    out.mkdir(parents=True,exist_ok=True)
    before={};schemas={}
    for alias,approved in contract['tables'].items():
        meta=reader.get(source_path(alias));schemas[alias]=fields_for(meta,approved)
        if int(meta['numRows'])>contract['maximum_rows_per_table']:raise ValueError('Source population exceeds the contract')
        before[alias]=meta
    with tempfile.TemporaryDirectory(prefix='.snapshot-',dir=out) as directory:
        stage=Path(directory);tables={}
        for alias in contract['tables']:
            tables[alias]=read_table(reader,source_path(alias),before[alias],schemas[alias],stage/(alias+'.csv'),
                                     contract['maximum_rows_per_table'],contract['page_rows'])
        for alias in contract['tables']:
            if fingerprint(before[alias])!=fingerprint(reader.get(source_path(alias))):raise ValueError('Source changed; refusing a mixed-version snapshot')
        receipt={'schema_version':1,'status':'complete_observed_snapshot','observed_at_utc':datetime.now(timezone.utc).isoformat(),
            'origin_classification':contract['origin_classification'],'query_jobs_created':0,'storage_read_api_used':False,
            'maximum_response_bytes':MAX_BYTES,'response_bytes':reader.bytes_read,'api_get_requests':reader.requests,
            'contract_sha256':hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),'tables':tables,
            'publication_allowed':False,'currency_verified':False,'refund_meaning_verified':False,
            'note':'Authenticated source observation, not independently certified real business truth. Events and personal user tables were not read.'}
        # A fresh content directory is committed before updating the local pointer.
        name='snapshot-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');destination=out/name;destination.mkdir()
        for file in stage.iterdir():file.replace(destination/file.name)
        (destination/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        pointer=out/'latest.json.staging';pointer.write_text(json.dumps({'snapshot':name})+'\n',encoding='utf-8');pointer.replace(out/'latest.json')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=PRIVATE_ROOT);args=p.parse_args()
    try:
        receipt=snapshot(RestReader(token()),args.out)
        print(json.dumps({'status':receipt['status'],'tables':{k:v['rows'] for k,v in receipt['tables'].items()},
                          'response_bytes':receipt['response_bytes'],'query_jobs_created':0,'public_snapshot_changed':False},indent=2))
    except (OSError,ValueError,RuntimeError,KeyError) as error:
        print('Source snapshot unavailable: '+str(error));raise SystemExit(2)
