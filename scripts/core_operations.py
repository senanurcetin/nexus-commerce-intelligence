"""Count-only operational analysis of the approved private source snapshot."""
import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

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
        select id, order_id, user_id,
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


def build(snapshot):
    with duckdb.connect() as con:
        receipt = load(con, snapshot)
        observed = datetime.fromisoformat(receipt['observed_at_utc']).timestamp()
        summary = analyze(con, observed)
    control = raw_control(snapshot / 'ecommerce.order_items.csv', observed)
    for row in summary['status_counts']:
        for field in ('item_rows', 'terminal_item_rows', 'duration_eligible_rows', 'reversed_delivery_rows'):
            if row[field] != control[row['status'], field]:
                raise ValueError('Independent CSV control differs')
    item_path = snapshot / 'ecommerce.order_items.csv'
    with item_path.open('rb') as stream:
        final_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    if final_hash != receipt['tables']['ecommerce.order_items']['csv_sha256']:
        raise ValueError('Source changed during operational analysis')
    result = {
        'schema_version': 1,
        'provenance': receipt['origin_classification'],
        'snapshot_observed_at_utc': receipt['observed_at_utc'],
        'source_item_rows': receipt['tables']['ecommerce.order_items']['rows'],
        'source_contract_sha256': receipt['contract_sha256'],
        'source_csv_sha256': receipt['tables']['ecommerce.order_items']['csv_sha256'],
        'implementation_sha256': hashlib.sha256(IMPLEMENTATION.read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
        'summary': summary, 'summary_sha256': canonical_hash(summary),
        'independent_raw_counts_reconciled': True,
        'decision': {
            'repair_chronology': summary['reversed_delivery_rows'] > 0,
            'action': 'Investigate delivery-before-creation rows using source event definitions and lineage.',
            'duration_eligibility': 'Complete or Returned item with finite creation/delivery epochs, creation <= delivery <= snapshot observation.',
            'grain_acceptance': 'One source item per key. Distinct orders reported separately. Mixed status/customer orders require investigation.',
            'success_criterion': 'Zero reversed delivery rows in a subsequent validated source correction. Preserve each original snapshot.',
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
