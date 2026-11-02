"""Private whole-snapshot availability history; no cloud calls or backdated reads.

Registration is a conservative local availability boundary, not historical source
ingestion time. Integrity hashes do not authenticate a hostile local writer.
"""
from __future__ import annotations
import argparse
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from scripts.read_core_source import ROOT,PRIVATE_ROOT,CONTRACT

ZERO='0'*64


def utc(value):
    try:stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError,AttributeError):raise ValueError('An explicit timezone-aware ISO timestamp is required') from None
    if stamp.tzinfo is None or stamp.utcoffset() is None:raise ValueError('Timestamp timezone is required')
    return stamp.astimezone(timezone.utc).isoformat(timespec='microseconds')


def now():return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode('utf-8')


def digest(value):return hashlib.sha256(encoded(value)).hexdigest()


def private(path):
    path=Path(path).resolve();root=PRIVATE_ROOT.resolve()
    if root not in path.parents:raise ValueError('History and raw snapshots must remain under ignored target/core_source')
    return path


def database(path=None):return private(path or PRIVATE_ROOT/'history.sqlite3')


def validate_snapshot(snapshot):
    snapshot=private(snapshot)
    raw=(snapshot/'receipt.json').read_bytes();receipt=json.loads(raw)
    if receipt.get('storage_read_api_used') is not False:raise ValueError('Unexpected source transport')
    if receipt.get('origin_classification')!=json.loads(CONTRACT.read_text())['origin_classification']:
        raise ValueError('Unexpected source provenance')
    # Reuse the existing fixed-contract, file-hash, projection and row-count controls.
    import duckdb
    from scripts.profile_core_source import load
    with closing(duckdb.connect()) as con:load(con,snapshot)
    if (snapshot/'receipt.json').read_bytes()!=raw:raise ValueError('Snapshot receipt changed during validation')
    return hashlib.sha256(raw).hexdigest(),receipt


def read_entries(con):
    if con.execute('pragma user_version').fetchone()[0]!=1:raise ValueError('Unsupported availability history version')
    entries=[];previous=ZERO;last_time=None
    for seq,identifier,available,payload,checksum in con.execute('select sequence,snapshot_id,available_at,entry_json,entry_hash from snapshots order by sequence'):
        p=json.loads(payload)
        if (p['sequence']!=seq or seq!=len(entries)+1 or p['snapshot_id']!=identifier
            or p['available_at_utc']!=available or p['previous_entry_sha256']!=previous or digest(p)!=checksum):
            raise ValueError('Availability history integrity failed')
        observed=utc(p['source_observed_at_utc']);registered=utc(p['registered_at_utc'])
        if (registered!=available or registered!=utc(available) or observed!=p['source_observed_at_utc']
            or observed>registered or (last_time is not None and available<last_time)):
            raise ValueError('Availability history chronology failed')
        entries.append(dict(p,entry_sha256=checksum));previous=checksum;last_time=available
    return entries


def history(path=None,anchor=None):
    path=database(path)
    if not path.exists():entries=[]
    else:
        with closing(sqlite3.connect(path)) as con:
            con.execute('pragma query_only=on');entries=read_entries(con)
    if anchor is not None:
        count=anchor['entries']
        if type(count) is not int or count<1 or len(entries)<count or entries[count-1]['entry_sha256']!=anchor['head_sha256']:
            raise ValueError('Published availability anchor does not match local history')
    return entries


