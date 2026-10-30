import test from 'node:test';
import assert from 'node:assert/strict';
import {between, ratio, summarize, csv, datePosition} from '../metrics.mjs';

test('inclusive filtering preserves a real empty period',()=>{
  const rows=[{date:'2024-01-01'},{date:'2024-01-02'}];
  assert.deepEqual(between(rows,'2024-01-01','2024-01-01'),[rows[0]]);
  assert.deepEqual(between(rows,'2025-01-01','2025-01-02'),[]);
});
test('conversion is weighted and missing denominators stay missing',()=>{
  const metrics=summarize('ecommerce',[{completed_revenue:400,completed_orders:4}],[{sessions:2,converted_sessions:1},{sessions:98,converted_sessions:4}]);
  assert.equal(metrics[2].value,100);
  assert.equal(metrics[3].value,0.05);
  assert.equal(ratio(0,0),null);
  assert.deepEqual(summarize('ecommerce',[]),[]);
});
test('margin may be negative; Greenweez has no E-Commerce revenue',()=>{
  const metrics=summarize('greenweez',[{revenue:100,transactions:2,ads_cost:120,ads_margin:-30,completed_revenue:99999}]);
  assert.equal(metrics[0].value,100);
  assert.equal(metrics[3].value,-30);
});
test('CSV quotes commas and embedded double quotes',()=>{
  assert.equal(csv([{label:'a,"b"',value:0}]),'"label","value"\r\n"a,""b""","0"');
});

test('irregular observation dates preserve actual temporal distance',()=>{
  assert.equal(datePosition('2024-01-02','2024-01-01','2024-01-11'),0.1);
  assert.equal(datePosition('2024-01-11','2024-01-01','2024-01-11'),1);
  assert.equal(datePosition('2024-01-01','2024-01-01','2024-01-01'),0.5);
});
