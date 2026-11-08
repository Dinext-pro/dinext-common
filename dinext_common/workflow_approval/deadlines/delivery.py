"""Transactional deadline escalation using current policies and permissions."""

from collections import defaultdict
from datetime import datetime
import hashlib
import json

import frappe
from frappe.utils import get_datetime, get_url_to_form, now_datetime
from dinext_common.workflow_approval.deadlines.extensions import get_extensions
from dinext_common.workflow_approval.email_preferences import email_allowed
from dinext_common.workflow_approval.email_settings import checked, normalize_send_times
from dinext_common.workflow_approval import notifications as mail


def current_policy(task,workflow):
    return next((row for row in workflow.transitions if row.custom_transition_uuid==task.deadline_transition_uuid
        and checked(row.get("custom_deadline_enabled"))),None)


def recipients(task,policy,now):
    kind=policy.custom_deadline_recipient_type
    if kind=="User":
        return [policy.custom_deadline_recipient_user] if policy.custom_deadline_recipient_user else []
    if kind=="Role":
        from frappe.utils.user import get_users_with_role
        return get_users_with_role(policy.custom_deadline_recipient_role)
    handler=get_extensions(task.reference_doctype).get("recipients",{}).get(kind)
    if not handler:
        return []
    return handler["resolve"](dict(approver=task.approver,doctype=task.reference_doctype,
        reference_name=task.reference_name,on_date=mail._database_datetime(mail._aware_utc(now)))) or []


def profile_key(policy):
    fields=("custom_deadline_email_mode","custom_deadline_email_template","custom_deadline_interval_unit",
        "custom_deadline_interval_value","custom_deadline_send_times","custom_deadline_schedule_anchor")
    return hashlib.sha256(json.dumps([policy.get(key) for key in fields],default=str).encode()).hexdigest()


def delivery_slot(task,policy,recipient,now):
    if policy.custom_deadline_email_mode=="Immediate":
        return None
    unit=policy.custom_deadline_interval_unit
    context=dict(created_at=mail._aware_utc(task.deadline_due_at),now=mail._aware_utc(now),
        timezone_name=mail._recipient_timezone(recipient),interval=int(policy.custom_deadline_interval_value or 1),
        send_times=tuple(datetime.strptime(part.strip(),"%H:%M").time()
            for part in normalize_send_times(policy.custom_deadline_send_times).split(",") if part.strip()) if unit!="Hours" else (),
        anchor=mail._aware_utc(policy.custom_deadline_schedule_anchor or now))
    if unit in ("Hours","Days"):
        return mail.latest_due_digest_slot(unit=unit,**context)
    handler=get_extensions(task.reference_doctype).get("sending_intervals",{}).get(unit)
    if not handler:
        return None
    return handler["latest_slot"]({**context,"recipient":recipient})


def _eligible(task,workflow,recipient,now):
    if not checked(workflow.send_email_alert) or not workflow.is_active or not email_allowed(recipient):
        return False
    if task.status!="Working" or task.round_status not in ("Open","Stalled") or task.deadline_error or not task.deadline_due_at:
        return False
    if mail._aware_utc(task.deadline_due_at)>=mail._aware_utc(now):
        return False
    policy=current_policy(task,workflow)
    if not policy or recipient not in recipients(task,policy,now):
        return False
    if not frappe.db.get_value("User",recipient,"enabled"):
        return False
    from dinext_common.workflow_approval.engine import _has_source_read_permission
    try:
        source=frappe.get_doc(task.reference_doctype,task.reference_name)
    except frappe.DoesNotExistError:
        return False
    if task.source_created_at and get_datetime(source.creation)!=get_datetime(task.source_created_at):
        return False
    from frappe.model.workflow import get_workflow_name
    return (get_workflow_name(source.doctype)==workflow.name
        and source.get(workflow.workflow_state_field)==task.workflow_state
        and _has_source_read_permission(source,recipient))