def register(snapshot,path=None):
    snapshot=private(snapshot);identifier,receipt=validate_snapshot(snapshot)
    observed=utc(receipt['observed_at_utc']);registered=utc(now())
    if observed>registered:raise ValueError('A future source observation cannot be registered')
    path=database(path);path.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(path,isolation_level=None,timeout=15)) as con:
        con.execute('begin immediate')
        try:
            version=con.execute('pragma user_version').fetchone()[0]
            if version==0:
                if con.execute("select count(*) from sqlite_master where type='table'").fetchone()[0]:
                    raise ValueError('Unsupported existing history database')
                con.execute('create table snapshots(sequence integer primary key,snapshot_id text unique not null,available_at text not null,entry_json text not null,entry_hash text not null)')
                con.execute('create index snapshot_availability on snapshots(available_at,sequence)')
                con.execute('pragma user_version=1')
            entries=read_entries(con)
            existing=next((e for e in entries if e['snapshot_id']==identifier),None)
            relative=snapshot.relative_to(PRIVATE_ROOT.resolve()).as_posix()
            if existing:
                if existing['snapshot_directory']!=relative:raise ValueError('Same receipt already registered at another private directory')
                con.execute('commit');return existing
            if entries and registered<entries[-1]['available_at_utc']:raise ValueError('Local clock precedes the registered availability history')
            p={'sequence':len(entries)+1,'snapshot_id':identifier,'snapshot_directory':relative,
                'source_observed_at_utc':observed,'registered_at_utc':registered,'available_at_utc':registered,
                'source_contract_sha256':receipt['contract_sha256'],
                'previous_entry_sha256':entries[-1]['entry_sha256'] if entries else ZERO,
                'tables':{a:{'rows':t['rows'],'csv_sha256':t['csv_sha256']} for a,t in receipt['tables'].items()},
                'policy':'Available only from local registration; business/source modification timestamps do not backdate availability.'}
            checksum=digest(p)
            con.execute('insert into snapshots values(?,?,?,?,?)',(p['sequence'],identifier,registered,encoded(p).decode(),checksum))
            con.execute('commit');return dict(p,entry_sha256=checksum)
        except Exception:
            con.execute('rollback');raise


def resolve_as_of(at,path=None,anchor=None):
    cutoff=utc(at)
    # Inclusive: a version becomes eligible at its recorded local availability time.
    eligible=[e for e in history(path,anchor) if e['available_at_utc']<=cutoff]
    if not eligible:return None
    chosen=eligible[-1];snapshot=private(PRIVATE_ROOT/chosen['snapshot_directory'])
    identifier,receipt=validate_snapshot(snapshot)
    if identifier!=chosen['snapshot_id'] or receipt['contract_sha256']!=chosen['source_contract_sha256']:
        raise ValueError('Selected snapshot differs from its registered receipt')
    if {a:{'rows':t['rows'],'csv_sha256':t['csv_sha256']} for a,t in receipt['tables'].items()}!=chosen['tables']:
        raise ValueError('Selected source population differs from registered history')
    return snapshot,chosen


def require_as_of(at,path=None,anchor=None):
    selected=resolve_as_of(at,path,anchor)
    if selected is None:raise ValueError('No registered snapshot was available at the requested cutoff; latest-snapshot fallback is forbidden')
    return selected


def public_status(path=None):
    entries=history(path)
    return {'schema_version':1,'entries':len(entries),'head_sha256':entries[-1]['entry_sha256'] if entries else ZERO,
        'earliest_available_at_utc':entries[0]['available_at_utc'] if entries else None,
        'latest_available_at_utc':entries[-1]['available_at_utc'] if entries else None,
        'available_from_registration_only':True,'historical_business_time_backfill_allowed':False,
        'source_ingestion_times_verified':False,'transactional_source_snapshot_verified':False,
        'current_business_validity_verified':False,'raw_rows_published':False,'financial_amounts_published':False,
        'limitations':'Local integrity/selection control, not authenticated original source ingestion history. Entirely rewritten or truncated history needs an independent previously published anchor to detect.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    registration=sub.add_parser('register');registration.add_argument('--snapshot',type=Path)
    selection=sub.add_parser('as-of');selection.add_argument('--at',required=True);selection.add_argument('--require',action='store_true')
    audit=sub.add_parser('audit');audit.add_argument('--anchor',type=Path);audit.add_argument('--out',type=Path)
    args=p.parse_args()
    try:
        if args.action=='register':
            source=args.snapshot or PRIVATE_ROOT/json.loads((PRIVATE_ROOT/'latest.json').read_text())['snapshot']
            e=register(source);result={'registered':True,'sequence':e['sequence'],'available_at_utc':e['available_at_utc'],'source_observed_at_utc':e['source_observed_at_utc']}
        elif args.action=='as-of':
            selected=require_as_of(args.at) if args.require else resolve_as_of(args.at)
            result={'cutoff_utc':utc(args.at),'availability':'available' if selected else 'unavailable','latest_fallback_used':False}
            if selected:result.update(sequence=selected[1]['sequence'],available_at_utc=selected[1]['available_at_utc'])
        else:
            if args.anchor:history(anchor=json.loads(args.anchor.read_text()))
            result=public_status()
            if args.out:args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2))
    except (ValueError,OSError,KeyError,sqlite3.DatabaseError) as error:
        print('Availability control blocked: '+str(error));raise SystemExit(2)
