"""Recipient-localized, email-safe presentation shared by workflow templates."""

import re
from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import frappe
from babel.dates import format_date, format_datetime
from babel.numbers import format_decimal
from frappe import _
from frappe.translate import print_language

COLORS = {
	"primary": "#1769aa",
	"info": "#1769aa",
	"success": "#18794e",
	"warning": "#855900",
	"danger": "#b42318",
	"inverse": "#344054",
}


def inline_assets(message):
	root = Path(frappe.get_app_path("dinext_common", "public", "images")).resolve()
	prefix = "assets/dinext_common/images/"
	images = []
	for name in sorted(
		set(
			re.findall(
				r"""\bembed\s*=\s*["'](assets/dinext_common/images/[A-Za-z0-9_./-]+)["']""", message or ""
			)
		)
	):
		path = (root / name.removeprefix(prefix)).resolve()
		if path.is_relative_to(root) and path.is_file():
			images.append(dict(filename=name, filecontent=path.read_bytes()))
	return images


def recipient_language(user):
	return (
		(frappe.db.get_value("User", user, "language") if user else None)
		or frappe.db.get_single_value("System Settings", "language")
		or frappe.db.get_default("lang")
		or "en"
	)


@contextmanager
def language_context(user):
	with print_language(recipient_language(user)):
		yield


def full_name(user):
	return (frappe.get_cached_value("User", user, "full_name") if user else None) or _("Former user")


def date_label(value, user, *, date_only=False):
	if not value:
		return ""
	from frappe.utils import getdate

	from dinext_common.workflow_approval.notifications import _aware_utc, _recipient_timezone, get_timezone

	locale = recipient_language(user).replace("-", "_")
	if date_only:
		return format_date(getdate(value), format="medium", locale=locale)
	local = _aware_utc(value).astimezone(get_timezone(_recipient_timezone(user)))
	return format_datetime(local, format="medium", locale=locale)


def number_label(value, user):
	return format_decimal(value or 0, format="#,##0.##", locale=recipient_language(user).replace("-", "_"))


def action_details(action):
	result = dict(action)
	name = result.get("action_name") or result.get("action") or ""
	style = result.get("style")
	if not style and result.get("next_state"):
		style = frappe.get_cached_value("Workflow State", result["next_state"], "style")
	icon = result.get("icon") or frappe.get_cached_value("Workflow Action Master", name, "custom_icon") or ""
	if icon == "close":
		icon = "close-alt"
	result["action_label"] = _(name)
	result["color"] = COLORS.get(str(style or "primary").lower(), COLORS["primary"])
	result["icon_image"] = (
		"assets/dinext_common/images/workflow-icons/" + icon + ".png"
		if re.fullmatch(r"[a-z0-9-]+", icon)
		and Path(
			frappe.get_app_path("dinext_common", "public", "images", "workflow-icons", icon + ".png")
		).is_file()
		else ""
	)
	return result


def document_title(doc):
	if not doc:
		return ""
	doctype = doc.get("doctype")
	title_field = frappe.get_meta(doctype).title_field if doctype else None
	return doc.get(title_field) if title_field and doc.get(title_field) else doc.get("name") or ""


def _row(row, user):
	result = dict(row)
	result["actions"] = [action_details(action) for action in row.get("actions") or []]
	result["doctype_label"] = _(row.get("doctype") or "")
	result["due_label"] = date_label(row.get("due"), user)
	result["overdue_label"] = number_label(row.get("overdue_hours"), user)
	result["hours_label"] = number_label(row.get("hours"), user)
	if row.get("approver"):
		result["approver_name"] = full_name(row["approver"])
	return result


