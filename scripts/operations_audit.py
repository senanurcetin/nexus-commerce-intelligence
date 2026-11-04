"""Replay matched-period delivery counts, uncertainty and decomposition from CSVs."""
import argparse
from collections import Counter, defaultdict
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import numpy as np

from scripts import delivery_association_audit, review_cluster_audit
from scripts.delivery_association_audit import bootstrap
from scripts.review_cluster_audit import FILES, ROOT, close, digest, finite, need, rows, timestamp

RAW_FILES = tuple(FILES[k] for k in ('customers', 'orders', 'order_items'))
EXPORTS = ('operations_monthly.csv', 'operations_strata.csv', 'operations_summary.csv')
YEARS = (2017, 2018)


def reconstruct(raw):
    customers = {}
    for row in rows(raw / FILES['customers'], ('customer_id', 'customer_unique_id', 'customer_state')):
        key = row['customer_id']
        need(key and key not in customers, 'Invalid customer key')
        customers[key] = (row['customer_unique_id'], row['customer_state'] or 'Unknown state')

    positive_orders = set()
    for row in rows(raw / FILES['order_items'], ('order_id', 'price')):
        need(finite(row['price']) > 0, 'Invalid item price')
        positive_orders.add(row['order_id'])

    orders = Counter()
    late = Counter()
    customers_by_year = defaultdict(lambda: [0, 0, 0, 0])
    seen_orders = set()
    fields = ('order_id', 'customer_id', 'order_status', 'order_purchase_timestamp',
              'order_delivered_customer_date', 'order_estimated_delivery_date')
    for row in rows(raw / FILES['orders'], fields):
        key = row['order_id']
        need(key and key not in seen_orders, 'Invalid order key')
        seen_orders.add(key)
        person, state = customers[row['customer_id']]
        if key not in positive_orders or row['order_status'] != 'delivered' or not person:
            continue
        purchase = timestamp(row['order_purchase_timestamp'])
        delivered = timestamp(row['order_delivered_customer_date'])
        promised = timestamp(row['order_estimated_delivery_date'])
        if not (purchase and delivered and promised and purchase.year in YEARS and purchase.month <= 7):
            continue
        if delivered < purchase or promised.date() < purchase.date():
            continue
        cell = (purchase.year, purchase.month, state)
        is_late = delivered.date() > promised.date()
        orders[cell] += 1
        late[cell] += is_late
        offset = 0 if purchase.year == 2018 else 2
        ledger = customers_by_year[person]
        ledger[offset] += is_late
        ledger[offset + 1] += 1
    need(positive_orders <= seen_orders, 'Orphan item order')
    ledger = np.array([customers_by_year[k] for k in sorted(customers_by_year)])
    return orders, late, ledger


