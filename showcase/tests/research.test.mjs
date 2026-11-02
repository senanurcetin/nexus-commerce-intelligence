import test from 'node:test';
import assert from 'node:assert/strict';
import {selectForecast,forecastSummary,ratingScenario,ratingBounds,forecastSvg,csv} from '../research/research-metrics.mjs';
const row=(day,actual,prediction,lower=0,upper=100)=>({day,origin:'2018-01-01',method:'seasonal_naive',actual_orders:actual,prediction,lower,upper});
test('research summaries weight errors by actual volume and preserve absent denominators',()=>{
  const summary=forecastSummary([row('2018-01-01',1,2),row('2018-01-02',99,90)]);
  assert.equal(summary.mae,5);assert.equal(summary.wape,.1);assert.equal(summary.dayCoverage,1);
  assert.equal(forecastSummary([row('2018-01-01',0,0)]).wape,null);assert.equal(forecastSummary([]),null);
});
test('method and calendar-window selection cannot mix methods or mutate source rows',()=>{
  const rows=[row('2018-01-03',2,1),{...row('2018-01-01',100,1),method:'past_mae_selector'},row('2018-01-01',3,2),row('2018-01-02',4,3)];
  assert.deepEqual(selectForecast(rows,'seasonal_naive',2).map(r=>r.day),['2018-01-02','2018-01-03']);
  assert.equal(rows[0].day,'2018-01-03');assert.deepEqual(selectForecast(rows,'missing'),[]);
  assert.throws(()=>selectForecast([rows[0],rows[0]],'seasonal_naive'),/Duplicate/);
});
test('missing-rating scenario uses eligible orders rather than observed-rating denominators',()=>{
  const groups={late:{poor:1,observed:2,total:4},on_time:{poor:2,observed:3,total:5}};
  assert.ok(Math.abs(ratingScenario(groups,.5,2/3)-(1/2-2/3))<1e-12);
  const b=ratingBounds(groups);assert.equal(b.low,1/4-4/5);assert.equal(b.high,3/4-2/5);
  assert.throws(()=>ratingScenario(groups,1.1,.5));assert.throws(()=>ratingBounds({...groups,late:{poor:3,observed:2,total:4}}));
});
test('invalid dates and non-finite values cannot create chart markup',()=>{
  for(const day of ['2018-02-31','<script>','invalid'])assert.throws(()=>forecastSvg([row(day,1,2)]));
  assert.throws(()=>forecastSvg([row('2018-01-01',Infinity,2)]));
  assert.throws(()=>forecastSummary([row('2018-01-01',1,2,10,0)]));
});
test('chart preserves accessible uncertainty context and exports every selected observation',()=>{
  const rows=[row('2018-01-01',3,2),row('2018-01-03',4,3)];
  const svg=forecastSvg(rows);assert.match(svg,/role="img"/);assert.match(svg,/without a temporal coverage guarantee/);
  assert.match(svg,/2018-01-03/);assert.match(forecastSvg(rows,false),/Reference band hidden/);
  assert.equal(csv(rows).split('\r\n').length,3);assert.match(csv(rows),/"actual_orders"/);
});
