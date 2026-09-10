import unittest
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo


class TestWorkflowApprovalNotifications(unittest.TestCase):
	def notifications(self):
		try:
			from dinext_common.workflow_approval import notifications
		except (ImportError, ModuleNotFoundError) as exc:
			self.fail(f"workflow approval notifications module is missing: {exc}")
		return notifications

	def test_daily_slot_uses_recipient_timezone(self):
		notifications = self.notifications()
		created = datetime(2026, 1, 1, 22, 0, tzinfo=timezone.utc)
		now = datetime(2026, 1, 2, 5, 30, tzinfo=timezone.utc)

		slot = notifications.latest_due_digest_slot(
			created_at=created,
			now=now,
			timezone_name="Europe/Moscow",
			unit="Days",
			interval=1,
			send_time=time(8, 0),
			anchor=created,
		)

		self.assertEqual(slot, datetime(2026, 1, 2, 5, 0, tzinfo=timezone.utc))

	def test_daily_first_slot_is_next_scheduled_time_not_immediate(self):
		notifications = self.notifications()
		created = datetime(2026, 1, 2, 6, 0, tzinfo=timezone.utc)
		now = datetime(2026, 1, 2, 6, 1, tzinfo=timezone.utc)

		self.assertIsNone(
			notifications.latest_due_digest_slot(
				created_at=created,
				now=now,
				timezone_name="Europe/Moscow",
				unit="Days",
				interval=1,
				send_time=time(8, 0),
				anchor=created,
			)
		)

	def test_hourly_slot_returns_one_latest_catchup_slot(self):
		notifications = self.notifications()
		created = datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc)
		anchor = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
		now = datetime(2026, 1, 1, 16, 45, tzinfo=timezone.utc)

		slot = notifications.latest_due_digest_slot(
			created_at=created,
			now=now,
			timezone_name="UTC",
			unit="Hours",
			interval=2,
			send_time=None,
			anchor=anchor,
		)

		self.assertEqual(slot, datetime(2026, 1, 1, 16, 0, tzinfo=timezone.utc))

	def test_invalid_timezone_falls_back_to_utc(self):
		notifications = self.notifications()
		self.assertEqual(notifications.get_timezone("Missing/Zone"), ZoneInfo("UTC"))

	def test_delivery_key_is_stable_for_same_logical_delivery(self):
		notifications = self.notifications()
		first = notifications.make_delivery_key(
			"Digest",
			"WF",
			"alice@example.com",
			"2026-01-01T08:00:00Z",
		)
		second = notifications.make_delivery_key(
			"Digest",
			"WF",
			"alice@example.com",
			"2026-01-01T08:00:00Z",
		)
		self.assertEqual(first, second)

	def test_daily_slot_moves_through_dst_gap(self):
		notifications = self.notifications()
		slot = notifications.latest_due_digest_slot(
			created_at=datetime(2026, 3, 28, 0, 0, tzinfo=timezone.utc),
			now=datetime(2026, 3, 29, 2, 0, tzinfo=timezone.utc),
			timezone_name="Europe/Berlin",
			unit="Days",
			interval=1,
			send_time=time(2, 30),
			anchor=datetime(2026, 3, 28, 0, 0, tzinfo=timezone.utc),
		)
		self.assertEqual(slot, datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc))

	def test_daily_slot_uses_first_dst_duplicate(self):
		notifications = self.notifications()
		slot = notifications.latest_due_digest_slot(
			created_at=datetime(2026, 10, 24, 0, 0, tzinfo=timezone.utc),
			now=datetime(2026, 10, 25, 2, 0, tzinfo=timezone.utc),
			timezone_name="Europe/Berlin",
			unit="Days",
			interval=1,
			send_time=time(2, 30),
			anchor=datetime(2026, 10, 24, 0, 0, tzinfo=timezone.utc),
		)
		self.assertEqual(slot, datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc))
