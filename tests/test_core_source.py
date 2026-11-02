"""Offline adversarial checks for bounded source reads and financial populations."""
import csv
import hashlib
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb
from scripts import read_core_source as read
from scripts import profile_core_source as prof
from scripts import export_core_source_status as public
from scripts import build_observed_greenweez as build


def metadata(fields=('id',),rows=2):
    return {'type':'TABLE','etag':'stable','lastModifiedTime':'1','numRows':str(rows),
            'schema':{'fields':[{'name':f,'type':'STRING'} for f in fields]}}


def page(values,total=2,cursor=None):
    result={'totalRows':str(total),'rows':[{'f':[{'v':v} for v in row]} for row in values]}
    if cursor:result['pageToken']=cursor
    return result


class Reader:
    def __init__(self,pages):self.pages=iter(pages);self.calls=[]
    def get(self,path,params=None):self.calls.append((path,params));return next(self.pages)


class ReadTests(unittest.TestCase):
    def run_read(self,pages,rows=2,**kwargs):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'rows.csv';reader=Reader(pages)
            receipt=read.read_table(reader,'/table',metadata(rows=rows),[{'name':'id','type':'STRING'}],out,**kwargs)
            with out.open(newline='') as stream:rows=list(csv.reader(stream))
            return receipt,rows,reader.calls

    def test_pagination_and_null(self):
        result,rows,calls=self.run_read([page([['1']],cursor='next'),page([[None]])])
        self.assertEqual(result['rows'],2);self.assertEqual(rows,[['id'],['1'],['']])
        self.assertEqual(calls[1][1]['pageToken'],'next')

    def test_repeated_cursor(self):
        with self.assertRaisesRegex(ValueError,'repeated'):
            self.run_read([page([['1']],cursor='x'),page([['2']],cursor='x')])

    def test_incomplete_population(self):
        with self.assertRaisesRegex(ValueError,'before all'):
            self.run_read([page([['1']])])

    def test_changed_population(self):
        with self.assertRaisesRegex(ValueError,'changed'):
            self.run_read([page([['1']],total=3)])

    def test_nested_value_rejected(self):
        with self.assertRaisesRegex(ValueError,'shape'):
            self.run_read([page([[{'private':'nested'}]],total=1)],rows=1)

    def test_row_cap_and_page_cap(self):
        for kwargs in ({'maximum_rows':1},{'maximum_rows':250001},{'page_rows':10001},{'page_rows':0}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):self.run_read([],**kwargs)

    def test_schema_order_and_repeated_field(self):
        meta=metadata(('b','a'))
        self.assertEqual([f['name'] for f in read.fields_for(meta,['a','b'])],['b','a'])
        meta['schema']['fields'][0]['mode']='REPEATED'
        with self.assertRaises(ValueError):read.fields_for(meta,['a','b'])

    def test_url_allowlist_before_network(self):
        reader=read.RestReader('never-used')
        with patch.object(read,'urlopen') as network:
            for path in ('https://elsewhere','/projects/other/datasets/x/tables/y',read.source_path('ecommerce.products')+'/data?x=1'):
                with self.assertRaises(ValueError):reader.get(path)
            with self.assertRaises(ValueError):
                reader.get(read.source_path('ecommerce.products')+'/data',{'selectedFields':'name','maxResults':10})
            network.assert_not_called()

    def test_byte_budget(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,size):return b'x'*size
        reader=read.RestReader('never-used',maximum_bytes=5)
        with patch.object(read,'urlopen',return_value=Response()),self.assertRaisesRegex(ValueError,'budget exceeded'):
            reader.get(read.source_path('ecommerce.products'))

    def test_changed_snapshot_preserves_previous_pointer(self):
        contract=json.loads(read.CONTRACT.read_text());calls={}
        class ChangingReader:
            bytes_read=1;requests=1
            def get(self,path,params=None):
                alias=next(a for a in contract['tables'] if path.startswith(read.source_path(a)))
                if path.endswith('/data'):return page([],total=0)
                calls[alias]=calls.get(alias,0)+1
                meta=metadata(contract['tables'][alias],0)
                if calls[alias]>1:meta['etag']='changed'
                return meta
        with tempfile.TemporaryDirectory() as td,patch.object(read,'PRIVATE_ROOT',Path(td)):
            pointer=Path(td)/'latest.json';pointer.write_text('{"snapshot":"previous"}')
            with self.assertRaisesRegex(ValueError,'mixed-version'):read.snapshot(ChangingReader(),Path(td))
            self.assertEqual(json.loads(pointer.read_text())['snapshot'],'previous')
            self.assertEqual(list(Path(td).glob('snapshot-*')),[])


