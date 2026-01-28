import json
import unittest
from datetime import datetime, timezone


class TestSchedulingTimezoneWindow(unittest.TestCase):
    def _compute(self, now_utc: datetime) -> dict:
        # Import lazily so tests don't require app bootstrapping.
        from airline.scheduling import compute_call_availability_status

        self.assertIsNotNone(now_utc.tzinfo)
        out = compute_call_availability_status(now_utc)
        # Must be JSON serializable (tool returns json.dumps of this)
        json.dumps(out)
        return out

    def test_summer_dst_israel_open_and_midnight_crossing(self):
        # Israel is typically UTC+3 in summer. Example: 2026-06-01 11:00 Israel ~= 08:00 UTC.
        # Guatemala is UTC-6 year-round. 20:00 Guatemala ~= 02:00 UTC next day.
        out_open = self._compute(datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(out_open["customer_service"], "open")

        out_open_late = self._compute(datetime(2026, 6, 2, 1, 59, tzinfo=timezone.utc))
        self.assertEqual(out_open_late["customer_service"], "open")

        out_closed = self._compute(datetime(2026, 6, 2, 2, 1, tzinfo=timezone.utc))
        self.assertEqual(out_closed["customer_service"], "currently_closed")
        self.assertIn("service will resume", out_closed["service_opens"])

    def test_winter_israel_open_boundary(self):
        # Israel is typically UTC+2 in winter. Example: 2026-01-05 11:00 Israel ~= 09:00 UTC.
        out_closed_before = self._compute(datetime(2026, 1, 5, 8, 59, tzinfo=timezone.utc))
        self.assertEqual(out_closed_before["customer_service"], "currently_closed")

        out_open_at = self._compute(datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(out_open_at["customer_service"], "open")

    def test_sunday_closed_in_israel(self):
        # Pick a Sunday in Israel (2026-06-07 is a Sunday). At 12:00 UTC it's 15:00 in Israel (Sunday).
        out = self._compute(datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(out["customer_service"], "currently_closed")
        self.assertIn("service will resume on", out["service_opens"])


if __name__ == "__main__":
    unittest.main()

