"""Count-only operational analysis of the approved private source snapshot."""
import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import tempfile

import duckdb

from scripts.profile_core_source import load
from scripts.read_core_source import PRIVATE_ROOT, ROOT

STATUSES = ('Cancelled', 'Complete', 'Processing', 'Returned', 'Shipped')
IMPLEMENTATION = Path(__file__)


def canonical_hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def epoch(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def export_delivery_inputs(con, artifact_root, observed_epoch, source_hash, code_hash):
    """Create immutable private input and quarantine files at source item grain."""
    if not math.isfinite(observed_epoch):
        raise ValueError('Finite observation boundary required')
    artifact_root.mkdir(parents=True, exist_ok=True)
    boundary_hash = canonical_hash(float(observed_epoch))[:16]
    destination = artifact_root / (source_hash[:16] + '-' + code_hash[:16] + '-' + boundary_hash)
    con.execute('''
        create or replace temp table delivery_inputs as
        select *, case
            when not coalesce(isfinite(created) and isfinite(delivered), false)
                then 'invalid_timestamp'
            when delivered < created then 'delivery_before_creation'
            when delivered > ? then 'event_after_observation'
            else 'eligible' end as eligibility_reason
        from operation_items where status in ('Complete', 'Returned')
    ''', [observed_epoch])
    reasons = dict(con.execute('''
        select eligibility_reason, count(*) from delivery_inputs
        group by eligibility_reason order by eligibility_reason
    ''').fetchall())
    terminal = con.execute('select count(*) from delivery_inputs').fetchone()[0]
    eligible = reasons.get('eligible', 0)
    if sum(reasons.values()) != terminal:
        raise ValueError('Delivery input partition does not conserve terminal rows')
    invalid_eligible = con.execute('''
        select count(*) from delivery_inputs where eligibility_reason = 'eligible'
        and (delivered < created or delivered > ? or created is null or delivered is null)
    ''', [observed_epoch]).fetchone()[0]
    if invalid_eligible:
        raise ValueError('Invalid timestamps entered eligible delivery inputs')
    expected = {
        'source_csv_sha256': source_hash, 'implementation_sha256': code_hash,
        'observation_epoch_utc': float(observed_epoch),
        'terminal_item_rows': terminal, 'eligible_item_rows': eligible,
        'quarantined_item_rows': terminal - eligible, 'reason_counts': reasons,
        'invalid_eligible_rows': invalid_eligible, 'timestamp_imputation_applied': False,
    }
    expected_files = {
        'eligible_delivery_items.csv': eligible,
        'quarantined_delivery_items.csv': terminal - eligible,
    }
    if destination.exists():
        manifest = json.loads((destination / 'manifest.json').read_text(encoding='utf-8'))
        if any(manifest[key] != value for key, value in expected.items()):
            raise ValueError('Existing delivery input manifest differs')
        if set(manifest['files']) != set(expected_files):
            raise ValueError('Private delivery artifact set differs')
        for name, metadata in manifest['files'].items():
            if (metadata['rows'] != expected_files[name]
                    or file_hash(destination / name) != metadata['sha256']):
                raise ValueError('Private delivery artifact hash differs')
        return expected
    with tempfile.TemporaryDirectory(prefix='staging-', dir=artifact_root) as directory:
        stage = Path(directory)
        files = {}
        for name, comparison, count in (
            ('eligible_delivery_items.csv', '=', eligible),
            ('quarantined_delivery_items.csv', '!=', terminal - eligible),
        ):
            path = stage / name
            con.execute(f'''
                copy (select id, order_id, user_id, status,
                    source_created_at, source_delivered_at, created, delivered,
                    eligibility_reason from delivery_inputs
                    where eligibility_reason {comparison} 'eligible' order by id)
                to ? (header, delimiter ',')
            ''', [str(path)])
            files[name] = {'sha256': file_hash(path), 'rows': count}
        manifest = {**expected, 'files': files}
        (stage / 'manifest.json').write_text(
            json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        try:
            stage.rename(destination)
        except FileExistsError:
            return export_delivery_inputs(con, artifact_root, observed_epoch, source_hash, code_hash)
    return expected


def analyze(con, observed_epoch):
    """Keep current-status composition and timestamp eligibility at item grain."""
    keys = con.execute('''
        select count(*), count(id), count(distinct id)
        from "ecommerce.order_items"
    ''').fetchone()
    if not keys[0] or len(set(keys)) != 1:
        raise ValueError('Unique nonempty source item keys required')
    con.execute('''
        create or replace temp table operation_items as
        select id, order_id, user_id, created_at as source_created_at,
            delivered_at as source_delivered_at,
            case when status in ('Cancelled','Complete','Processing','Returned','Shipped')
                 then status else 'Unknown' end as status,
            try_cast(created_at as double) as created,
            try_cast(delivered_at as double) as delivered
        from "ecommerce.order_items"
    ''')
    records = con.execute('''
        select status, count(*) as item_rows,
            count(*) filter(where isfinite(delivered) and isfinite(created)
                and delivered < created) as reversed_delivery_rows,
            count(*) filter(where status in ('Complete','Returned')) as terminal_item_rows,
            count(*) filter(where status in ('Complete','Returned')
                and isfinite(created) and isfinite(delivered)
                and created <= delivered and delivered <= ?) as duration_eligible_rows
        from operation_items group by status order by status
    ''', [observed_epoch]).fetchall()
    statuses = [dict(zip(('status', 'item_rows', 'reversed_delivery_rows',
                         'terminal_item_rows', 'duration_eligible_rows'), row)) for row in records]
    grain = con.execute('''
        with grouped as (
            select order_id, count(distinct status) as states,
                count(distinct user_id) as customers,
                count(*) filter(where user_id is null) as missing_customer_rows
            from operation_items where order_id is not null group by order_id
        )
        select count(*), count(*) filter(where states > 1),
            count(*) filter(where customers != 1 or missing_customer_rows > 0)
        from grouped
    ''').fetchone()
    missing = con.execute('select count(*) from operation_items where order_id is null').fetchone()[0]
    return {
        'item_rows': keys[0], 'distinct_order_keys': grain[0],
        'mixed_status_orders': grain[1], 'ambiguous_customer_orders': grain[2],
        'missing_order_key_item_rows': missing, 'status_counts': statuses,
        'terminal_item_rows': sum(r['terminal_item_rows'] for r in statuses),
        'duration_eligible_rows': sum(r['duration_eligible_rows'] for r in statuses),
        'reversed_delivery_rows': sum(r['reversed_delivery_rows'] for r in statuses),
    }


def raw_control(path, observed_epoch):
    counts = Counter()
    with path.open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            status = row['status'] if row['status'] in STATUSES else 'Unknown'
            counts[status, 'item_rows'] += 1
            created, delivered = epoch(row['created_at']), epoch(row['delivered_at'])
            if created is not None and delivered is not None and delivered < created:
                counts[status, 'reversed_delivery_rows'] += 1
            if status in ('Complete', 'Returned'):
                counts[status, 'terminal_item_rows'] += 1
                if created is not None and delivered is not None and created <= delivered <= observed_epoch:
                    counts[status, 'duration_eligible_rows'] += 1
    return counts


def validate(result, source):
    if (result['snapshot_observed_at_utc'] != source['observed_at_utc']
            or result['provenance'] != source['origin_classification']
            or result['source_contract_sha256'] != source['source_contract_sha256']):
        raise ValueError('Operational source snapshot differs')
    if result['financial_amounts_published'] or result['raw_identifiers_published']:
        raise ValueError('Operational publication boundary differs')
    if result['independent_raw_counts_reconciled'] is not True:
        raise ValueError('Independent operational count control required')
    if result['source_item_rows'] != source['tables']['ecommerce.order_items']['rows']:
        raise ValueError('Operational source population differs')
    summary = result['summary']
    if summary['item_rows'] != result['source_item_rows']:
        raise ValueError('Operational item denominator differs')
    for field in ('item_rows', 'terminal_item_rows', 'duration_eligible_rows', 'reversed_delivery_rows'):
        if sum(row[field] for row in summary['status_counts']) != summary[field]:
            raise ValueError('Status counts fail conservation')
    if not 0 <= summary['duration_eligible_rows'] <= summary['terminal_item_rows'] <= summary['item_rows']:
        raise ValueError('Invalid duration population')
    if result['decision']['repair_chronology'] != (summary['reversed_delivery_rows'] > 0):
        raise ValueError('Chronology decision differs from evidence')
    if result['summary_sha256'] != canonical_hash(summary):
        raise ValueError('Operational summary hash differs')
    inputs = result['delivery_inputs']
    if (inputs['terminal_item_rows'] != summary['terminal_item_rows']
            or inputs['eligible_item_rows'] != summary['duration_eligible_rows']
            or inputs['eligible_item_rows'] + inputs['quarantined_item_rows'] != inputs['terminal_item_rows']
            or sum(inputs['reason_counts'].values()) != inputs['terminal_item_rows']
            or inputs['invalid_eligible_rows'] != 0):
        raise ValueError('Private delivery input acceptance differs')


def build(snapshot):
    code_hash = hashlib.sha256(IMPLEMENTATION.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    with duckdb.connect() as con:
        receipt = load(con, snapshot)
        observed = datetime.fromisoformat(receipt['observed_at_utc']).timestamp()
        summary = analyze(con, observed)
        control = raw_control(snapshot / 'ecommerce.order_items.csv', observed)
        for row in summary['status_counts']:
            for field in ('item_rows', 'terminal_item_rows', 'duration_eligible_rows', 'reversed_delivery_rows'):
                if row[field] != control[row['status'], field]:
                    raise ValueError('Independent CSV control differs')
        delivery_inputs = export_delivery_inputs(
            con, PRIVATE_ROOT / 'derived_operations', observed,
            receipt['tables']['ecommerce.order_items']['csv_sha256'], code_hash)
    item_path = snapshot / 'ecommerce.order_items.csv'
    with item_path.open('rb') as stream:
        final_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    if final_hash != receipt['tables']['ecommerce.order_items']['csv_sha256']:
        raise ValueError('Source changed during operational analysis')
    if code_hash != hashlib.sha256(IMPLEMENTATION.read_bytes().replace(b'\r\n', b'\n')).hexdigest():
        raise ValueError('Operational implementation changed during build')
    result = {
        'schema_version': 1,
        'provenance': receipt['origin_classification'],
        'snapshot_observed_at_utc': receipt['observed_at_utc'],
        'source_item_rows': receipt['tables']['ecommerce.order_items']['rows'],
        'source_contract_sha256': receipt['contract_sha256'],
        'source_csv_sha256': receipt['tables']['ecommerce.order_items']['csv_sha256'],
        'implementation_sha256': code_hash,
        'summary': summary, 'summary_sha256': canonical_hash(summary),
        'delivery_inputs': delivery_inputs,
        'independent_raw_counts_reconciled': True,
        'decision': {
            'repair_chronology': summary['reversed_delivery_rows'] > 0,
            'action': 'Investigate delivery-before-creation rows using source event definitions and lineage.',
            'duration_eligibility': 'Complete or Returned item with finite creation/delivery epochs, creation <= delivery <= snapshot observation.',
            'grain_acceptance': 'One source item per key. Distinct orders reported separately. Mixed status/customer orders require investigation.',
            'success_criterion': 'Every terminal item belongs to eligible inputs or quarantine. Eligible inputs contain zero invalid duration records. Review quarantined records against authoritative source event definitions.',
            'business_effect_evaluation': 'Measure any operational intervention on new observations with an approved loss budget.',
        },
        'financial_amounts_published': False, 'raw_identifiers_published': False,
        'original_business_origin_verified': False, 'historical_status_availability_verified': False,
    }
    if summary['item_rows'] != result['source_item_rows']:
        raise ValueError('Source item count differs')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'docs/core-source/operations.json')
    args = parser.parse_args()
    snapshot = PRIVATE_ROOT / json.loads((PRIVATE_ROOT / 'latest.json').read_text())['snapshot']
    result = build(snapshot)
    out = args.out.resolve()
    if PRIVATE_ROOT.resolve() == out or PRIVATE_ROOT.resolve() in out.parents:
        parser.error('Public receipt output must be outside private source files')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'item_rows': result['summary']['item_rows'],
                      'reversed_delivery_rows': result['summary']['reversed_delivery_rows']}))


if __name__ == '__main__':
    main()
