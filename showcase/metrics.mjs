export function between(rows, start, end, field = 'date') {
  return rows.filter(row => row[field] >= start && row[field] <= end);
}

export function sum(rows, key) {
  return rows.reduce((total, row) => total + (Number.isFinite(row[key]) ? row[key] : 0), 0);
}

export function ratio(numerator, denominator) {
  return denominator > 0 ? numerator / denominator : null;
}

export function datePosition(day, start, end) {
  const first = Date.parse(start + 'T00:00:00Z');
  const last = Date.parse(end + 'T00:00:00Z');
  return last === first ? 0.5 : (Date.parse(day + 'T00:00:00Z') - first) / (last - first);
}

export function summarize(source, rows, sessions = []) {
  if (!rows.length) return [];
  if (source === 'ecommerce') {
    const revenue = sum(rows, 'completed_revenue');
    const orders = sum(rows, 'completed_orders');
    return [
      {label: 'Completed line revenue', value: revenue, unit: 'source units', note: 'Current complete status; returned lines excluded'},
      {label: 'Completed order-days', value: orders, unit: 'order-days', note: 'Sum of daily distinct orders; not period-unique'},
      {label: 'Revenue per order-day', value: ratio(revenue, orders), unit: 'source units', note: 'Completed revenue / completed order-days'},
      {label: 'Session conversion', value: ratio(sum(sessions, 'converted_sessions'), sum(sessions, 'sessions')), unit: 'percent', note: 'Converted sessions / all historical sessions'},
    ];
  }
  return [
    {label: 'Revenue', value: sum(rows, 'revenue'), unit: 'source units', note: 'Greenweez finance mart only'},
    {label: 'Transactions', value: sum(rows, 'transactions'), unit: 'orders', note: 'Greenweez daily order count'},
    {label: 'Advertising cost', value: sum(rows, 'ads_cost'), unit: 'source units', note: 'Paid platforms; no order attribution inferred'},
    {label: 'Margin after advertising', value: sum(rows, 'ads_margin'), unit: 'source units', note: 'Operational margin less advertising cost'},
  ];
}

export function csv(rows) {
  if (!rows.length) return '';
  const keys = Object.keys(rows[0]);
  const quote = value => '"' + String(value ?? '').replaceAll('"', '""') + '"';
  return [keys, ...rows.map(row => keys.map(key => row[key]))].map(row => row.map(quote).join(',')).join('\r\n');
}