def send_group(*,workflow,recipient,task_names,slot,profile_key,template,now=None):
    now=now or now_datetime()
    user=frappe.db.get_value("User",recipient,["email","enabled"],as_dict=True)
    if not user or not user.enabled or not user.email:
        return
    tasks=[]
    # Lock assignments deterministically. Queue insertion and delivery claim share the transaction.
    for name in sorted(set(task_names)):
        task=frappe.get_doc("Workflow Task",name,for_update=True)
        if _eligible(task,workflow,recipient,now):tasks.append(task)
    if not tasks:
        return
    state=tasks[0].workflow_state
    tasks=[task for task in tasks if task.workflow_state==state]
    identity=(slot.isoformat() if slot else tasks[0].deadline_assignment_id)+":"+profile_key
    key=mail.make_delivery_key("Deadline Digest" if slot else "Deadline Immediate",workflow.name,
        recipient,identity,state=state)
    if frappe.db.exists("Workflow Deadline Delivery",key):
        return
    savepoint="deadline_delivery_"+key[:12]
    frappe.db.savepoint(savepoint)
    try:
        frappe.get_doc(dict(doctype="Workflow Deadline Delivery",delivery_key=key,recipient=recipient,
            workflow=workflow.name,workflow_state=state,slot=mail._database_datetime(slot) if slot else None,
            task_names=json.dumps([task.name for task in tasks]),status="Enqueued")).insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        frappe.db.rollback(save_point=savepoint)
        return
    try:
        if mail._queued_delivery(key):
            return
        rows=[]
        for task in tasks:
            row=dict(doctype=task.reference_doctype,name=task.reference_name,title=task.source_title,
                link=get_url_to_form(task.reference_doctype,task.reference_name),due=task.deadline_due_at,
                overdue_hours=max(0,(mail._aware_utc(now)-mail._aware_utc(task.deadline_due_at)).total_seconds()/3600),
                approver=task.approver,approver_name=frappe.db.get_value("User",task.approver,"full_name") or task.approver,
                actions=[],count=1,tasks=[task.name])
            for adapter in frappe.get_hooks("workflow_approval_digest_item") or []:
                row.update(frappe.get_attr(adapter)(task) or {})
            row["actions"]=[]
            rows.append(row)
        context=dict(rows=rows,tasks=[task.as_dict() for task in tasks],workflow=workflow.as_dict(),
            workflow_state=state,recipient=recipient,slot=slot,deadline_notice=True,actions=[])
        if frappe.db.exists("Email Template",template):
            subject,message=mail._template_message(template,context,recipient)
        else:
            with mail._language_context(recipient):
                subject=frappe._("Approval deadline exceeded")
                message=frappe.render_template("templates/emails/dinext_workflow_deadline.html",context)
        mail._sendmail_for_user(recipient,recipients=[user.email],sender="Dinext <ikhmel@dinext.ru>",
            reply_to="ikhmel@dinext.ru",subject=subject,message=message,message_id=key,
            reference_doctype="Workflow",reference_name=workflow.name)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise


def dispatch_due_deadlines(now=None):
    now=now or now_datetime()
    groups=defaultdict(list);workflows={};templates={};slots={}
    # Scheduler is a trusted system reader; every recipient/document pair is checked again at send.
    names=frappe.get_all("Workflow Task",filters={"status":"Working","round_status":["in",["Open","Stalled"]],
        "deadline_assignment_id":["is","set"]},pluck="name",order_by="name")
    for name in names:
        try:
            task=frappe.get_doc("Workflow Task",name)
            if task.deadline_error:
                from dinext_common.workflow_approval.deadlines.lifecycle import retry_task
                retry_task(task)
            if task.deadline_error or not task.deadline_due_at or mail._aware_utc(task.deadline_due_at)>=mail._aware_utc(now):
                continue
            workflow=workflows.setdefault(task.workflow,frappe.get_doc("Workflow",task.workflow))
            policy=current_policy(task,workflow)
            if not policy or not checked(workflow.send_email_alert):continue
            for recipient in sorted(set(recipients(task,policy,now))):
                if not _eligible(task,workflow,recipient,now):continue
                slot=delivery_slot(task,policy,recipient,now)
                if policy.custom_deadline_email_mode=="Digest" and not slot:continue
                profile=profile_key(policy)
                key=(workflow.name,task.workflow_state,recipient,profile,slot,
                    task.deadline_assignment_id if slot is None else "")
                groups[key].append(task.name)
                templates[key]=policy.custom_deadline_email_template or ("Dinext Timesheet Workflow Deadline Digest"
                    if task.reference_doctype=="User Timesheet Position" else "Dinext Workflow Deadline Digest")
        except Exception:
            frappe.log_error(title="Workflow deadline dispatch failed",reference_doctype="Workflow Task",reference_name=name)
    for key,names in groups.items():
        workflow,state,recipient,profile,slot,_assignment=key
        try:
            send_group(workflow=workflows[workflow],recipient=recipient,task_names=names,slot=slot,
                profile_key=profile,template=templates[key],now=now)
        except Exception:
            frappe.log_error(title="Workflow deadline delivery failed",reference_doctype="Workflow",reference_name=workflow)