def timesheet_groups(rows, user):
	authors = {}
	for row in rows:
		if not row.get("timesheet_name"):
			continue
		author = row.get("author") or ""
		group = authors.setdefault(author, dict(author_name=full_name(author), sheets={}))
		sheet = group["sheets"].setdefault(
			row["timesheet_name"],
			dict(
				name=row["timesheet_name"],
				title=_("Timesheet")
				+ " · "
				+ date_label(row.get("period_from"), user, date_only=True)
				+ " — "
				+ date_label(row.get("period_to"), user, date_only=True),
				link=row["link"],
				positions={},
			),
		)
		position = sheet["positions"].setdefault(
			row.get("position_name") or row["name"], dict(row, overdues=[])
		)
		if row.get("due"):
			position["overdues"].append(
				dict(
					approver_name=row.get("approver_name"),
					due_label=row["due_label"],
					overdue_label=row["overdue_label"],
				)
			)
	result = []
	for author in sorted(authors.values(), key=lambda item: item["author_name"].casefold()):
		sheets = []
		for sheet in author["sheets"].values():
			positions = sorted(
				sheet["positions"].values(),
				key=lambda item: (int(item.get("ordinal") or 0), item.get("position_name") or ""),
			)
			sheet.update(
				positions=positions,
				count=len(positions),
				hours=sum(float(item.get("hours") or 0) for item in positions),
			)
			sheet["hours_label"] = number_label(sheet["hours"], user)
			sheets.append(sheet)
		author["sheets"] = sorted(sheets, key=lambda item: item["name"])
		result.append(author)
	return result


def prepare_context(template_name, context, user):
	result = deepcopy(context)
	state = result.get("workflow_state") or (result.get("workflow_task") or {}).get("workflow_state")
	kind = (
		"deadline"
		if result.get("deadline_notice") or "Deadline" in template_name
		else "correction"
		if "Correction" in template_name or state in ("Rejected", "Отклонено")
		else "digest"
		if "Digest" in template_name or (result.get("rows") is not None and not result.get("doc"))
		else "action"
	)
	result.update(
		email_kind=kind,
		is_timesheet="Timesheet" in template_name
		or bool(result.get("timesheet_link"))
		or any(row.get("timesheet_name") for row in result.get("rows") or []),
	)
	doc = result.get("doc") or {}
	result["document_title"] = result.get("document_title") or document_title(doc)
	result["document_type_label"] = _(doc.get("doctype") or "")
	result["author_name"] = full_name(
		doc.get("owner") or (result.get("workflow_task") or {}).get("source_owner")
	)
	result["actions"] = [action_details(action) for action in result.get("actions") or []]
	result["rows"] = [_row(row, user) for row in result.get("rows") or []]
	result["author_groups"] = timesheet_groups(result["rows"], user)
	result["comments"] = [
		dict(
			comment, author_name=full_name(comment.get("actor")), at_label=date_label(comment.get("at"), user)
		)
		for comment in (result.get("entry_context") or {}).get("comments", [])
	]
	if kind in ("correction", "deadline"):
		result["actions"] = []
		for row in result["rows"]:
			row["actions"] = []
		for author in result["author_groups"]:
			for sheet in author["sheets"]:
				for position in sheet["positions"]:
					position["actions"] = []
	headers = {
		"action": _("Approval required"),
		"digest": _("Pending workflow approvals"),
		"correction": _("Correction required"),
		"deadline": _("Approval deadline exceeded"),
	}
	result["header_title"] = headers[kind]
	result["count"] = len({(row.get("doctype"), row.get("name")) for row in result["rows"]})
	if result["author_groups"]:
		sheets = [sheet for author in result["author_groups"] for sheet in author["sheets"]]
		result["summary"] = " · ".join(
			(
				_("Timesheets") + ": " + str(len(sheets)),
				_("Positions") + ": " + str(sum(sheet["count"] for sheet in sheets)),
				_("Hours") + ": " + number_label(sum(sheet["hours"] for sheet in sheets), user),
			)
		)
	elif kind in ("digest", "deadline"):
		result["summary"] = (
			_("Documents") + ": " + str(result["count"]) + " · " + _(result.get("workflow_state") or "")
		)
	else:
		result["summary"] = result["document_type_label"]
	if result.get("timesheet_period_from"):
		result["timesheet_title"] = (
			_("Timesheet")
			+ " · "
			+ date_label(result["timesheet_period_from"], user, date_only=True)
			+ " — "
			+ date_label(result["timesheet_period_to"], user, date_only=True)
		)
	return result


def render_standard(name, context, user):
	from dinext_common.workflow_approval.email_templates import default_email_templates

	with language_context(user):
		context = prepare_context(name, context, user)
		template = default_email_templates()[name]
		return (
			frappe.render_template(template["subject"], context),
			frappe.render_template(template["response_html"], context),
		)
