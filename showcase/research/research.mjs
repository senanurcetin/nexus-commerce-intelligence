import {METHOD_NAMES,selectForecast,forecastSummary,ratingScenario,ratingBounds,csv,forecastSvg} from './research-metrics.mjs';
const $=id=>document.getElementById(id);
const number=(value,digits=2)=>new Intl.NumberFormat('en-US',{maximumFractionDigits:digits,minimumFractionDigits:digits}).format(value);
const pct=value=>value===null?'Not estimable':number(value*100,1)+'%';
const node=(tag,text,className)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;};
let data,displayed=[];
function renderForecast(){
  displayed=selectForecast(data.forecast.rows,$('method').value,Number($('window').value));
  const s=forecastSummary(displayed);$('forecast-metrics').replaceChildren();
  if(!s){$('forecast-chart').textContent='No forecasts in this selection.';return;}
  for(const [label,value,note] of [['Mean absolute error',number(s.mae),'Orders/day across '+s.days+' displayed days'],['Weighted absolute error',pct(s.wape),'Absolute error / displayed actual count'],['Days inside stored band',pct(s.dayCoverage),'Day coverage; not whole-week coverage']]){
    const card=node('div',undefined,'metric');card.append(node('span',label),node('strong',value),node('small',note));$('forecast-metrics').append(card);
  }
  // The SVG helper accepts only validated dates and finite numeric coordinates.
  $('forecast-chart').innerHTML=forecastSvg(displayed,$('bands').checked);
}
function renderReview(){
  const ql=Number($('q-late').value)/100,qo=Number($('q-on-time').value)/100;
  $('q-late-value').textContent=pct(ql);$('q-on-time-value').textContent=pct(qo);
  const value=ratingScenario(data.review.groups,ql,qo),bounds=ratingBounds(data.review.groups);
  $('scenario-value').textContent=(value>=0?'+':'')+number(value*100)+' pp';
  $('scenario-note').textContent='Late minus on-time under these assumptions. Full sharp range: '+number(bounds.low*100)+' to +'+number(bounds.high*100)+' pp. This range is not a confidence interval.';
  const {late,on_time:on}=data.review.groups;
  $('review-coverage').textContent='Observed within-window ratings: late '+late.observed.toLocaleString('en-US')+'/'+late.total.toLocaleString('en-US')+' ('+pct(late.observed/late.total)+'); on-time '+on.observed.toLocaleString('en-US')+'/'+on.total.toLocaleString('en-US')+' ('+pct(on.observed/on.total)+').';
}
function selectStudy(id,focus=false){
  const study=data.studies.find(s=>s.id===id);if(!study)return;
  for(const button of $('study-tabs').children){const active=button.dataset.study===id;button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;if(active&&focus)button.focus();}
  $('study-panel').setAttribute('aria-labelledby','tab-'+id);
  for(const key of ['question','population','finding','decision','methods','limits'])$(key).textContent=study[key];
  $('case-title').textContent=study.title;$('report-link').href=study.report;$('receipt-link').href=study.receipt;
  $('forecast-lab').hidden=id!=='forecast';$('review-lab').hidden=id!=='review';
  $('figures').replaceChildren();
  for(const path of study.figures){
    const figure=node('figure'),img=node('img');img.src=path;img.alt=study.title+' — '+path.split('/').at(-1).replace('.png','').replaceAll('_',' ');img.loading='lazy';
    const caption=node('figcaption',study.population+' '+study.limits);figure.append(img,caption);$('figures').append(figure);
  }
  const hash='#'+id;if(location.hash!==hash)history.replaceState(null,'',hash);
}
function benchmark(){
  const head=node('thead'),row=node('tr');for(const text of ['Method','MAE / day','WAPE','Week coverage','Mean width','Interval score']){const th=node('th',text);th.scope='col';row.append(th);}head.append(row);
  const body=node('tbody');for(const m of data.forecast.metrics){const tr=node('tr');for(const value of [METHOD_NAMES[m.method],number(m.mae),pct(m.wape),pct(m.week_coverage),number(m.mean_width),number(m.interval_score)])tr.append(node('td',value));body.append(tr);}
  $('benchmark').replaceChildren(head,body);
}
async function start(){
  const response=await fetch('./data.json',{cache:'no-cache'});if(!response.ok)throw new Error('Research evidence is unavailable');data=await response.json();
  if(data.provenance!=='historical_public_olist'||data.synthetic!==false||data.studies.length!==5)throw new Error('Unexpected research provenance');
  for(const study of data.studies){const button=node('button',study.title);button.type='button';button.id='tab-'+study.id;button.dataset.study=study.id;button.setAttribute('role','tab');button.setAttribute('aria-controls','study-panel');button.addEventListener('click',()=>selectStudy(study.id));$('study-tabs').append(button);}
  $('study-tabs').addEventListener('keydown',event=>{const tabs=[...$('study-tabs').children],current=tabs.indexOf(document.activeElement);if(current<0)return;let index;
    if(event.key==='ArrowRight')index=(current+1)%tabs.length;else if(event.key==='ArrowLeft')index=(current-1+tabs.length)%tabs.length;else if(event.key==='Home')index=0;else if(event.key==='End')index=tabs.length-1;else return;
    event.preventDefault();selectStudy(tabs[index].dataset.study,true);
  });
  for(const [key,label] of Object.entries(METHOD_NAMES)){const option=node('option',label);option.value=key;$('method').append(option);}$('method').value='past_mae_selector';
  for(const id of ['method','window','bands'])$(id).addEventListener('change',renderForecast);
  for(const id of ['q-late','q-on-time'])$(id).addEventListener('input',renderReview);
  $('observed-assumption').addEventListener('click',()=>{for(const [id,g] of [['q-late',data.review.groups.late],['q-on-time',data.review.groups.on_time]]){const input=$(id);input.step='any';input.value=String(100*g.poor/g.observed);}renderReview();});
  $('download-forecast').addEventListener('click',()=>{const blob=new Blob([csv(displayed)],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),link=node('a');link.href=url;link.download='nexus-displayed-forecast.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),0);});
  renderForecast();renderReview();benchmark();
  const requested=location.hash.slice(1);selectStudy(data.studies.some(s=>s.id===requested)?requested:'forecast');
  $('status').textContent=data.source_orders.toLocaleString('en-US')+' public-source orders · Five separate study populations · Aggregate evidence only';
}
start().catch(error=>{$('status').textContent='Research could not be loaded. Serve this folder over local HTTP; inspect the downloadable evidence separately.';console.error(error.message);});
