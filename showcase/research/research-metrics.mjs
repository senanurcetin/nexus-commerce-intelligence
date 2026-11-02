export const METHOD_NAMES = Object.freeze({seasonal_naive:'Weekly repeat',weekday_mean_28:'Four-week weekday mean',ridge_calendar_180:'Calendar ridge · 180 days',past_mae_selector:'Past-error selector'});
const validDay = value => typeof value==='string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value+'T00:00:00Z')) && new Date(value+'T00:00:00Z').toISOString().slice(0,10)===value;
function validateRow(r){
  if(!validDay(r.day)||!Object.hasOwn(METHOD_NAMES,r.method)||!['actual_orders','prediction','lower','upper'].every(k=>Number.isFinite(r[k])&&r[k]>=0)||r.lower>r.upper)throw new Error('Invalid forecast observation');
}
export function selectForecast(rows,method,days=56){
  if(!Number.isInteger(days)||days<1)throw new Error('Positive day window required');
  const selected=rows.filter(r=>r.method===method).slice().sort((a,b)=>a.day.localeCompare(b.day));
  selected.forEach(validateRow);
  if(new Set(selected.map(r=>r.day)).size!==selected.length)throw new Error('Duplicate forecast dates');
  return selected.slice(-days);
}
export function forecastSummary(rows){
  if(!rows.length)return null;
  rows.forEach(validateRow);
  const total=rows.reduce((s,r)=>s+r.actual_orders,0),error=rows.reduce((s,r)=>s+Math.abs(r.actual_orders-r.prediction),0);
  return {days:rows.length,mae:error/rows.length,wape:total?error/total:null,
    dayCoverage:rows.filter(r=>r.actual_orders>=r.lower&&r.actual_orders<=r.upper).length/rows.length,
    meanWidth:rows.reduce((s,r)=>s+r.upper-r.lower,0)/rows.length};
}
function groupsValid(groups){
  for(const key of ['late','on_time']){
    const g=groups[key];if(!g||!['poor','observed','total'].every(k=>Number.isInteger(g[k])&&g[k]>=0)||g.total===0||g.poor>g.observed||g.observed>g.total)throw new Error('Invalid rating counts');
  }
}
export function ratingScenario(groups,qLate,qOnTime){
  groupsValid(groups);if(![qLate,qOnTime].every(q=>Number.isFinite(q)&&q>=0&&q<=1))throw new Error('Assumed probabilities must be between zero and one');
  const rate=(g,q)=>(g.poor+(g.total-g.observed)*q)/g.total;
  return rate(groups.late,qLate)-rate(groups.on_time,qOnTime);
}
export function ratingBounds(groups){return {low:ratingScenario(groups,0,1),high:ratingScenario(groups,1,0)};}
export function csv(rows){
  if(!rows.length)return '';
  const fields=['day','origin','method','actual_orders','prediction','lower','upper'];
  const quote=x=>'"'+String(x??'').replaceAll('"','""')+'"';
  return [fields,...rows.map(r=>fields.map(k=>r[k]))].map(row=>row.map(quote).join(',')).join('\r\n');
}
export function forecastSvg(rows,showBands=true){
  if(!rows.length)return '<p>No observations in this selection.</p>';
  rows.forEach(validateRow);
  const w=980,h=370,l=64,r=28,t=28,b=58,plotW=w-l-r,plotH=h-t-b;
  const first=Date.parse(rows[0].day+'T00:00:00Z'),last=Date.parse(rows.at(-1).day+'T00:00:00Z');
  const max=Math.max(1,...rows.flatMap(d=>showBands?[d.actual_orders,d.prediction,d.upper]:[d.actual_orders,d.prediction]));
  const x=d=>l+(last===first?.5:(Date.parse(d.day+'T00:00:00Z')-first)/(last-first))*plotW;
  const y=value=>t+plotH*(1-value/max);
  const line=key=>rows.map((d,i)=>(i?'L':'M')+x(d).toFixed(2)+','+y(d[key]).toFixed(2)).join(' ');
  const band=showBands?`<path d="${line('upper')} ${rows.slice().reverse().map(d=>'L'+x(d).toFixed(2)+','+y(d.lower).toFixed(2)).join(' ')} Z" fill="#8f9bff" fill-opacity=".22"/>`:'';
  const yticks=[0,1/3,2/3,1].map(f=>`<line x1="${l}" x2="${w-r}" y1="${y(max*f)}" y2="${y(max*f)}" stroke="#293448"/><text x="${l-10}" y="${y(max*f)+4}" text-anchor="end" fill="#a2afc2" font-size="11">${Math.round(max*f)}</text>`).join('');
  const xticks=[...new Set([0,Math.floor((rows.length-1)/3),Math.floor(2*(rows.length-1)/3),rows.length-1])].map(i=>`<text x="${x(rows[i])}" y="${h-28}" text-anchor="middle" fill="#a2afc2" font-size="11">${rows[i].day}</text>`).join('');
  return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-labelledby="forecast-svg-title forecast-svg-description"><title id="forecast-svg-title">Observed placed orders and recorded seven-day forecasts</title><desc id="forecast-svg-description">${rows.length} displayed days. White: observed placed orders. Cyan: point forecast. ${showBands?'Lavender: rolling reference band, without a temporal coverage guarantee.':'Reference band hidden.'} Exact values are available in the CSV export.</desc>${yticks}${band}<path d="${line('actual_orders')}" fill="none" stroke="#edf2f8" stroke-width="2"/><path d="${line('prediction')}" fill="none" stroke="#00e0ff" stroke-width="2"/>${xticks}<text x="${l}" y="16" fill="#a2afc2" font-size="11">Placed orders / day</text><text x="${w-r}" y="16" text-anchor="end" fill="#a2afc2" font-size="11">White: observed · Cyan: forecast${showBands?' · Lavender: reference band':''}</text></svg>`;
}
