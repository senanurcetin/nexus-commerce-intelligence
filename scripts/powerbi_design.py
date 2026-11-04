"""NEXUS native PBIR presentation, scoped filters and semantic number formats.

Authors editable Power BI objects only. No screenshot, simulated BI image,
browser, native engine or source-data transformation is used here.
"""
from __future__ import annotations
import json
from pathlib import Path
import re

from scripts.build_powerbi import SCHEMA_ROOT,_field

METHOD_LABELS={'seasonal_naive':'Seasonal naive','weekday_mean_28':'28-day weekday mean',
               'ridge_calendar_180':'Calendar ridge','past_mae_selector':'Past-MAE selector'}
RATE_FIELDS={'retention','repeat_probability','ci_low','ci_high','risk_share','mature_repeat_rate',
    'km_repeat_probability','gmv_share','cumulative_share','top_1_share','top_10_share','top_100_share',
    'late_rate','wape','day_coverage','week_coverage'}
LABELS={'gmv':'Item GMV (source units)','gmv_change':'GMV change','order_volume':'Order volume',
    'basket_size':'Basket size','unit_value':'Unit value','ci_low':'95% lower','ci_high':'95% upper',
    'km_repeat_probability':'Pooled KM repeat','mature_repeat_rate':'Mature repeat rate','at_risk':'At risk',
    'method_label':'Benchmark method','late':'Delivery group','month':'Month','quarter':'Quarter','day':'Day'}


def literal(value):
    if isinstance(value,bool):encoded='true' if value else 'false'
    elif isinstance(value,(int,float)):encoded=str(value)+'D'
    else:encoded="'"+str(value).replace("'","''")+"'"
    return {'expr':{'Literal':{'Value':encoded}}}


def fill(color):return {'solid':{'color':literal(color)}}


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def textbox(name,text,x,y,width,height,tab=90):
    return {'$schema':SCHEMA_ROOT+'item/report/definition/visualContainer/2.7.0/schema.json','name':name,
        'position':{'x':x,'y':y,'z':9500,'width':width,'height':height,'tabOrder':tab},
        'visual':{'visualType':'textbox','objects':{'general':[{'properties':{'paragraphs':[
            {'textRuns':[{'value':line,'textStyle':{'fontFamily':'Segoe UI','fontSize':'10px','color':'#B8C8DF'}}]}
            for line in text.split('\n')]}}]},'visualContainerObjects':{key:[{'properties':{'show':literal(False)}}] for key in ('background','border')},'drillFilterOtherVisuals':False}}


def slicer(name,table,column,title,index,default=None):
    objects={'data':[{'properties':{'mode':literal('Between' if column in {'day','date'} else 'Dropdown')}}],
             'header':[{'properties':{'show':literal(True),'text':literal(title)}}]}
    if default is not None:
        objects['selection']=[{'properties':{'singleSelect':literal(True),'selectAllCheckboxEnabled':literal(False)}}]
        objects['general']=[{'properties':{'filter':{'filter':{'Version':2,'From':[{'Name':'s','Entity':table,'Type':0}],
            'Where':[{'Condition':{'In':{'Expressions':[{'Column':{'Expression':{'SourceRef':{'Source':'s'}},'Property':column}}],
                'Values':[[{'Literal':{'Value':"'"+default.replace("'","''")+"'"}}]]}}}]}}}}]
    return {'$schema':SCHEMA_ROOT+'item/report/definition/visualContainer/2.7.0/schema.json','name':name,
        'position':{'x':24+index*316,'y':108,'z':8000+index,'width':300,'height':80,'tabOrder':10+index},
        'visual':{'visualType':'slicer','query':{'queryState':{'Values':{'projections':[_field(table,column,False)]}}},
            'objects':objects,'visualContainerObjects':{'title':[{'properties':{'show':literal(False)}}],
                'padding':[{'properties':{side:literal(8) for side in ('top','bottom','left','right')}}]},'drillFilterOtherVisuals':False}}


