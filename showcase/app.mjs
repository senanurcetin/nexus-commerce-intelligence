import {between, sum, ratio, summarize, csv, datePosition} from './metrics.mjs';

const $ = id => document.getElementById(id);
const number = value => value === null ? '—' : new Intl.NumberFormat('en-US', {maximumFractionDigits: 2}).format(value);
let data, source = 'ecommerce', selected = [];

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function bounds() {
  const rows = source === 'ecommerce' ? data.sources.ecommerce.orders : data.sources.greenweez.daily;
  const dates = rows.map(row => row.date).sort();
  return [dates[0], dates.at(-1)];
}

function setDates() {
  const [start, end] = bounds();
  $('start').value = start; $('end').value = end;
  render();
}

function renderChart(rows, key) {
  const area = $('chart'); area.replaceChildren();
  if (!rows.length) {area.append(node('p', 'No observations in this date range.', 'empty')); return;}
  const NS = 'http://www.w3.org/2000/svg';
  const svgNode = (tag, attrs, text) => {
    const el = document.createElementNS(NS, tag);
    for (const [name, value] of Object.entries(attrs)) el.setAttribute(name, String(value));
    if (text !== undefined) el.textContent = text;
    return el;
  };
  const svg = svgNode('svg', {viewBox:'0 0 680 235', role:'img', 'aria-labelledby':'trend-description'});
  svg.append(svgNode('title', {id:'trend-description'}, 'Daily revenue in source units. All values are available in the ledger below.'));
  const values = rows.map(row => row[key]);
  const low = Math.min(0, ...values), high = Math.max(1, ...values);
  const x = index => 61 + datePosition(rows[index].date, rows[0].date, rows.at(-1).date) * 596;
  const y = value => 187 - ((value - low) / (high - low)) * 153;
  const defs = svgNode('defs', {}), gradient = svgNode('linearGradient', {id:'fade',x1:0,y1:0,x2:0,y2:1});
  gradient.append(svgNode('stop', {offset:'0%', 'stop-color':'#4edcec','stop-opacity':'.19'}),svgNode('stop', {offset:'100%', 'stop-color':'#4edcec','stop-opacity':'0'}));
  defs.append(gradient);svg.append(defs);
  for (let i=0; i<=3; i++) {
    const value = low + (high-low)*i/3, yy = y(value);
    svg.append(svgNode('line',{x1:61,y1:yy,x2:657,y2:yy,stroke:'#243044','stroke-dasharray':'3 5'}));
    svg.append(svgNode('text',{x:48,y:yy+3,fill:'#8599b3','font-size':9,'text-anchor':'end'},new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1}).format(value)));
  }
  const points = rows.map((row,i)=>`${x(i)},${y(row[key])}`).join(' ');
  svg.append(svgNode('polygon',{points:`${x(0)},${y(0)} ${points} ${x(rows.length-1)},${y(0)}`,fill:'url(#fade)'}));
  svg.append(svgNode('polyline',{points,fill:'none',stroke:'#62dce9','stroke-width':2.1,'stroke-linejoin':'round'}));
  rows.forEach((row,i) => {
    const circle = svgNode('circle',{cx:x(i),cy:y(row[key]),r:rows.length<40?3:1.5,fill:'#84e5ee'});
    circle.append(svgNode('title',{},`${row.date}: ${number(row[key])} source units`));svg.append(circle);
  });
  const ticks = [...new Set([0,Math.floor((rows.length-1)/2),rows.length-1])];
  ticks.forEach(i=>svg.append(svgNode('text',{x:x(i),y:218,fill:'#91a5bf','font-size':9,'text-anchor':'middle'},rows[i].date)));
  area.append(svg);
}

function insight(title, text) {
  const div = node('div', undefined, 'insight');div.append(node('strong',title),node('p',text));return div;
}