class FinanceTests(unittest.TestCase):
    def setUp(self):self.con=duckdb.connect()
    def tearDown(self):self.con.close()

    def ecommerce(self,products):
        self.con.execute('''create table "ecommerce.order_items" as select * from (values
            ('1','a','u','p','Complete','0','10'),('2','b','u','q','Complete','0','20'),
            ('3','c','u','p','Complete','0',NULL),('4','d','u','p','Complete','0','-1'))
            t(id,order_id,user_id,product_id,status,created_at,sale_price)''')
        self.con.execute('create table "ecommerce.products" (id varchar,cost varchar,category varchar)')
        self.con.executemany('insert into "ecommerce.products" values (?,?,?)',products)
        return prof.ecommerce(self.con)[0]

    def test_cost_denominator_uses_same_valid_population(self):
        result=self.ecommerce([('p','4','a'),('q',None,'a')])['completed_cost_coverage']
        self.assertEqual(result['eligible_cost_rows'],1)
        self.assertEqual(result['known_cost_completed_value'],10)
        self.assertEqual(result['known_cost_catalogue_contribution'],6)

    def test_duplicate_products_block_cost_join(self):
        result=self.ecommerce([('p','4','a'),('p','5','a')])
        self.assertFalse(result['cost_join_safe']);self.assertNotIn('completed_cost_coverage',result)

    def greenweez(self,shipping):
        self.con.execute('''create table "greenweez.gwz_finance_orders_orders" as select * from
            (values ('a','2021-01-01','100','40','5')) t(orders_id,datetime,turnover,purchase_cost,ship_fee)''')
        self.con.execute('create table "greenweez.gwz_finance_shipping_shipping" (orders_id varchar,date_date varchar,log_cost varchar,ship_cost varchar)')
        self.con.executemany('insert into "greenweez.gwz_finance_shipping_shipping" values (?,?,?,?)',shipping)
        self.con.execute('''create table "greenweez.gwz_finance_refund_sheet_1" as select * from
            (values ('a','2021-01-01','500')) t(orders_id,datetime,refund)''')
        return prof.greenweez(self.con)[0]

    def test_unknown_refund_never_subtracted(self):
        result=self.greenweez([('a','2021-01-01','2','3')])
        self.assertIsNone(result['net_revenue_after_refunds'])
        self.assertEqual(result['component_coverage']['complete_component_subtotal'],60)

    def test_date_mismatch_excluded(self):
        result=self.greenweez([('a','2021-01-02','2','3')])['component_coverage']
        self.assertEqual(result['complete_component_orders'],0)
        self.assertEqual(result['shipping_order_date_mismatches'],1)

    def test_missing_cost_excluded_not_zero(self):
        result=self.greenweez([('a','2021-01-01',None,'3')])['component_coverage']
        self.assertEqual(result['complete_component_orders'],0)

    def test_duplicate_shipping_blocks_join(self):
        result=self.greenweez([('a','2021-01-01','2','3')]*2)
        self.assertFalse(result['joins_safe']);self.assertNotIn('component_coverage',result)

    def test_independent_decimal_control(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'x.csv';path.write_text('value\n1.0000000005\n-1.0000000005\ninvalid\nNaN\n1e40\n2\n')
            self.assertEqual(prof.independent_sum(path,'value'),Decimal(2))

    def test_financial_contract_keeps_unknowns(self):
        domains=json.loads(prof.SEMANTICS.read_text())['domains']
        for domain in domains.values():self.assertIsNone(domain['currency']['value'])
        self.assertFalse(domains['greenweez']['refund']['subtract_from_turnover_allowed'])


class EvidenceTests(unittest.TestCase):
    def fixture(self):
        contract=json.loads(read.CONTRACT.read_text())
        receipt={'contract_sha256':hashlib.sha256(read.CONTRACT.read_bytes()).hexdigest(),
            'tables':{a:{'rows':2,'secret_row':'DO_NOT_PUBLISH'} for a in contract['tables']},
            'status':'complete_observed_snapshot','publication_allowed':False,'query_jobs_created':0,
            'storage_read_api_used':False,'response_bytes':100,'observed_at_utc':'2026-11-02T00:00:00+00:00',
            'origin_classification':contract['origin_classification']}
        analysis={'financial_contract_sha256':hashlib.sha256(prof.SEMANTICS.read_bytes()).hexdigest(),
            'snapshot_observed_at_utc':receipt['observed_at_utc'],'independent_raw_amount_reconciliation':True,
            'ecommerce':{'keys':{'products':{'unique_nonnull_keys':True}},'completed_value':'DO_NOT_PUBLISH'},
            'greenweez':{'keys':{'orders':{'rows':2}},'joins_safe':True,'turnover':'DO_NOT_PUBLISH'}}
        dbt={'source_orders':2,'refund_adjusted_net_revenue_remains_null':True,'node_status_counts':{'success':11,'pass':41,'warn':1}}
        return receipt,analysis,dbt

    def test_public_projection_excludes_private_values(self):
        result=public.project(*self.fixture())
        self.assertNotIn('DO_NOT_PUBLISH',json.dumps(result))
        self.assertFalse(result['gates']['currency_verified'])
        self.assertFalse(result['public_commerce_payload_replaced'])

    def test_mixed_profile_blocked(self):
        receipt,analysis,dbt=self.fixture();analysis['snapshot_observed_at_utc']='old'
        with self.assertRaisesRegex(ValueError,'Mixed'):public.project(receipt,analysis,dbt)

    def test_failed_or_wrong_population_build_blocked(self):
        for field,value in (('source_orders',3),('refund_adjusted_net_revenue_remains_null',False),('node_status_counts',{'error':1})):
            receipt,analysis,dbt=self.fixture();dbt[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):public.project(receipt,analysis,dbt)

    def test_source_budget_and_contract_mismatch_blocked(self):
        for field,value in (('response_bytes',100000001),('contract_sha256','old'),('storage_read_api_used',True)):
            receipt,analysis,dbt=self.fixture();receipt[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):public.project(receipt,analysis,dbt)

    def test_failed_rebuild_removes_previous_success_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);snapshot=root/'snapshot';out=snapshot/'analysis/dbt';out.mkdir(parents=True)
            receipt=out/'verified_build.json';receipt.write_text('{"old_success":true}')
            with patch.object(build,'PRIVATE_ROOT',root),patch.object(build,'profile',side_effect=ValueError('edited raw source')):
                with self.assertRaisesRegex(ValueError,'edited'):build.build(snapshot)
            self.assertFalse(receipt.exists())


if __name__=='__main__':unittest.main()