def number_format(table,column,kind):
    if kind=='dateTime':return 'mmm yyyy' if column in {'month','quarter','cohort'} else 'dd MMM yyyy'
    if kind=='int64':return '#,0'
    if kind!='double':return None
    if column in RATE_FIELDS and table!='Association':return '0.00%'
    if table=='OperationsSummary':return '0.00%'
    return '0.0000' if column=='hhi' else '#,0.00'


def apply_formats(project,model_name,tables):
    for table,fields in tables.items():
        path=project.parent/(model_name+'.SemanticModel/definition/tables')/(table+'.tmdl')
        text=path.read_text(encoding='utf-8')
        for column,kind in fields:
            fmt=number_format(table,column,kind)
            if fmt:
                pattern=r'(?m)^(\tcolumn '+re.escape(column)+r'\n)((?:\t\t[^\n]*\n)*)'
                def formatted(match):
                    body=re.sub(r'(?m)^\t\tformatString:[^\n]*\n','',match.group(2))
                    return match.group(1)+'\t\tformatString: '+fmt+'\n'+body
                text,count=re.subn(pattern,formatted,text)
                if count!=1:raise ValueError('Cannot format an unknown or repeated semantic column')
        path.write_text(text,encoding='utf-8')


def line_styles(spec):
    roles=spec['visual']['query']['queryState'];ys=roles.get('Y',{}).get('projections',[])
    entries=[]
    for index,p in enumerate(ys):
        measure=next(iter(p['field'].values()))['Property']
        bound='Lower' in measure or 'Upper' in measure
        observed=measure=='Observed Placed Orders'
        props={'strokeWidth':literal(1.25 if bound or observed else 2.5),
            'lineStyle':literal('dotted' if bound else 'solid' if observed or index==0 else 'dashed'),
            'showMarker':literal(False),'lineChartType':literal('linear')}
        if 'RepeatCurve.' in p['queryRef']:
            props.update(lineChartType=literal('step'),interpolationStep=literal('after'))
        if bound or observed or measure=='Selected Forecast':
            props['strokeColor']=fill('#A892F4' if bound else '#EDF5FF' if observed else '#47DFF2')
        entries.append({'selector':{'metadata':p['queryRef']},'properties':props})
    spec['visual']['objects']['lineStyles']=entries


