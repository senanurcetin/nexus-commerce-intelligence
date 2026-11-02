"""Execute analytical SQL against adversarial DuckDB session fixtures."""
from pathlib import Path
import unittest
import duckdb

ROOT = Path(__file__).resolve().parents[1]


class OrderedFunnelTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect()
        self.con.execute("create table events(session_id varchar, user_id int, event_type varchar, event_created_at timestamp, sequence_number int, event_id int)")
        self.con.execute("create table sessions(session_id varchar, user_id int, channel_group varchar)")
        self.sql = (ROOT / "analyses/conversion_funnel.sql").read_text(encoding="utf-8-sig").replace(
            "{{ ref('int_events_enriched') }}", "events").replace(
            "{{ ref('fct_marketing_web_performance') }}", "sessions")

    def tearDown(self):
        self.con.close()

    def add(self, session, user, types, channel="Organic"):
        self.con.execute("insert into sessions values (?,?,?)", [session,user,channel])
        self.con.executemany("insert into events values (?,?,?,cast(? as timestamp),?,?)", [
            (session,user,event,"2026-01-01 12:00:00",i,i) for i,event in enumerate(types)
        ])

    def result(self):
        result = self.con.execute(self.sql)
        return [dict(zip([c[0] for c in result.description], row)) for row in result.fetchall()]

    def test_shared_session_id_does_not_join_different_users(self):
        self.add("shared",1,["page_view","cart","purchase"])
        self.add("shared",2,["page_view"])
        row=self.result()[0]
        self.assertEqual((row["total_sessions"],row["page_view_sessions"],row["cart_sessions"],row["purchase_sessions"]),(2,2,1,1))
        self.assertEqual(row["overall_cvr_pct"],50)

    def test_events_must_follow_the_required_sequence(self):
        self.add("reverse",1,["purchase","cart","page_view"])
        self.add("retry",2,["cart","page_view","cart","purchase"])
        row=self.result()[0]
        self.assertEqual((row["cart_sessions"],row["purchase_sessions"]),(1,1))

    def test_anonymous_session_and_no_view_denominator(self):
        self.add("anonymous",None,["page_view","cart","purchase"],"Direct")
        self.add("purchase_only",1,["purchase"],"Paid")
        rows={row["channel_group"]:row for row in self.result()}
        self.assertEqual(rows["Direct"]["purchase_sessions"],1)
        self.assertEqual(rows["Paid"]["purchase_sessions"],0)
        self.assertIsNone(rows["Paid"]["overall_cvr_pct"])

    def test_multiple_events_cannot_count_one_session_twice(self):
        self.add("repeat",1,["page_view","page_view","cart","cart","purchase","purchase"])
        row=self.result()[0]
        self.assertEqual(row["purchase_sessions"],1)
        self.assertEqual(row["cart_to_purchase_pct"],100)


if __name__ == "__main__":
    unittest.main()