def validate(raw, published, evidence):
    orders, late, ledger = reconstruct(raw)
    monthly = {(y, m): (sum(n for (a, b, _), n in orders.items() if (a, b) == (y, m)),
                        sum(n for (a, b, _), n in late.items() if (a, b) == (y, m)))
               for y in YEARS for m in range(1, 8)}
    observed = {}
    for row in rows(published / EXPORTS[0], ('year', 'month', 'orders', 'late_orders', 'late_rate')):
        cell = (int(row['year']), int(row['month']))
        need(cell not in observed, 'Duplicate monthly cell')
        n, k = int(row['orders']), int(row['late_orders'])
        need(n > 0, 'Empty published month')
        close(row['late_rate'], Fraction(k, n), 'Monthly rate differs')
        observed[cell] = (n, k)
    need(observed == monthly, 'Monthly raw counts differ')

    common = {(month, state) for year, month, state in orders
              if all(orders[y, month, state] >= 20 for y in YEARS)}
    totals = {y: sum(orders[y, *cell] for cell in common) for y in YEARS}
    need(bool(common), 'No common support')
    contributions = {'within_contribution': Fraction(0), 'mix_contribution': Fraction(0)}
    standardized = {y: Fraction(0) for y in YEARS}
    seen = set()
    for row in rows(published / EXPORTS[1], ('month', 'state')):
        cell = (int(row['month']), row['state'])
        need(cell in common and cell not in seen, 'Invalid common-support cell')
        seen.add(cell)
        counts = {y: orders[y, *cell] for y in YEARS}
        rates = {y: Fraction(late[y, *cell], counts[y]) for y in YEARS}
        weights = {y: Fraction(counts[y], totals[y]) for y in YEARS}
        pooled = Fraction(sum(counts.values()), sum(totals.values()))
        for y in YEARS:
            need(int(row[f'orders_{y}']) == counts[y] and int(row[f'late_orders_{y}']) == late[y, *cell],
                 'Raw stratum counts differ')
            close(row[f'rate_{y}'], rates[y], 'Stratum rate differs')
            close(row[f'weight_{y}'], weights[y], 'Stratum weight differs')
            standardized[y] += pooled * rates[y]
        close(row['pooled_weight'], pooled, 'Pooled weight differs')
        values = {
            'within_contribution': sum(weights.values()) * (rates[2018] - rates[2017]) / 2,
            'mix_contribution': sum(rates.values()) * (weights[2018] - weights[2017]) / 2,
        }
        for key, value in values.items():
            close(row[key], value, 'Stratum contribution differs')
            contributions[key] += value
    need(seen == common, 'Missing common-support cells')

    replay = bootstrap(ledger, seed=20261028)
    expected = {'common_strata': len(common), 'minimum_orders_per_year_stratum': 20,
                'common_rate_change': sum(contributions.values()), **contributions}
    for y, prefix in ((2017, 'on_time'), (2018, 'late')):
        n, k = replay[f'{prefix}_orders'], replay[f'{prefix}_poor']
        expected.update({f'orders_{y}': n, f'late_orders_{y}': k, f'full_rate_{y}': Fraction(k, n),
                         f'common_orders_{y}': totals[y], f'common_coverage_{y}': Fraction(totals[y], n),
                         f'common_rate_{y}': Fraction(sum(late[y, *c] for c in common), totals[y]),
                         f'pooled_standardized_rate_{y}': standardized[y]})
    for key in ('customers', 'iterations', 'seed', 'valid_replicates'):
        expected['bootstrap_' + key] = replay[key]
    expected.update(full_rate_change=replay['risk_difference'], full_change_ci_low=replay['ci_low'],
                    full_change_ci_high=replay['ci_high'])
    summary, = rows(published / EXPORTS[2], expected)
    for key, value in expected.items():
        close(summary[key], value, 'Summary CSV differs: ' + key)
        close(evidence['summary'][key], value, 'Evidence summary differs: ' + key)
    return {key: float(value) if isinstance(value, Fraction) else value for key, value in expected.items()}


def audit(raw, published):
    paths = {f'raw/{name}': raw / name for name in RAW_FILES}
    paths.update({f'published/{name}': published / name for name in ('operations_evidence.json', *EXPORTS)})
    paths.update({f'code/{path.name}': path for path in (
        Path(__file__), Path(delivery_association_audit.__file__), Path(review_cluster_audit.__file__))})
    result = {'acceptance': 'FAIL', 'raw_rows_exported': False, 'derived_license': 'CC-BY-NC-SA-4.0',
              'scope': 'Retrospective matched-period counts, crude cluster interval and common-support rate/mix arithmetic.'}
    try:
        def snapshot():
            return {key: digest(path) if key.startswith('raw/') else
                    hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                    for key, path in paths.items()}

        before = snapshot()
        evidence = json.loads((published / 'operations_evidence.json').read_text(encoding='utf-8'))
        need(evidence['source_kind'] == 'historical_public_olist_operations', 'Unexpected source')
        for name in RAW_FILES:
            need(before[f'raw/{name}'] == evidence['quality']['files'][name]['sha256'], 'Raw hash differs')
        for name in EXPORTS:
            need(digest(published / name) == evidence['aggregate_sha256'][name], 'Export hash differs')
        details = validate(raw, published, evidence)
        need(before == snapshot(), 'Inputs changed during replay')
        result.update(acceptance='PASS', input_sha256=before, details=details)
    except (OSError, ValueError, KeyError, TypeError, csv.Error):
        result['error'] = 'Source integrity or numerical replay failed'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, default=ROOT / 'target/olist/raw')
    parser.add_argument('--published', type=Path, default=ROOT / 'docs/advanced-analysis')
    parser.add_argument('--out', type=Path, default=ROOT / 'target/operations-validation.json')
    args = parser.parse_args()
    raw, published, out = args.raw.resolve(), args.published.resolve(), args.out.resolve()
    if any(out == folder or folder in out.parents for folder in (raw, published)):
        parser.error('Write the receipt outside the input directories')
    result = audit(raw, published)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(result['acceptance'])
    return int(result['acceptance'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