def apply(project,model_name,pages,tables,config):
    """Configure explicit per-page filters without introducing model relationships."""
    apply_formats(project,model_name,tables);receipts=[]
    base=project.parent/(model_name+'.Report/definition/pages')
    kinds={table:dict(fields) for table,fields in tables.items()}
    for page in pages:
        pid=page['id'];folder=base/pid;cfg=config[pid]
        visuals={p.parent.name:json.loads(p.read_text(encoding='utf-8')) for p in (folder/'visuals').glob('*/visual.json')}
        for name in list(visuals):
            if name.startswith('nexus_filter_') or name=='nexus_metric_note':
                path=(folder/'visuals'/name/'visual.json').resolve()
                if folder.resolve() not in path.parents:raise ValueError('Generated visual cleanup escaped its page')
                path.unlink();del visuals[name]
        for v in visuals.values():
            if v['visual']['visualType'] in {'textbox','image'}:
                v['visual'].setdefault('visualContainerObjects',{}).update({key:[{'properties':{'show':literal(False)}}] for key in ('background','border')})
        numerical=[v for v in visuals.values() if v['visual'].get('query')]
        cards=[v for v in numerical if v['visual']['visualType']=='cardVisual']
        charts=[v for v in numerical if v['visual']['visualType']!='cardVisual']
        if len(cards)>3 or len(charts)>2:raise ValueError('Unexpected or stale visuals exceed the native page layout contract')
        cards.sort(key=lambda v:v['position']['tabOrder']);charts.sort(key=lambda v:v['position']['tabOrder'])
        for i,v in enumerate(cards):
            width=(1232-16*(len(cards)-1))/len(cards)
            v['position'].update(x=24+i*(width+16),y=204,width=width,height=82,tabOrder=20+i)
        for i,v in enumerate(charts):
            width=1232 if len(charts)==1 else (792 if i==0 else 424) if pid=='olist_forecasting' else 608
            x=24 if i==0 else 832 if pid=='olist_forecasting' else 648
            v['position'].update(x=x,y=310 if cards else 208,width=width,height=320 if cards else 422,tabOrder=30+i)
            v['visual']['visualContainerObjects']['padding']=[{'properties':{side:literal(8) for side in ('top','bottom','left','right')}}]
            roles=v['visual']['query']['queryState']
            for role in roles.values():
                for projection in role['projections']:
                    field=next(iter(projection['field'].values()));table=field['Expression']['SourceRef']['Entity'];column=field['Property']
                    if 'Column' in projection['field']:
                        projection['displayName']=LABELS.get(column,column.replace('_',' ').capitalize())
                        fmt=number_format(table,column,kinds[table][column])
                        if fmt:projection['format']=fmt
            if v['visual']['visualType']=='lineChart':line_styles(v)
            category=roles.get('Category',roles.get('Rows',{})).get('projections',[])
            if category:
                descending=v['visual']['visualType']=='clusteredBarChart'
                sort_field=(roles['Y']['projections'][0]['field'] if descending else category[0]['field'])
                v['visual']['query']['sortDefinition']={'sort':[{'field':sort_field,'direction':'Descending' if descending and pid!='olist_forecasting' else 'Ascending'}],'isDefaultSort':True}
        filters=[]
        for i,definition in enumerate(cfg['filters']):
            table,column,title,*default=definition
            name='nexus_filter_'+str(i+1);spec=slicer(name,table,column,title,i,default[0] if default else None)
            visuals[name]=spec;filters.append((name,table))
        note_x=24+len(filters)*316
        visuals['nexus_filter_scope']=textbox('nexus_filter_scope',cfg['scope'],note_x,108,1256-note_x,80,15)
        visuals['nexus_metric_note']=textbox('nexus_metric_note',cfg['note'],24,650,1232,54,80)
        interactions=[]
        data_targets={v['name']:v for v in numerical}
        targets={**data_targets,**{name:visuals[name] for name,_ in filters}}
        # Keep selections from silently refitting fixed uncertainty or comparing
        # nonmatching windows. Only declared slicers drive declared targets.
        for source in targets:
            for target,v in targets.items():
                if source==target:continue
                enabled=False
                if source in dict(filters) and target in data_targets:
                    source_table=dict(filters)[source]
                    used={next(iter(p['field'].values()))['Expression']['SourceRef']['Entity'] for role in v['visual']['query']['queryState'].values() for p in role['projections']}
                    enabled=source_table in used
                    if pid=='olist_forecasting':
                        enabled=(source_table=='ForecastDaily' and target==charts[0]['name']) or (source_table=='ForecastMetrics' and target!=charts[1]['name'])
                interactions.append({'source':source,'target':target,'type':'DataFilter' if enabled else 'NoFilter'})
        page_path=folder/'page.json';spec=json.loads(page_path.read_text());spec['visualInteractions']=interactions;write(page_path,spec)
        for name,v in visuals.items():write(folder/'visuals'/name/'visual.json',v)
        receipts.append({'page':pid,'visuals':len(visuals),'slicers':len(filters),'interaction_rules':len(interactions),
                         'scope':cfg['scope'],'note':cfg['note']})
    receipt={'source':'native PBIR/PBIP objects','canvas':[1280,720],'pages':receipts,
        'native_render_verified':False,'dax_engine_executed':False,'runtime_filter_behavior_verified':False,
        'no_cross_source_relationships_added':True,'official_nexus_logo_preserved':True}
    write(project.parent/'visual_design.json',receipt)
    return receipt
