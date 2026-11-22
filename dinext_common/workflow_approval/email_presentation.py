"""Recipient-localized, email-safe presentation shared by workflow templates."""

import re
from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from urllib.parse import urljoin, urlsplit

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


def plain_text(message):
	from bs4 import BeautifulSoup
	from frappe.core.utils import html_to_plain_text
	from frappe.utils import get_url

	soup = BeautifulSoup(message, "html.parser")
	base_url = get_url()
	for link in soup.select("a[href]"):
		href = link["href"].strip()
		if not href or href.startswith("#"):
			continue
		try:
			url = urljoin(base_url, href)
			parsed = urlsplit(url)
		except ValueError:
			continue
		if parsed.scheme in ("http", "https") and parsed.netloc and link.get_text(strip=True) != url:
			link.append(f" ({url})")
	return html_to_plain_text(str(soup))


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


def document_title(doc, user=None):
	if not doc:
		return ""
	doctype = doc.get("doctype")
	title_field = frappe.get_meta(doctype).title_field if doctype else None
	return (
		(doc.get(title_field) if title_field and title_field != "name" else None)
		or doc.get("subject")
		or doc.get("title")
		or _(doctype or "Document")
	)


def _row(row, user):
	result = dict(row)
	result["actions"] = [action_details(action) for action in row.get("actions") or []]
	result["doctype_label"] = _(row.get("doctype") or "")
	if not result.get("title") or result.get("title") == result.get("name"):
		result["title"] = result["doctype_label"]
	result["due_label"] = date_label(row.get("due"), user)
	result["overdue_label"] = number_label(row.get("overdue_hours"), user)
	if row.get("approver"):
		result["approver_name"] = full_name(row["approver"])
	return result


def document_summary(rows, doc=None, workflow=None):
	by_type = defaultdict(set)
	doc = doc or {}
	for row in rows:
		by_type[row.get("doctype") or doc.get("doctype") or "Document"].add(row.get("name"))
	if not by_type:
		by_type[doc.get("doctype") or (workflow or {}).get("document_type") or "Document"].add(doc.get("name"))
	return " · ".join(_(doctype) + ": " + str(len(names)) for doctype, names in by_type.items())


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
	result.update(email_kind=kind, workflow_state=state)
	doc = result.get("doc") or {}
	result["document_title"] = result.get("document_title") or document_title(doc, user)
	result["document_type_label"] = _(doc.get("doctype") or "")
	result["author_name"] = full_name(
		doc.get("owner") or (result.get("workflow_task") or {}).get("source_owner")
	)
	result["actions"] = [action_details(action) for action in result.get("actions") or []]
	result["rows"] = [_row(row, user) for row in result.get("rows") or []]
	result["comments"] = [
		dict(
			comment,
			author_name=full_name(comment.get("actor")),
			at_label=date_label(comment.get("at"), user),
			lines=(comment.get("text") or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"),
		)
		for comment in (result.get("entry_context") or {}).get("comments", [])
	]
	if kind in ("correction", "deadline"):
		result["actions"] = []
		for row in result["rows"]:
			row["actions"] = []
	headers = {
		"action": _("Approval required"),
		"digest": _("Pending workflow approvals"),
		"correction": _("Correction required"),
		"deadline": _("Approval deadline exceeded"),
	}
	result["header_title"] = headers[kind]
	result["count"] = len({(row.get("doctype"), row.get("name")) for row in result["rows"]})
	result["summary"] = document_summary(result["rows"], doc, result.get("workflow"))
	if state:
		result["summary"] += " — " + _(state)

	# These layout controls may only be set by installed applications.
	result.update(
		subject_document_title=None,
		document_caption=None,
		document_details=[],
		primary_document_link=result.get("document_link"),
		primary_document_title=result["document_title"],
		grouped_rows_template=None,
		ungrouped_rows=result["rows"],
	)
	if getattr(frappe.local, "site", None):
		for provider in frappe.get_hooks("workflow_approval_email_presentation_providers") or ():
			result.update(frappe.get_attr(provider)(template_name, result, user) or {})
	return result


def render_standard(name, context, user):
	from dinext_common.workflow_approval.email_templates import renderable_email_templates

	with language_context(user):
		context = prepare_context(name, context, user)
		template = renderable_email_templates()[name]
		return (
			frappe.render_template(template["subject"], context),
			frappe.render_template(template["response_html"], context),
		)
