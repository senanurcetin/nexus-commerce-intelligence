"""Chronological source availability, integrity and no-latest-fallback controls."""
import csv
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scripts import core_source_history as h
from scripts import profile_core_source as prof


class SourceHistory(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        self.root=Path(directory.name);self.patch=patch.object(h,'PRIVATE_ROOT',self.root)
        self.patch.start();self.addCleanup(self.patch.stop)
        self.contract=json.loads(h.CONTRACT.read_text())

    def snapshot(self,name='first',observed='2026-11-02T14:00:00Z'):
        folder=self.root/name;folder.mkdir()
        tables={}
        for alias,fields in self.contract['tables'].items():
            p=folder/(alias+'.csv')
            with p.open('w',newline='') as stream:
                w=csv.writer(stream);w.writerow(fields);w.writerow(['1']*len(fields))
            tables[alias]={'columns':[{'name':f,'type':'STRING'} for f in fields],
                          'rows':1,'csv_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        receipt={'status':'complete_observed_snapshot','query_jobs_created':0,'storage_read_api_used':False,
            'publication_allowed':False,'origin_classification':self.contract['origin_classification'],
            'contract_sha256':hashlib.sha256(h.CONTRACT.read_bytes()).hexdigest(),
            'observed_at_utc':observed,'tables':tables}
        (folder/'receipt.json').write_text(json.dumps(receipt))
        return folder

    def register(self,folder,at='2026-11-03T00:00:00Z'):
        with patch.object(h,'now',return_value=at):return h.register(folder)

    def test_registration_does_not_backdate_to_source_observation_or_business_time(self):
        folder=self.snapshot();entry=self.register(folder)
        self.assertEqual(entry['available_at_utc'],'2026-11-03T00:00:00.000000+00:00')
        self.assertIsNone(h.resolve_as_of('2021-10-15T23:59:59Z'))
        self.assertIsNone(h.resolve_as_of('2026-11-02T15:00:00Z'))
        self.assertEqual(h.resolve_as_of(entry['available_at_utc'])[0],folder.resolve())

    def test_versions_select_latest_eligible_whole_snapshot_and_normalize_offsets(self):
        first=self.snapshot();self.register(first)
        second=self.snapshot('second','2026-11-03T01:00:00Z');self.register(second,'2026-11-03T02:00:00Z')
        self.assertEqual(h.require_as_of('2026-11-03T04:00:00+03:00')[0],first.resolve())
        self.assertEqual(h.require_as_of('2026-11-03T05:00:00+03:00')[0],second.resolve())
        self.assertEqual(len(h.history()),2)

    def test_missing_or_ineligible_history_never_falls_back_to_latest(self):
        folder=self.snapshot();(self.root/'latest.json').write_text(json.dumps({'snapshot':folder.name}))
        with self.assertRaisesRegex(ValueError,'fallback is forbidden'):h.require_as_of('2026-11-03T00:00:00Z')
        self.assertFalse(h.database().exists())

    def test_naive_invalid_and_date_only_cutoffs_are_rejected(self):
        for at in ('2026-11-03','2026-11-03T01:00:00','invalid',None):
            with self.subTest(at=at),self.assertRaises(ValueError):h.resolve_as_of(at)

    def test_idempotent_registration_preserves_original_availability(self):
        folder=self.snapshot();entry=self.register(folder)
        self.assertEqual(self.register(folder,'2026-11-04T00:00:00Z'),entry)
        self.assertEqual(len(h.history()),1)

    def test_future_observation_rejected_without_creating_history(self):
        with self.assertRaisesRegex(ValueError,'future source observation'):
            self.register(self.snapshot(observed='2026-11-04T00:00:00Z'))
        self.assertFalse(h.database().exists())

    def test_clock_regression_rolls_back_new_registration(self):
        self.register(self.snapshot())
        second=self.snapshot('second','2026-11-02T15:00:00Z')
        with self.assertRaisesRegex(ValueError,'clock precedes'):self.register(second,'2026-11-02T23:00:00Z')
        self.assertEqual(len(h.history()),1)

    def test_edited_selected_csv_is_rejected(self):
        folder=self.snapshot();self.register(folder)
        p=folder/'ecommerce.products.csv';p.write_bytes(p.read_bytes()+b'edited')
        with self.assertRaisesRegex(ValueError,'file hash mismatch'):h.require_as_of('2026-11-04T00:00:00Z')

    def test_edited_selected_receipt_is_rejected_even_if_projection_still_valid(self):
        folder=self.snapshot();self.register(folder)
        p=folder/'receipt.json';data=json.loads(p.read_text());data['observed_at_utc']='2026-11-02T15:00:00Z';p.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'registered receipt'):h.require_as_of('2026-11-04T00:00:00Z')

    def test_changed_entry_fails_integrity_check(self):
        self.register(self.snapshot())
        with closing(sqlite3.connect(h.database())) as con:
            con.execute("update snapshots set available_at='2021-01-01T00:00:00Z'");con.commit()
        with self.assertRaisesRegex(ValueError,'integrity'):h.history()

    def test_previously_published_anchor_detects_truncated_tail(self):
        self.register(self.snapshot());self.register(self.snapshot('second','2026-11-03T00:00:00Z'),'2026-11-04T00:00:00Z')
        anchor=h.public_status()
        with closing(sqlite3.connect(h.database())) as con:
            con.execute('delete from snapshots where sequence=2');con.commit()
        with self.assertRaisesRegex(ValueError,'anchor'):h.history(anchor=anchor)

    def test_private_boundary_and_public_projection(self):
        self.register(self.snapshot())
        status=h.public_status();text=json.dumps(status)
        for value in ('snapshot_directory','csv_sha256','source_contract_sha256','ecommerce.products'):
            self.assertNotIn(value,text)
        with self.assertRaisesRegex(ValueError,'must remain'):h.database(self.root.parent/'outside.sqlite3')

    def test_profile_rejects_unavailable_cutoff_before_loading_or_overwriting_output(self):
        folder=self.snapshot();out=folder/'analysis';out.mkdir();marker=out/'profile.json';marker.write_text('previous retrospective result')
        with patch.object(prof,'PRIVATE_ROOT',self.root),patch.object(prof,'load') as load:
            with self.assertRaisesRegex(ValueError,'fallback is forbidden'):prof.profile(folder,as_of='2021-10-15T00:00:00Z')
            load.assert_not_called()
        self.assertEqual(marker.read_text(),'previous retrospective result')

    def test_copied_identical_receipt_cannot_create_a_new_version_or_directory_binding(self):
        self.register(self.snapshot())
        with self.assertRaisesRegex(ValueError,'another private directory'):self.register(self.snapshot('copy'))
        self.assertEqual(len(h.history()),1)

    def test_concurrent_same_snapshot_registration_is_atomic_and_idempotent(self):
        folder=self.snapshot()
        with patch.object(h,'now',return_value='2026-11-03T00:00:00Z'),ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(h.register,[folder,folder]))
        self.assertEqual(results[0],results[1]);self.assertEqual(len(h.history()),1)


if __name__=='__main__':unittest.main()
