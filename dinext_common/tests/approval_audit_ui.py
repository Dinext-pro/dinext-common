"""Synthetic audit acceptance fixtures; never callable against the served localhost."""
import json

import frappe
from frappe.utils import add_days, now_datetime

from dinext_common.tests.ui_test_helpers import PASSWORD, _ensure_role, _ensure_user, _ensure_master
from dinext_common.workflow_approval import engine

PREFIX = "DINEXT-APPROVAL-AUDIT-QA-"
ALICE = "approval-audit.alice@example.invalid"
BOB = "approval-audit.bob@example.invalid"
MONITOR = "approval-audit.monitor@example.invalid"
ROLE = PREFIX + "Approver"
REJECT_ROLE = PREFIX + "Rejector"
MONITOR_ROLE = PREFIX + "Monitor"
READER_ROLE = PREFIX + "Reader"
REPORTS = ("My Approvals", "My Approval History", "Approval Monitoring", "Approval Load", "Approval Duration")
WORKFLOW = PREFIX + "Note"
PREVIOUS = PREFIX + "previous-workflows"


def _guard():
	if frappe.local.site not in {"approvals-fixes-test", "test_site"} or frappe.session.user != "Administrator":
		raise frappe.PermissionError("Audit fixtures require the isolated test administrator")


def cleanup():
	_guard()
	previous = frappe.cache.get_value(PREVIOUS) or []
	tasks = frappe.get_all("Workflow Task", filters={"workflow": WORKFLOW}, pluck="name")
	frappe.db.delete("Available Workflow Transitions", {"parent": ["in", tasks]}) if tasks else None
	frappe.db.delete("Workflow Task", {"workflow": WORKFLOW})
	for doctype, filters in [
		("ToDo", {"reference_type": "Workflow Task", "reference_name": ["in", tasks]}),
		("Workflow Action", {"reference_doctype": "Note", "reference_name": ["like", PREFIX + "%"]}),
		("Comment", {"reference_doctype": "Note", "reference_name": ["like", PREFIX + "%"]}),
		("DocShare", {"share_doctype": "Note", "share_name": ["like", PREFIX + "%"]}),
		("Note", {"name": ["like", PREFIX + "%"]}),
		("Has Role", {"parent": WORKFLOW, "parenttype": "Workflow"}),
		("Workflow Transition", {"parent": WORKFLOW}),
		("Workflow Document State", {"parent": WORKFLOW}),
		("Workflow", {"name": WORKFLOW}),
	]:
		frappe.db.delete(doctype, filters)
	for user in (ALICE, BOB, MONITOR):
		if frappe.db.exists("User", user):
			frappe.delete_doc("User", user, force=True, ignore_permissions=True)
	for permission in ("DocPerm", "Custom DocPerm", "DocType Permission Condition"):
		frappe.db.delete(permission, {"role": READER_ROLE})
	frappe.cache.delete_value("doctype_permission_map")
	for role in (ROLE, REJECT_ROLE, MONITOR_ROLE, READER_ROLE):
		frappe.db.delete("Role", {"name": role})
	for name in previous:
		if frappe.db.exists("Workflow", name):
			frappe.db.set_value("Workflow", name, "is_active", 1)
	frappe.cache.delete_value(PREVIOUS)
	frappe.cache.hdel("workflow", "Note")
	frappe.clear_cache()
	frappe.db.commit()
	return {"cleaned": True}


def _grant_report_read():
	# Extend the existing layer: the first Custom DocPerm would replace all
	# standard Report permissions rather than adding this fixture role.
	permission_type = "Custom DocPerm" if frappe.db.exists("Custom DocPerm", {"parent": "Report"}) else "DocPerm"
	frappe.get_doc({"doctype": permission_type, "parent": "Report", "parenttype": "DocType",
		"parentfield": "permissions", "role": READER_ROLE, "permlevel": 0, "read": 1}).db_insert()
	report = frappe.qb.DocType("Report")
	condition = report.name.isin(REPORTS).get_sql()
	for rule in frappe.get_all("DocType Permission", filters={"ref_doctype": "Report"}, pluck="name"):
		frappe.get_doc({"doctype": "DocType Permission Condition", "parent": rule,
			"parenttype": "DocType Permission", "parentfield": "conditions", "role": READER_ROLE,
			"perm_level": "Full Access", "script": f"conditions = {condition!r}"}).db_insert()
	frappe.clear_cache(doctype="Report")
	frappe.cache.delete_value("doctype_permission_map")


