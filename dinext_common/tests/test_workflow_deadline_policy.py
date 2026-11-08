import unittest
from datetime import datetime, timezone


class TestDeadlinePolicy(unittest.TestCase):

    def calculate(self, **kwargs):
        from dinext_common.workflow_approval.deadlines.policy import calculate_due
        return calculate_due(**kwargs)

    def test_elapsed_hours_across_dst(self):
        self.assertEqual(self.calculate(start=datetime(2026, 3, 28, 12, tzinfo=timezone.utc),
            amount=24, unit="Hours", timezone_name="Europe/Berlin"),
            datetime(2026, 3, 29, 12, tzinfo=timezone.utc))

    def test_calendar_day_preserves_local_clock_across_dst(self):
        self.assertEqual(self.calculate(start=datetime(2026, 3, 28, 12, tzinfo=timezone.utc),
            amount=1, unit="Days", timezone_name="Europe/Berlin"),
            datetime(2026, 3, 29, 11, tzinfo=timezone.utc))

    def test_invalid_duration_and_unknown_type_fail_closed(self):
        for amount, unit in [(0, "Hours"), (-1, "Days"), (1.5, "Days"), (1, "Unknown")]:
            with self.subTest(amount=amount, unit=unit), self.assertRaises(ValueError):
                self.calculate(start=datetime(2026, 1, 1, tzinfo=timezone.utc), amount=amount,
                    unit=unit, timezone_name="UTC")

    def test_earliest_transition_and_stable_tie(self):
        from dinext_common.workflow_approval.deadlines.policy import choose_deadline
        start=datetime(2026, 1, 1, tzinfo=timezone.utc)
        transitions=[dict(uuid="z", idx=3, amount=1, unit="Days"),
            dict(uuid="b", idx=2, amount=8, unit="Hours"),
            dict(uuid="a", idx=2, amount=8, unit="Hours")]
        chosen=choose_deadline(transitions, start=start, timezone_name="UTC")
        self.assertEqual(chosen["uuid"], "a")
        self.assertEqual(chosen["due"],datetime(2026,1,1,8,tzinfo=timezone.utc))

    def test_extension_dispatches_installed_handler_with_context(self):
        def calculate(context):
            self.assertEqual(context["approver"], "approver@example.test")
            return datetime(2026,1,5,15,30,tzinfo=timezone.utc)
        result=self.calculate(start=datetime(2026,1,2,15,30,tzinfo=timezone.utc), amount=3,
            unit="Working Days", timezone_name="UTC", approver="approver@example.test",
            extensions={"deadline_intervals":{"Working Days":{"label":"Working Days",
                "calculate":calculate, "integer":True}}})
        self.assertEqual(result,datetime(2026,1,5,15,30,tzinfo=timezone.utc))

    def test_uncomputable_candidate_does_not_silently_choose_later_deadline(self):
        from dinext_common.workflow_approval.deadlines.policy import choose_deadline
        with self.assertRaises(ValueError):
            choose_deadline([dict(uuid="a",idx=1,amount=1,unit="Hours"),
                dict(uuid="b",idx=2,amount=1,unit="Missing")],
                start=datetime(2026,1,1,tzinfo=timezone.utc),timezone_name="UTC")
