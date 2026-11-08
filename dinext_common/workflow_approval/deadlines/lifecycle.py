"""Freeze one deadline obligation per personal assignment."""

import json

import frappe
from frappe.utils import get_datetime, now_datetime
from dinext_common.workflow_approval.deadlines.extensions import get_extensions
from dinext_common.workflow_approval.deadlines.policy import choose_deadline
from dinext_common.workflow_approval.email_settings import checked

FIELDS = ("deadline_assignment_id","deadline_started_at","deadline_due_at","deadline_transition_uuid",
    "deadline_interval_type","deadline_interval_value","deadline_timezone","deadline_error","deadline_candidates")


def snapshot(task):
    return {**{field:task.get(field) for field in FIELDS},
        "deadline_origin_task":task.get("deadline_origin_task") or task.name}


def candidates(task, workflow):
    available={row.transition_uuid for row in task.available_workflow_transitions}
    required={row.state for row in workflow.states if not checked(row.is_optional_state)}
    return [dict(uuid=row.custom_transition_uuid,idx=row.idx,
        amount=row.custom_deadline_value,unit=row.custom_deadline_unit)
        for row in workflow.transitions if row.custom_transition_uuid in available
        and row.next_state in required and checked(row.get("custom_deadline_enabled"))]


def prepare_task(task, workflow, *, inherited=None, started_at=None):
    if inherited and inherited.get("deadline_assignment_id"):
        task.update(inherited)
        return
    policies=candidates(task,workflow)
    if not policies:
        return
    from dinext_common.workflow_approval.notifications import _recipient_timezone
    task.deadline_assignment_id=task.name
    task.deadline_started_at=started_at or now_datetime()
    task.deadline_timezone=_recipient_timezone(task.approver)
    task.deadline_candidates=json.dumps(policies,ensure_ascii=False)
    calculate_task(task)


def calculate_task(task):
    """Retry only the frozen policy when missing calendar data is repaired."""
    from dinext_common.workflow_approval.notifications import _database_datetime, _aware_utc
    try:
        if not task.deadline_started_at:
            raise ValueError("Original assignment time is unknown")
        chosen=choose_deadline(json.loads(task.deadline_candidates or "[]"),
            start=_aware_utc(get_datetime(task.deadline_started_at)), timezone_name=task.deadline_timezone,
            approver=task.approver,doctype=task.reference_doctype,
            extensions=get_extensions(task.reference_doctype))
        if not chosen:
            raise ValueError("Deadline policy snapshot is missing")
        task.update(dict(deadline_due_at=_database_datetime(chosen["due"]),
            deadline_transition_uuid=chosen["uuid"],deadline_interval_type=chosen["unit"],
            deadline_interval_value=chosen["amount"],deadline_error=None))
    except Exception as exc:
        task.deadline_due_at=None
        task.deadline_error=str(exc)[:4000]


def retry_task(task):
    if task.status!="Working" or not task.deadline_assignment_id or not task.deadline_error:
        return
    calculate_task(task)
    frappe.db.set_value("Workflow Task",task.name,{key:task.get(key) for key in FIELDS},update_modified=False)
