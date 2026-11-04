"""Synthetic prospective-design laboratory; no real randomized study or ROI claim."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd
from scipy.stats import binom,binomtest,fisher_exact

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/'contracts/delivery_experiment_plan.json'
SOURCES={
    'normal_planning':'https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.samplesize_proportions_2indep_onetail.html',
    'fisher':'https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.stats.fisher_exact.html',
    'newcombe':'https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.confint_proportions_2indep.html',
    'wilson':'https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html'}


def probability(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<value<1:
        raise ValueError('Finite probability strictly between zero and one required')
    return float(value)


def counts(events,total,allow_empty=False):
    if type(events) is not int or type(total) is not int or total<(0 if allow_empty else 1) or not 0<=events<=total:
        raise ValueError('Integer events within the complete nonnegative population required')


def planned_per_arm(control,treatment,alpha=.05,power=.8):
    control=probability(control);treatment=probability(treatment);alpha=probability(alpha);power=probability(power)
    if power<=.5 or control==treatment:raise ValueError('Power above 0.5 and a nonzero planned contrast required')
    pooled=(control+treatment)/2;z=NormalDist().inv_cdf(1-alpha/2);zp=NormalDist().inv_cdf(power)
    return math.ceil(((z*math.sqrt(2*pooled*(1-pooled))+zp*math.sqrt(control*(1-control)+treatment*(1-treatment)))/abs(treatment-control))**2)


def wilson(events,total,alpha=.05):
    counts(events,total);alpha=probability(alpha)
    p=events/total;z=NormalDist().inv_cdf(1-alpha/2);denominator=1+z*z/total
    center=(p+z*z/(2*total))/denominator
    radius=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/denominator
    return max(0.,center-radius),min(1.,center+radius)


def analyze(control_events,control_n,treatment_events,treatment_n,alpha=.05):
    counts(control_events,control_n);counts(treatment_events,treatment_n);alpha=probability(alpha)
    c=control_events/control_n;t=treatment_events/treatment_n;difference=t-c
    cl,cu=wilson(control_events,control_n,alpha);tl,tu=wilson(treatment_events,treatment_n,alpha)
    low=max(-1.,difference-math.hypot(t-tl,cu-c));high=min(1.,difference+math.hypot(tu-t,c-cl))
    p=float(fisher_exact([[treatment_events,treatment_n-treatment_events],[control_events,control_n-control_events]],alternative='two-sided').pvalue)
    return {'risk_difference_treatment_minus_control':difference,'newcombe_ci_low':low,'newcombe_ci_high':high,
        'fisher_two_sided_p':p,'reject_equal_risk':p<alpha,
        'direction':'lower_failure_risk' if difference<0 else 'higher_failure_risk' if difference>0 else 'equal_observed_risk',
        'causal_effect_execution_verified':False,'adoption_recommended':False}


def evaluate(control_events,control_n,treatment_events,treatment_n,planned_total,*,outcomes_complete=False,assignment_verified=False,alpha=.05,srm_alpha=.001):
    counts(control_events,control_n,True);counts(treatment_events,treatment_n,True)
    if type(planned_total) is not int or planned_total<2:raise ValueError('A fixed planned total of at least two required')
    if type(outcomes_complete) is not bool or type(assignment_verified) is not bool:raise ValueError('Explicit boolean evidence flags required')
    alpha=probability(alpha);srm_alpha=probability(srm_alpha);total=control_n+treatment_n
    result={'source_kind':'synthetic_experiment_design','gate':None,'inference':None,'adoption_recommended':False}
    if total<planned_total:result['gate']='WAIT_FIXED_HORIZON'
    elif total>planned_total:result['gate']='HOLD_ENROLLMENT_OVERRUN'
    elif not outcomes_complete:result['gate']='HOLD_INCOMPLETE_OUTCOMES'
    elif not assignment_verified:result['gate']='HOLD_ASSIGNMENT_UNVERIFIED'
    elif min(control_n,treatment_n)==0:result['gate']='HOLD_EMPTY_ARM'
    else:
        srm=float(binomtest(treatment_n,total,p=.5,alternative='two-sided').pvalue)
        result['sample_ratio_mismatch_p']=srm
        if srm<srm_alpha:result['gate']='HOLD_SAMPLE_RATIO_MISMATCH'
        else:
            result['gate']='READY_SYNTHETIC_FIXED_HORIZON'
            result['inference']=analyze(control_events,control_n,treatment_events,treatment_n,alpha)
    return result


def simulate(control,treatment,total,replicates,seed,alpha=.05,srm_alpha=.001):
    control=probability(control);treatment=probability(treatment);alpha=probability(alpha);srm_alpha=probability(srm_alpha)
    if type(total) is not int or total<2 or type(replicates) is not int or replicates<100 or type(seed) is not int or seed<0:
        raise ValueError('Positive fixed total, >=100 replicates and nonnegative integer seed required')
    rng=np.random.default_rng(seed)
    tn=rng.binomial(total,.5,replicates);cn=total-tn
    ce=rng.binomial(cn,control);te=rng.binomial(tn,treatment)
    # Exact fair-binomial two-sided SRM tail, vectorized by symmetry.
    srm=np.minimum(1.,2*binom.cdf(np.minimum(tn,cn),total,.5))<srm_alpha
    valid=(tn>0)&(cn>0);reject=np.zeros(replicates,dtype=bool);benefit=reject.copy();harm=reject.copy()
    for i in np.flatnonzero(valid):
        reject[i]=fisher_exact([[int(te[i]),int(tn[i]-te[i])],[int(ce[i]),int(cn[i]-ce[i])]],alternative='two-sided').pvalue<alpha
        benefit[i]=reject[i] and te[i]/tn[i]<ce[i]/cn[i]
        harm[i]=reject[i] and te[i]/tn[i]>ce[i]/cn[i]
    low,high=wilson(int(reject.sum()),replicates)
    return {'control_risk_assumed':control,'treatment_risk_assumed':treatment,'fixed_total_customers':total,
        'replicates':replicates,'seed':seed,'rejections':int(reject.sum()),'rejection_probability':float(reject.mean()),
        'monte_carlo_ci_low':low,'monte_carlo_ci_high':high,'benefit_rejections':int(benefit.sum()),'harm_rejections':int(harm.sum()),
        'srm_flags':int(srm.sum()),'empty_arm_trials':int((~valid).sum()),'decision_eligible_rejections':int((reject&~srm&valid).sum())}


def build(out=ROOT/'docs/experiment-design'):
    out=Path(out).resolve()
    if out in (ROOT,CONTRACT.parent,ROOT/'docs/advanced-analysis'):raise ValueError('Output must not overwrite existing source or Olist research directories')
    out.mkdir(parents=True,exist_ok=True);receipt=out/'evidence.json';receipt.unlink(missing_ok=True)
    contract_bytes=CONTRACT.read_bytes().replace(b'\r\n',b'\n')
    implementation=hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    logo_sha=hashlib.sha256((ROOT/'branding/nexus_official_transparent.png').read_bytes()).hexdigest()
    plan=json.loads(contract_bytes)
    if (plan['version']!=1 or plan['status']!='proposed_synthetic_design_not_preregistered'
        or plan['source_kind']!='synthetic_experiment_design' or plan['adoption_allowed'] is not False
        or plan['real_customers_enrolled']!=0 or plan['unit_economics_verified'] is not False
        or plan['guardrail_business_thresholds_approved'] is not False
        or plan['allocation']!='independent Bernoulli 0.5 per eligible customer'
        or plan['primary_test']!='two-sided Fisher exact; single primary hypothesis; no optional stopping'
        or plan['risk_difference_interval']!='Newcombe hybrid Wilson at 1-alpha; not an inversion of the Fisher test'):
        raise ValueError('Only a proposed synthetic design with adoption disabled is supported')
    rows=[]
    for baseline in plan['assumed_control_risks']:
        for delta in plan['assumed_absolute_reductions']:
            n=planned_per_arm(baseline,baseline-delta,plan['alpha_two_sided'],plan['planning_power'])
            rows.append({'control_risk_assumed':baseline,'absolute_reduction_assumed':delta,'treatment_risk_assumed':baseline-delta,'expected_customers_per_arm':n,'fixed_total_customers':2*n})
    grid=pd.DataFrame(rows);s=plan['simulation'];n=planned_per_arm(s['control_risk'],s['control_risk']-s['absolute_change'],plan['alpha_two_sided'],plan['planning_power'])
    trials=[]
    for i,(name,change) in enumerate((('null',0),('benefit',-s['absolute_change']),('harm',s['absolute_change']))):
        trials.append(dict(scenario=name,**simulate(s['control_risk'],s['control_risk']+change,2*n,s['replicates'],s['seed']+i,plan['alpha_two_sided'],plan['srm_alpha'])))
    simulation=pd.DataFrame(trials)
    grid.to_csv(out/'sample_size_grid.csv',index=False,lineterminator='\n');simulation.to_csv(out/'simulation.csv',index=False,lineterminator='\n')
    figure(grid,simulation,plan,out)
    report(grid,simulation,plan,out)
    if (CONTRACT.read_bytes().replace(b'\r\n',b'\n')!=contract_bytes
        or hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=implementation
        or hashlib.sha256((ROOT/'branding/nexus_official_transparent.png').read_bytes()).hexdigest()!=logo_sha):
        raise ValueError('Design inputs changed during generation; success receipt withheld')
    files=('sample_size_grid.csv','simulation.csv','design_tradeoffs.png','REPORT.md')
    from scripts.research_environment import inspect
    result={'source_kind':'synthetic_experiment_design','synthetic':True,'real_customers_enrolled':0,
        'contract_sha256':hashlib.sha256(contract_bytes).hexdigest(),
        'implementation_sha256':implementation,'design_inputs_stable_during_generation':True,
        'environment':inspect(),'grid_scenarios':len(grid),'simulation_scenarios':len(simulation),
        'replicates_per_scenario':s['replicates'],'planned_total_customers':2*n,
        'artifact_hash_basis':'LF-normalized text; binary byte-exact',
        'artifacts_sha256':{name:artifact_hash(out/name) for name in files},
        'official_logo_sha256':logo_sha,
        'method_sources':SOURCES,'business_thresholds_approved':False,'causal_effect_execution_verified':False,
        'current_business_baseline_verified':False,'financial_roi_estimated':False,'adoption_recommended':False}
    receipt.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return result


def artifact_hash(path):
    raw=path.read_bytes()
    if path.suffix in {'.md','.csv','.json'}:raw=raw.replace(b'\r\n',b'\n')
    return hashlib.sha256(raw).hexdigest()


def figure(grid,simulation,plan,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'figure.facecolor':'#080F20','axes.facecolor':'#080F20','text.color':'#EDF5FF','axes.labelcolor':'#B9C5CE',
        'xtick.color':'#B9C5CE','ytick.color':'#B9C5CE','axes.edgecolor':'#334155','font.size':10})
    fig,axes=plt.subplots(1,2,figsize=(13,6))
    for delta,color in zip(plan['assumed_absolute_reductions'],('#47DFF2','#A99BFF','#81B8FF')):
        subset=grid[grid.absolute_reduction_assumed==delta]
        axes[0].plot(subset.control_risk_assumed*100,subset.expected_customers_per_arm,marker='o',color=color,label=f'{delta*100:g} pp reduction')
    axes[0].set(xlabel='Assumed control failure risk (%)',ylabel='Expected customers per arm',yscale='log',title='Approximate sample-size sensitivity')
    axes[0].legend(facecolor='#080F20',labelcolor='#EDF5FF')
    rate=simulation.rejection_probability.to_numpy()
    axes[1].errorbar(np.arange(3),rate*100,yerr=np.array([rate-simulation.monte_carlo_ci_low,simulation.monte_carlo_ci_high-rate])*100,
                     fmt='o',capsize=6,color='#47DFF2',markersize=7)
    labels=[f'{r.scenario.title()}: {r.control_risk_assumed:.0%} / {r.treatment_risk_assumed:.0%}' for r in simulation.itertuples()]
    axes[1].set(xticks=np.arange(3),xticklabels=labels,ylabel='Two-sided rejection probability (%)',ylim=(0,100),title='Exact-test Monte Carlo operating characteristics')
    axes[1].axhline(plan['alpha_two_sided']*100,color='#A99BFF',linestyle=':',label=f"Nominal alpha: {plan['alpha_two_sided']:.0%}")
    axes[1].axhline(plan['planning_power']*100,color='#81B8FF',linestyle='--',label=f"Approximate planning target: {plan['planning_power']:.0%}")
    axes[1].legend(facecolor='#080F20',labelcolor='#EDF5FF',loc='center right',fontsize=8)
    fig.text(.06,.95,'NEXUS  /  EXPERIMENT DESIGN LAB',color='#47DFF2',fontsize=12)
    fig.text(.06,.895,'Synthetic assumptions • fixed total enrollment • one first order per randomized customer',fontsize=10)
    logo=fig.add_axes([.80,.90,.15,.075]);logo.imshow(plt.imread(ROOT/'branding/nexus_official_transparent.png'));logo.axis('off')
    fig.text(.06,.04,f"{plan['simulation']['replicates']:,} synthetic trials/scenario | Error bars: Monte Carlo Wilson 95% intervals | No real trial, ROI or adoption claim",fontsize=9,color='#B9C5CE')
    fig.subplots_adjust(top=.78,bottom=.20,left=.09,right=.97,wspace=.28)
    fig.savefig(out/'design_tradeoffs.png',dpi=160,facecolor=fig.get_facecolor());plt.close(fig)


def report(grid,simulation,plan,out):
    n=int(simulation.fixed_total_customers.iloc[0]);lines=[]
    s=plan['simulation'];baselines=', '.join(f'{p:.0%}' for p in plan['assumed_control_risks'])
    reductions=', '.join(f'{p*100:g}' for p in plan['assumed_absolute_reductions'])
    for row in simulation.itertuples():lines.append(f'| {row.scenario} | {row.control_risk_assumed:.0%} / {row.treatment_risk_assumed:.0%} | {row.rejections}/{row.replicates} | {row.rejection_probability:.2%} [{row.monte_carlo_ci_low:.2%}, {row.monte_carlo_ci_high:.2%}] | {row.srm_flags} |')
    text=f'''# NEXUS Experiment Design Lab

**Proposed synthetic design; no real trial, prospective preregistration or causal effect has been established.** This is a separate teaching module, not a sixth Olist study. It reads no historical commerce records and does not replace the five public Olist studies or their native report. All rates and target effects below are illustrative assumptions, not measured current-business baselines.

## Question and proposed measurement

Could a future shipment-exception triage intervention reduce failure to deliver by the promised deadline? Randomize eligible customers independently with probability 0.5; use only each customer's first eligible order and preserve assignment. The denominator is every randomized eligible customer, including cancelled and genuinely undelivered first orders. Freeze the promised UTC deadline at assignment. Adjudicate after that deadline plus seven recording days. Missing telemetry remains unknown and blocks complete-outcome analysis; absent records must not be relabelled as physical non-delivery or successful delivery.

Historical Olist lateness was measured among delivered orders. That is a different estimand and cannot supply the failure-risk baseline for this all-randomized-customer endpoint. Customer-level assignment also does not resolve shared queue capacity, geographic interference or warehouse-level treatment spillover. Those need feasibility evidence and possibly a different randomization design.

## Planning sensitivity and simulated operation

The {len(grid)}-cell grid assumes baseline risks {baselines}, with absolute reductions of {reductions} percentage points. Equal *expected* arm sizes use a pooled-null/unpooled-alternative normal approximation at two-sided alpha {plan['alpha_two_sided']:g} and target power {plan['planning_power']:.2f}. It ignores the far tail and exact-test discreteness. The fixed total for the {s['control_risk']:.0%} to {s['control_risk']-s['absolute_change']:.0%} demonstration is **{n:,} customers**; Bernoulli assignment allows unequal realized arm sizes. No calendar duration is estimated because reliable eligible-customer arrival volume is unavailable. No arbitrary attrition factor converts unknown outcomes into complete data.

For each scenario, {s['replicates']:,} independent synthetic trials use that fixed total. Counts follow independent binomial assumptions, without seasonality, clustering or interference. Two-sided Fisher testing supplies the rejection indicator. Wilson intervals below describe **Monte Carlo estimation uncertainty**, not treatment-effect uncertainty or evidence from actual customers. The null row estimates Type I rejection; alternative rows estimate rejection power under those particular assumptions. Power is not guaranteed. The harm scenario changes baseline variance in the opposite direction, so the benefit-based sample size does not guarantee the same harm-detection power.

| Scenario | Assumed control / treatment risk | Rejections | Rejection probability [Monte Carlo 95% interval] | SRM flags |
| --- | --- | --- | --- | --- |
{chr(10).join(lines)}

![NEXUS synthetic sample-size and power sensitivity](design_tradeoffs.png)

[Planning grid](sample_size_grid.csv) · [Simulation counts](simulation.csv) · [Machine-readable provenance](evidence.json) · [Proposed contract](../../contracts/delivery_experiment_plan.json).

## Analysis and decision rules

- One primary null: equal binary failure risks; two-sided Fisher test at alpha {plan['alpha_two_sided']:g}. Report treatment-minus-control risk difference, so negative means lower failure risk. Newcombe hybrid Wilson {1-plan['alpha_two_sided']:.0%} intervals describe that difference. They are not an inversion of the Fisher test, and no p-value/interval equivalence is asserted.
- `evaluate` withholds inference before the fixed enrollment horizon, on enrollment overrun, incomplete outcomes, unverified assignment or sample-ratio mismatch. SRM uses an exact two-sided fair-binomial check at {plan['srm_alpha']:g} under the specified independent Bernoulli assignment. It diagnoses allocation integrity rather than a secondary business outcome. Simulation counts retain all replicates, including SRM/empty-arm cases; no conditional filtering inflates power.
- No optional stopping, interim significance searches, subgroup winner selection or unadjusted secondary confirmatory tests. Guardrails are cancellations/non-delivery, unknown telemetry, workload and queue interference; business thresholds are **unapproved**, not fabricated here.
- A detectable effect is not an approved economically worthwhile effect. Unit costs, guardrail budgets and incremental revenue are unknown. Statistical rejection never automatically recommends adoption. No production assignment, customer contact, commercial launch or paid infrastructure is created.

## Reproduction and sources

Run `python -m scripts.experiment_design` with the existing locked research environment. The contract and implementation hashes, runtime versions and exported-file hashes are retained in `evidence.json`. Fixed seeds make this a reproducible simulation, not prospective registration of an actual study. Simulation assumptions must be replaced and preregistered appropriately before a real trial.

[Normal sample-size approximation]({SOURCES['normal_planning']}) · [Fisher exact definition]({SOURCES['fisher']}) · [Newcombe interval methods]({SOURCES['newcombe']}) · [Wilson interval reference]({SOURCES['wilson']}). Formula implementations and method cross-checks are executable locally. This authored synthetic module remains separate from Olist-derived CC BY-NC-SA artifacts and from private financial data.
'''
    (out/'REPORT.md').write_text(text,encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=ROOT/'docs/experiment-design');a=p.parse_args()
    result=build(a.out);print(json.dumps({k:result[k] for k in ('source_kind','grid_scenarios','simulation_scenarios','planned_total_customers','adoption_recommended')},indent=2))