def seed():
	_guard()
	cleanup()
	previous = frappe.get_all("Workflow", filters={"document_type": "Note", "is_active": 1}, pluck="name")
	frappe.cache.set_value(PREVIOUS, previous)
	for name in previous:
		frappe.db.set_value("Workflow", name, "is_active", 0)
	for role in (ROLE, REJECT_ROLE, MONITOR_ROLE, READER_ROLE):
		_ensure_role(role)
	_grant_report_read()
	for user, roles, language in [(ALICE, [ROLE], "en"), (BOB, [ROLE, REJECT_ROLE, MONITOR_ROLE], "ru"), (MONITOR, [MONITOR_ROLE], "ru")]:
		_ensure_user(user, user.split("@")[0], ["Desk User", READER_ROLE, *roles])
		frappe.db.set_value("User", user, "language", language)
		frappe.clear_cache(user=user)
	for state in ("Draft", "Approved", "Rejected"):
		_ensure_master("Workflow State", state, {"workflow_state_name": state})
	for action in ("Approve", "Reject"):
		_ensure_master("Workflow Action Master", action, {"workflow_action_name": action})
	workflow = frappe.get_doc({"doctype": "Workflow", "name": WORKFLOW,
		"workflow_name": WORKFLOW, "document_type": "Note", "workflow_state_field": "title", "is_active": 1})
	workflow.db_insert()
	for index, state in enumerate(("Draft", "Approved", "Rejected"), 1):
		frappe.get_doc({"doctype": "Workflow Document State", "parent": WORKFLOW, "parenttype": "Workflow",
			"parentfield": "states", "idx": index, "state": state, "doc_status": 0, "allow_edit": ROLE}).db_insert()
	for index, (action, state, role, policy) in enumerate([
		("Approve", "Approved", ROLE, "All"), ("Reject", "Rejected", REJECT_ROLE, "Any")], 1):
		frappe.get_doc({"doctype": "Workflow Transition", "parent": WORKFLOW, "parenttype": "Workflow",
			"parentfield": "transitions", "idx": index, "state": "Draft", "action": action,
			"next_state": state, "allowed": role, "allow_self_approval": 1,
			"custom_parallel_approval_policy": policy, "custom_transition_uuid": PREFIX + action,
			"custom_comment_is_required": 1}).db_insert()
	frappe.get_doc({"doctype": "Has Role", "parent": WORKFLOW, "parenttype": "Workflow",
		"parentfield": "custom_approval_monitor_roles", "role": MONITOR_ROLE}).db_insert()
	frappe.cache.hdel("workflow", "Note")
	frappe.clear_cache(doctype="Workflow")
	task_names = {}
	for suffix in ("Main", "Denied"):
		source = frappe.get_doc({"doctype": "Note", "name": PREFIX + suffix, "title": "Draft", "owner": "Administrator", "public": 0, "content": "Synthetic audit fixture"})
		source.db_insert()
		for user in (ALICE, BOB, MONITOR):
			frappe.share.add("Note", source.name, user, read=1)
		engine.reconcile_source(source)
		task_names[suffix] = frappe.db.get_value("Workflow Task", {"reference_doctype": "Note", "reference_name": source.name, "approver": ALICE}, "name")
		if suffix == "Main":
			bob_task = frappe.db.get_value("Workflow Task", {"reference_name": source.name, "approver": BOB}, "name")
			frappe.set_user(BOB)
			engine.cast_vote(bob_task, transition_uuid=PREFIX + "Approve", comment="Synthetic first vote", request_id=PREFIX + "first-vote")
			frappe.set_user("Administrator")
		else:
			frappe.share.remove("Note", source.name, ALICE)
	# A timestamp-boundary population independently exercises the control route.
	now = now_datetime()
	cutoff = add_days(now, -30)
	for suffix, stamp in [("Before", add_days(cutoff, -1)), ("After", now)]:
		frappe.get_doc({"doctype": "Workflow Task", "name": PREFIX + suffix,
			"doc": "Note", "wt_docname": PREFIX + "Main", "reference_doctype": "Note", "reference_name": PREFIX + "Main",
			"approver": ALICE, "user": ALICE, "workflow": WORKFLOW, "status": "Completed",
			"round_status": "Transitioned", "approval_round_id": PREFIX + suffix, "creation": stamp,
			"completed_at": stamp, "completion_source": "Manual", "action": "Approve", "round_manifest": "{}"}).db_insert()
	try:
		for user in (ALICE, BOB, MONITOR):
			frappe.set_user(user)
			for name in REPORTS:
				frappe.get_doc("Report", name).check_permission("read")
			if frappe.has_permission("Workflow Action Master", ptype="read"):
				raise AssertionError("The fixture must exercise action filters without workflow setup read")
	finally:
		frappe.set_user("Administrator")
	frappe.db.commit()
	return {"alice": ALICE, "bob": BOB, "monitor": MONITOR, "password": PASSWORD,
		"prefix": PREFIX, "tasks": task_names, "transition_uuid": PREFIX + "Approve", "workflow": WORKFLOW}
