"""Read recorded mandatory comments without changing approval state."""

from __future__ import annotations

import json
from typing import TypedDict

import frappe
from frappe.query_builder import DocType
from frappe.utils import cint
from pypika import Order
from pypika.analytics import RowNumber


class WorkflowCommentResponse(TypedDict):
	task_name: str
	reference_name: str
	author: str
	author_name: str
	comment: str


def get_latest_round_comments(doctype: str, names: list[str]) -> list[WorkflowCommentResponse]:
	"""Collect every required comment in each source's latest decision round."""
	if not names:
		return []
	task = DocType("Workflow Task")
	source = DocType(doctype)
	latest = (
		frappe.qb.from_(task)
		.inner_join(source).on((task.reference_name == source.name) & (task.source_created_at == source.creation))
		.select(
			task.reference_name,
			task.approval_round_id,
			RowNumber().over(task.reference_name)
			.orderby(task.completed_at, order=Order.desc)
			.orderby(task.creation, order=Order.desc)
			.orderby(task.name, order=Order.desc).as_("sequence"),
		)
		.where(
			(task.reference_doctype == doctype)
			& task.reference_name.isin(names)
			& (task.status == "Completed")
			& task.completed_at.notnull()
			& task.source_deleted_at.isnull()
			& task.approval_round_id.notnull()
			& (task.approval_round_id != "")
			& (task.completion_source.isnull() | (task.completion_source != "Carried"))
		).as_("latest")
	)
	rounds = dict(
		frappe.qb.from_(latest)
		.select(latest.reference_name, latest.approval_round_id)
		.where(latest.sequence == 1)
		.run()
	)
	if not rounds:
		return []
	rows = frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": doctype,
			"reference_name": ("in", list(rounds)),
			"approval_round_id": ("in", list(set(rounds.values()))),
			"status": "Completed",
		},
		fields=[
			"name", "reference_name", "approval_round_id", "approver", "user",
			"vote_comment", "transition_uuid", "round_manifest",
		],
		order_by="completed_at asc, name asc",
		limit_page_length=0,
	)
	comments: list[WorkflowCommentResponse] = []
	for row in rows:
		if rounds.get(row.reference_name) != row.approval_round_id:
			continue
		text = str(row.vote_comment or "").strip()
		author = row.approver or row.user
		if not text or not author or not _required_comment(row):
			continue
		comments.append({
			"task_name": row.name,
			"reference_name": row.reference_name,
			"author": author,
			"author_name": author,
			"comment": text,
		})
	if comments:
		names_by_user = dict(frappe.get_all(
			"User",
			filters={"name": ("in", sorted({row["author"] for row in comments}))},
			fields=["name", "full_name"],
			as_list=True,
		))
		for row in comments:
			row["author_name"] = names_by_user.get(row["author"]) or row["author"]
	return comments


def _required_comment(row: frappe._dict) -> bool:
	if not row.transition_uuid:
		return False
	try:
		manifest = json.loads(row.round_manifest or "{}")
	except (TypeError, ValueError):
		return False
	if not isinstance(manifest, dict):
		return False
	transitions = manifest.get("transitions")
	if not isinstance(transitions, list):
		return False
	return any(
		isinstance(transition, dict)
		and transition.get("transition_uuid") == row.transition_uuid
		and bool(cint(transition.get("comment_is_required")))
		for transition in transitions
	)
