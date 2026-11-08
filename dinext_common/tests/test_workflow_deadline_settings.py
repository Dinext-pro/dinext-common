import unittest
from types import SimpleNamespace as Row
from datetime import datetime


def workflow(**overrides):
    transition=Row(custom_transition_uuid="uuid", next_state="Approved", custom_deadline_enabled=1,
        custom_deadline_unit="Hours", custom_deadline_value=24, custom_deadline_recipient_type="User",
        custom_deadline_recipient_user="manager@example.test",custom_deadline_email_mode="Digest",
        custom_deadline_interval_unit="Days",custom_deadline_interval_value=1,
        custom_deadline_send_times="17:00, 08:00, 08:00")
    for key,value in overrides.items():setattr(transition,key,value)
    return Row(transitions=[transition],states=[Row(state="Approved",is_optional_state=0)],document_type="Issue")


class TestDeadlineSettings(unittest.TestCase):
    def test_optional_destination_cannot_have_deadline(self):
        from dinext_common.workflow_approval.deadlines.metadata import prepare_settings
        w=workflow();w.states[0].is_optional_state=1
        with self.assertRaises(ValueError):prepare_settings(w,extensions={})

    def test_schedule_normalizes_and_changes_reset_anchor_only_when_needed(self):
        from dinext_common.workflow_approval.deadlines.metadata import prepare_settings
        import copy
        w=workflow();now=datetime(2026,11,9,7)
        prepare_settings(w,extensions={},now=lambda:now)
        self.assertEqual(w.transitions[0].custom_deadline_send_times,"08:00, 17:00")
        old=copy.deepcopy(w)
        prepare_settings(w,previous=old,extensions={},now=lambda:datetime(2026,11,10))
        self.assertEqual(w.transitions[0].custom_deadline_schedule_anchor,now)
        w.transitions[0].custom_deadline_send_times="09:00"
        prepare_settings(w,previous=old,extensions={},now=lambda:datetime(2026,11,10))
        self.assertEqual(w.transitions[0].custom_deadline_schedule_anchor,datetime(2026,11,10))

    def test_invalid_or_unregistered_types_rejected(self):
        from dinext_common.workflow_approval.deadlines.metadata import prepare_settings
        for values in [dict(custom_deadline_value=0),dict(custom_deadline_unit="Working Hours"),
            dict(custom_deadline_recipient_type="arbitrary.callable"),dict(custom_deadline_send_times="tomorrow")]:
            with self.subTest(values=values),self.assertRaises(ValueError):
                prepare_settings(workflow(**values),extensions={})
