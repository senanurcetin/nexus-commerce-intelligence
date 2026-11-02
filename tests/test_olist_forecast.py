"""Temporal leakage, independent ridge solution, interval ranks and raw target."""
import json
from pathlib import Path
import tempfile
import unittest

import duckdb
import numpy as np
import pandas as pd

from scripts.olist_forecast import (ROOT,SQL,PROTOCOL,MODELS,SELECTOR,design,predictions,
    calibration_radius,interval_score,block_interval,backtest,load_series)
from scripts.advanced_olist import sha256


class ForecastMethods(unittest.TestCase):
    def history(self):
        idx=pd.date_range('2017-01-01',periods=267)
        return pd.Series(30+np.arange(267)/5+idx.dayofweek*3,index=idx)

    def test_ridge_agrees_with_independent_augmented_least_squares(self):
        history=self.history();future=pd.date_range(history.index[-1]+pd.Timedelta(days=1),periods=7)
        p=predictions(history,future);x=design(history.index[-180:],history.index[-1])
        augmentation=np.diag(np.sqrt([0]+[10]*7))
        coef=np.linalg.lstsq(np.vstack([x,augmentation]),np.r_[history.values[-180:],np.zeros(8)],rcond=None)[0]
        np.testing.assert_allclose(p['ridge_calendar_180'],np.maximum(0,design(future,history.index[-1])@coef),atol=1e-9)
        np.testing.assert_array_equal(p['seasonal_naive'],history.values[-7:])
        np.testing.assert_allclose(p['weekday_mean_28'],np.array([history.values[-28:][i::7].mean() for i in range(7)]))

    def test_date_precision_does_not_create_a_false_calendar_gap(self):
        history=self.history();future=pd.date_range(history.index[-1]+pd.Timedelta(days=1),periods=7)
        expected=predictions(history,future)
        history.index=history.index.astype('datetime64[us]')
        for key,value in predictions(history,future).items():np.testing.assert_allclose(value,expected[key])
        with self.assertRaises(ValueError):predictions(history.iloc[:-1],future)
        with self.assertRaises(ValueError):predictions(history.drop(history.index[10]),future)

    def test_upper_rank_does_not_interpolate_or_invent_tiny_sample_intervals(self):
        self.assertIsNone(calibration_radius([]));self.assertIsNone(calibration_radius(range(8)))
        self.assertEqual(calibration_radius(range(12)),11)
        with self.assertRaises(ValueError):calibration_radius([float('nan')])

    def test_interval_score_penalizes_misses_and_width(self):
        np.testing.assert_allclose(interval_score([5,-1,11],[0,0,0],[10,10,10]),[10,30,30])
        with self.assertRaises(ValueError):interval_score([1],[2],[0])

    def test_paired_block_bootstrap_preserves_constant_gain_and_rejects_invalid_blocks(self):
        a=block_interval(np.repeat(3.,30),block=4,iterations=100,seed=2)
        self.assertEqual((a['ci_low'],a['ci_high']),(3.,3.))
        self.assertEqual(a,block_interval(np.repeat(3.,30),block=4,iterations=100,seed=2))
        with self.assertRaises(ValueError):block_interval([1,2],block=4)


class ChronologyContracts(unittest.TestCase):
    def fixture(self):
        idx=pd.date_range('2017-01-01','2018-04-01')
        series=pd.Series(50+idx.dayofweek*5+np.arange(len(idx))%11,index=idx)
        plan=json.loads(PROTOCOL.read_text());plan['bootstrap_iterations']=100
        return series,plan

    def test_poisoning_future_outcomes_cannot_change_an_earlier_forecast_choice_or_band(self):
        series,plan=self.fixture();first=backtest(series,plan)['forecast_daily']
        cutoff=pd.Timestamp('2018-02-12');series.loc[cutoff:]+=10000
        changed=backtest(series,plan)['forecast_daily']
        cols=['origin','method','prediction','lower','upper','chosen_model','mase_scale']
        pd.testing.assert_frame_equal(first[first.origin<=cutoff][cols].reset_index(drop=True),changed[changed.origin<=cutoff][cols].reset_index(drop=True))
        self.assertTrue((changed.training_end<changed.origin).all())
        self.assertTrue((changed.calibration_end.dropna()<changed.loc[changed.calibration_end.notna(),'origin']).all())

    def test_every_selector_choice_uses_completed_past_folds_and_not_current_week_error(self):
        series,plan=self.fixture();tables=backtest(series,plan);folds=tables['forecast_folds']
        for row in folds[folds.method==SELECTOR].itertuples():
            past=folds[(folds.end<row.origin)&folds.method.isin(MODELS)]
            scores={m:past[past.method==m].tail(12).mae.mean() for m in MODELS}
            expected=min(MODELS,key=lambda m:(scores[m],MODELS.index(m))) if not past.empty else 'seasonal_naive'
            self.assertEqual(row.chosen_model,expected)
        daily=tables['forecast_daily'];evaluation=daily[daily.phase=='evaluation']
        self.assertFalse(evaluation[['lower','upper']].isna().any().any())
        self.assertTrue(daily[(daily.phase=='calibration')&(daily.origin==daily.origin.min())].lower.isna().all())

    def test_zero_training_scale_stays_unavailable_instead_of_becoming_perfect_skill(self):
        series,plan=self.fixture();series[:]=0
        tables=backtest(series,plan)
        self.assertTrue(tables['forecast_metrics'].mase.isna().all())
        self.assertTrue(tables['forecast_metrics'].wape.isna().all())

    def test_target_keeps_cancelled_undelivered_and_itemless_orders_and_calendar_zeros(self):
        con=duckdb.connect()
        try:
            con.execute("create table raw_orders(order_purchase_timestamp timestamp,order_status varchar); insert into raw_orders values ('2017-01-01','canceled'),('2017-01-01','delivered'),('2017-01-03','unavailable')")
            with tempfile.TemporaryDirectory() as directory:
                raw=Path(directory);(raw/'olist_orders_dataset.csv').write_text('order_purchase_timestamp\n2017-01-01 00:00:00\n2017-01-01 00:00:00\n2017-01-03 00:00:00\n')
                series,_=load_series(con,raw,{'series_start':'2017-01-01','series_end_exclusive':'2017-01-04'})
                self.assertEqual(series.tolist(),[2,0,1])
        finally:con.close()

    def test_committed_forecasts_reconcile_metrics_and_implementation_fingerprints(self):
        folder=ROOT/'docs/advanced-analysis';e=json.loads((folder/'forecast_evidence.json').read_text())
        self.assertEqual(e['protocol_sha256'],sha256(PROTOCOL));self.assertEqual(e['implementation_sha256'],sha256(ROOT/'scripts/olist_forecast.py'))
        self.assertEqual(e['query_sha256'],sha256(SQL/'daily_order_volume.sql'))
        for file,digest in e['aggregate_sha256'].items():self.assertEqual(sha256(folder/file),digest)
        daily=pd.read_csv(folder/'forecast_daily.csv');metrics=pd.read_csv(folder/'forecast_metrics.csv')
        for row in metrics.itertuples():
            d=daily[(daily.phase=='evaluation')&(daily.method==row.method)];err=(d.actual_orders-d.prediction).abs()
            self.assertAlmostEqual(row.mae,err.mean(),places=8)
            self.assertAlmostEqual(row.wape,err.sum()/d.actual_orders.sum(),places=8)
        self.assertEqual(e['evaluation_days'],210);self.assertEqual(e['unscored_tail_days'],2)


if __name__=='__main__':unittest.main()