function render() {
  const start = $('start').value, end = $('end').value;
  const invalid = !start || !end || start>end;
  const domain = data.sources[source];
  selected = invalid ? [] : between(source==='ecommerce'?domain.orders:domain.daily,start,end);
  const sessions = source==='ecommerce' && !invalid ? between(domain.sessions,start,end):[];
  $('source-label').textContent = `${domain.label} / ${domain.origin}`;
  $('period').textContent = `${selected.length} observed days`;
  $('status').textContent = invalid ? 'Choose a valid date range. The start date must be on or before the end date.' : !selected.length ? 'No observations in this date range. Reset the dates to explore this source.' : '';
  $('download').disabled = selected.length===0;
  $('metrics').replaceChildren();
  for (const metric of summarize(source,selected,sessions)) {
    const card = node('article',undefined,'metric');
    const value = metric.unit==='percent' && metric.value!==null ? number(metric.value*100)+'%' : number(metric.value);
    card.append(node('div',metric.label,'metric-label'),node('div',value,'metric-value'),node('div',metric.unit==='percent'?'WEIGHTED RATE':metric.unit,'metric-unit'),node('div',metric.note,'metric-note'));
    $('metrics').append(card);
  }
  renderChart(selected,source==='ecommerce'?'completed_revenue':'revenue');
  $('insights').replaceChildren();
  if (source==='ecommerce') {
    const conversion = ratio(sum(sessions,'converted_sessions'),sum(sessions,'sessions'));
    $('insights').append(insight('Conversion is a session metric.',conversion===null?'No sessions are available in the selected period.':`${number(conversion*100)}% of historical sessions contain a conversion event. This is not evidence of completed payment.`),insight('Returns are already excluded.',`${number(sum(selected,'returned_line_revenue'))} source units of returned-line value are reported separately. Subtracting them again would understate completed revenue.`),insight('Keep attribution scoped.','Signup source, historical session source and GA4 acquisition are distinct dimensions.'));
  } else {
    const margin = ratio(sum(selected,'ads_margin'),sum(selected,'revenue'));
    $('insights').append(insight('Contribution after acquisition.',margin===null?'No revenue denominator is available.':`${number(margin*100)}% margin after advertising in this synthetic finance example. This is not audited net profit.`),insight('Spend does not imply attribution.','Campaign spend is not joined to individual orders. The report does not claim incremental ROAS or customer acquisition cost.'),insight('One domain at a time.','Greenweez finance is never added to historical E-Commerce revenue.'));
  }
  const keys = source==='ecommerce' ? ['date','completed_orders','completed_revenue','returned_orders','returned_line_revenue'] : ['date','transactions','revenue','operational_margin','ads_cost','ads_margin'];
  const labels = source==='ecommerce' ? ['Date','Completed order-days','Completed revenue','Returned order-days','Returned-line value'] : ['Date','Transactions','Revenue','Operational margin','Ad cost','Margin after ads'];
  const head = node('thead'), header = node('tr'); labels.forEach(label=>{const th=node('th',label);th.scope='col';header.append(th);});head.append(header);
  const body=node('tbody');
  selected.forEach(row=>{const tr=node('tr');keys.forEach(key=>tr.append(node('td',key==='date'?row[key]:number(row[key]))));body.append(tr);});
  $('ledger').replaceChildren(head,body);
}

async function init() {
  try {
    const response = await fetch('./data.json');
    if (!response.ok) throw new Error('data unavailable');
    data = await response.json();
    if (data.version!==1 || data.sources?.ecommerce?.origin!=='synthetic_ci' || data.sources?.greenweez?.origin!=='synthetic_demo') throw new Error('unsupported data contract');
    document.querySelectorAll('[data-source]').forEach(button=>button.addEventListener('click',()=>{
      source=button.dataset.source;
      document.querySelectorAll('[data-source]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
      setDates();
    }));
    ['start','end'].forEach(id=>$(id).addEventListener('change',render));
    $('reset').addEventListener('click',setDates);
    $('download').addEventListener('click',()=>{
      const url=URL.createObjectURL(new Blob([csv(selected)],{type:'text/csv;charset=utf-8'}));
      const a=node('a');a.href=url;a.download=`nexus-${source}-synthetic-${$('start').value}-${$('end').value}.csv`;a.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    });
    setDates();
  } catch {
    $('status').textContent='Demonstration data is unavailable. Build the showcase from both synthetic dbt projects and serve the generated folder over HTTP.';
    $('download').disabled=true;
  }
}
await init();
