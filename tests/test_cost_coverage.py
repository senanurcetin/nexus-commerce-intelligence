"""Coverage-aware contribution: aligned denominators, null costs and grain."""
from pathlib import Path
import tempfile
import unittest

import duckdb

from scripts.run_analysis import ROOT, cost_diagnostics, execute_analysis


class EcommerceCostCoverage(unittest.TestCase):
    def setUp(self):
        self.con=duckdb.connect()
        self.con.execute('create table fact(order_item_id int,order_id int,category varchar,revenue double,is_completed_order int)')
        self.con.execute('create table enriched(order_item_id int,order_id int,cost double)')

    def tearDown(self):self.con.close()

    def query(self):
        return execute_analysis(self.con,ROOT/'analyses/completed_product_contribution.sql',references={
            'fct_order_marketing':'fact','int_orders_enriched':'enriched'})

    def test_unpriced_revenue_is_not_in_the_known_cost_margin_denominator(self):
        self.con.execute("insert into fact values (1,1,'A',100,1),(2,1,'A',100,1),(3,2,'A',0,0)")
        self.con.execute('insert into enriched values (1,1,60),(2,1,NULL),(3,2,10)')
        r=self.query()[0]
        self.assertEqual(r['completed_lines'],2)
        self.assertEqual(r['completed_revenue'],200)
        self.assertEqual(r['unknown_cost_completed_revenue'],100)
        self.assertEqual(r['known_cost_product_contribution'],40)
        self.assertEqual(r['known_cost_margin_pct'],40)  # 40/100, never 40/200.
        self.assertEqual(r['cost_revenue_coverage_pct'],50)

    def test_invalid_or_absent_cost_does_not_become_free_inventory(self):
        self.con.execute("insert into fact values (1,1,NULL,50,1),(2,2,NULL,100,1)")
        self.con.execute('insert into enriched values (1,1,-5)')
        r=self.query()[0]
        self.assertEqual(r['category'],'Unknown category')
        self.assertEqual(r['cost_revenue_coverage_pct'],0)
        self.assertIsNone(r['known_cost_product_contribution'])
        self.assertIsNone(r['known_cost_margin_pct'])

    def test_empty_or_zero_value_denominator_remains_unestimable(self):
        self.assertEqual(self.query(),[])
        self.con.execute("insert into fact values (1,1,'A',0,1)")
        self.con.execute('insert into enriched values (1,1,5)')
        r=self.query()[0]
        self.assertIsNone(r['known_cost_margin_pct']);self.assertIsNone(r['cost_revenue_coverage_pct'])

    def test_raw_control_rejects_many_side_fanout_before_other_domain_export(self):
        self.con.execute("insert into fact values (1,1,'A',100,1),(2,1,'A',100,1)")
        self.con.execute('insert into enriched values (1,1,60),(1,1,60),(2,1,NULL)')
        rows=self.query()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'target').mkdir()
            con=duckdb.connect(str(root/'target/ci.duckdb'))
            con.execute('''create schema analytics;
                create table analytics.products(id int,cost double);
                insert into analytics.products values (1,60),(2,NULL);
                create table analytics.order_items(product_id int,status varchar,sale_price double,user_id int);
                insert into analytics.order_items values (1,'complete',100,1),(2,'complete',100,1)''')
            con.close()
            with self.assertRaisesRegex(ValueError,'raw item/product keys'):cost_diagnostics(root,rows)


class GreenweezCostCoverage(unittest.TestCase):
    def test_partial_orders_and_null_shipping_are_not_complete_components(self):
        con=duckdb.connect()
        try:
            con.execute('''create table sales(orders_id int,date_date date,products_id int,revenue double,quantity int);
                insert into sales values (1,'2026-01-01',10,100,1),(1,'2026-01-01',999,50,1),
                    (2,'2026-01-01',999,30,1),(3,'2026-01-01',10,40,1),(4,'2026-01-01',10,60,1);
                create table product(products_id int,purchase_price double);insert into product values (10,20);
                create table ship(orders_id int,shipping_fee double,log_cost double,ship_cost double);
                insert into ship values (1,5,2,3),(3,5,NULL,2),(4,0,0,0);
                create table operational(orders_id int,date_date date,revenue double,margin double,operational_margin double);
                insert into operational values (1,'2026-01-01',150,80,80),(2,'2026-01-01',30,NULL,0),
                    (3,'2026-01-01',40,20,23),(4,'2026-01-01',60,40,40)''')
            rows=execute_analysis(con,ROOT/'integrations/greenweez/analyses/cost_coverage.sql',references={
                'stg_raw__sales':'sales','stg_raw__product':'product','stg_raw__ship':'ship','int_orders_operational':'operational'})
            self.assertEqual(sum(r['orders'] for r in rows),4)
            self.assertEqual(sum(r['revenue'] for r in rows),280)
            self.assertEqual(sum(r['unknown_cost_line_revenue'] for r in rows),80)
            self.assertEqual(sum(r['known_cost_product_contribution'] or 0 for r in rows),140)
            self.assertEqual(sum(r['complete_components_operational_margin'] or 0 for r in rows),40)
            unpriced=next(r for r in rows if r['product_cost_coverage']=='unpriced')
            self.assertIsNone(unpriced['known_cost_product_contribution'])
            self.assertIsNone(unpriced['complete_components_operational_margin'])
        finally:con.close()


if __name__=='__main__':unittest.main()
