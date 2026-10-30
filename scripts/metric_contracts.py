"""Validate the source-scoped metric registry and render its documentation.

Uses committed/local aggregate evidence only. No cloud account checks or queries.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FIELDS={'id','domain','name','unit','grain','definition','denominator','null_policy','sql','limits'}


def validate(registry: dict,root: Path=ROOT) -> list[dict]:
    if registry.get('version')!=1 or not isinstance(registry.get('metrics'),list) or not registry['metrics']:
        raise ValueError('Nonempty version-1 metric registry required')
    seen=set()
    for metric in registry['metrics']:
        if not FIELDS.issubset(metric) or any(not isinstance(metric[k],str) or not metric[k].strip() for k in FIELDS):
            raise ValueError('Each metric requires explicit unit, grain, denominator, null policy, source and limitations')
        if metric['id'] in seen:raise ValueError('Duplicate metric id: '+metric['id'])
        seen.add(metric['id'])
        if metric['domain'] not in {'E-Commerce','Greenweez','Olist'}:raise ValueError('Unregistered source domain')
        prefixes={'E-Commerce':('models/','analyses/','scripts/run_analysis.py'),
                  'Greenweez':('integrations/greenweez/',),
                  'Olist':('analytics/olist/','scripts/olist_','scripts/advanced_olist.py')}
        if not metric['sql'].startswith(prefixes[metric['domain']]):raise ValueError('Metric implementation crosses its source domain')
        source=(root/metric['sql']).resolve()
        if root.resolve() not in source.parents or not source.is_file():raise ValueError('Missing/escaped metric source: '+metric['sql'])
        if source.relative_to(root.resolve()).as_posix()!=metric['sql']:raise ValueError('Metric implementation path must be canonical')
    return registry['metrics']


def build(root: Path=ROOT,*,evidence_dir: Path | None=None,out: Path | None=None) -> dict:
    root=root.resolve();out=(out or root/'docs').resolve()
    evidence_dir=evidence_dir or root/'docs/analysis'
    registry=json.loads((root/'contracts/metrics.json').read_text(encoding='utf-8'))
    metrics=validate(registry,root)
    def relative(path):
        value=Path(os.path.relpath(path,out)).as_posix()
        return '<'+value+'>' if any(ch.isspace() for ch in value) else value
    evidence=json.loads((evidence_dir/'evidence.json').read_text(encoding='utf-8'))
    public=json.loads((root/'docs/advanced-analysis/evidence.json').read_text(encoding='utf-8'))
    if evidence.get('provenance')!='synthetic_ci' or evidence['greenweez'].get('provenance')!='synthetic_demo':
        raise ValueError('Source coverage documentation requires explicitly synthetic commerce evidence')
    if public.get('source_kind')!='historical_public_olist' or public.get('synthetic') is not False:
        raise ValueError('Olist coverage must remain a separate public historical population')
    lines=['# Source-scoped KPI catalog','',
        f'Authoritative definitions: [`contracts/metrics.json`]({relative(root/"contracts/metrics.json")}). Regenerate with `python -m scripts.metric_contracts`.',
        '', 'The registry documents implemented calculations and their interpretation. It does not certify source freshness, accounting recognition or DAX engine acceptance. Legacy SQL fields named `net_revenue` mean current completed item value in this project; their compatibility names do not establish net revenue.',
        '', 'Values, periods and denominators must never be added across E-Commerce, Greenweez, Olist or optional Google account measurements. Percentages require recomputed weighted numerators/denominators rather than averages of subgroup percentages.','']
    for domain in ('E-Commerce','Greenweez','Olist'):
        lines+=['## '+domain,'']
        for m in metrics:
            if m['domain']!=domain:continue
            lines += ['### '+m['name'],'',f"`{m['id']}` · Unit: **{m['unit']}** · Grain: **{m['grain']}**",'',
                m['definition']+'.', '',f"Denominator: {m['denominator']}. Null policy: {m['null_policy']}.", '',
                f"Limit: {m['limits']}. [Implementation]({relative(root/m['sql'])}).",'']
    p=evidence['profile'];c=evidence['cost_diagnostics'];g=c['greenweez']
    cost_coverage=f"{c['ecommerce']['cost_revenue_coverage_pct']:.2f}%" if c['ecommerce']['cost_revenue_coverage_pct'] is not None else 'not estimable'
    coverage=f'''# Source coverage and analytical readiness

This table describes the recorded inputs of the public portfolio build. It does **not** check current cloud access or perform a new live refresh. Regenerate from explicit local evidence with `python -m scripts.metric_contracts`.

| Domain | Evidence and population | Current analytical boundary |
| --- | --- | --- |
| E-Commerce fixture | {p['order_lines']} synthetic item rows; {p['sessions']} session/user pairs; {p['completed_orders_period_distinct']} period-distinct completed orders; {p['order_period'][0]} through {p['order_period'][1]} | Reconciled pipeline demonstration. Too small for channel winners, causal uplift or business forecasts. |
| Greenweez raw-branch fixture | {g['sales_lines']:,} synthetic sales lines; {g['orders']:,} order records; {evidence['greenweez']['daily_rows']} finance dates | {g['orders_with_incomplete_components']} order records have incomplete product/shipping components under the diagnostic policy; {g['unknown_cost_line_revenue']:,.2f} source units of sales value lack eligible line costs. Arithmetic reconciliation is not an accounting audit. |
| Olist public history | {public['quality']['order_fact_rows']:,} source orders; {public['summary']['orders']:,} delivered orders in {public['summary']['purchase_window']} | Separate non-commercial historical study. Source-file hashes and selection/observation limits are recorded; no current commerce performance claim. |
| Existing BigQuery integration | Repository configuration and historical keyless metadata evidence; no cloud rows read by this build | Current live row coverage/freshness is unverified here. Preserve existing byte caps and source-region separation; do not promote historical authentication evidence into a fresh extraction. |
| GA4 / GSC / Lighthouse / Commerce Lab | Independent optional collectors and consented test-event workflows | Not imported into this analytical denominator. Account measurements and lab events are not historical completed orders or sales. |

## Cost coverage acceptance

E-Commerce completed-value coverage is {cost_coverage} in the current synthetic fixture. The product contribution rate uses only revenue paired with eligible costs. Unknown costs are never treated as free inventory.

Greenweez's current finance model retains all sales revenue while `SUM` excludes missing product-line margins; missing operational components follow its existing zero policies. The coverage diagnostic exposes those policies without changing them. A complete-component subtotal describes selected order records, not a whole-business margin estimate, lower bound or advertising-adjusted result. Google Sheets refund units remain a separately unverified contract.

## Gates before a real business conclusion

1. Confirm source population, extract freshness, period, currency and refund/cost interpretation.
2. Reconcile raw eligible rows, item/order grain and joins before aggregating metrics.
3. Publish missing-component coverage and use the same eligible rows for numerator and denominator.
4. Distinguish observational attribution/accounting identities from causal effects.
5. Apply a quota-bounded authorized source refresh before replacing synthetic labels with real-business labels.

Evidence: [commerce results]({relative(evidence_dir/'REPORT.md')}), [commerce receipt]({relative(evidence_dir/'evidence.json')}), [Olist study]({relative(root/'docs/advanced-analysis/REPORT.md')}), [BigQuery connection contract]({relative(root/'docs/GITHUB_ACTIONS_BIGQUERY_OIDC.md')}), [Google measurement contract]({relative(root/'docs/GOOGLE_MEASUREMENT_INTEGRATION.md')}). [KPI definitions](KPI_CATALOG.md).
'''
    out.mkdir(parents=True,exist_ok=True)
    (out/'KPI_CATALOG.md').write_text('\n'.join(lines),encoding='utf-8')
    (out/'SOURCE_COVERAGE.md').write_text(coverage,encoding='utf-8')
    return {'metrics':len(metrics),'domains':3,'live_queries_performed':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir',type=Path)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args();print(json.dumps(build(evidence_dir=args.evidence_dir,out=args.out),indent=2))
