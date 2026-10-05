"""Recipient-aware Follow digests for the standard Frappe scheduler."""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.core.utils import html2text
from frappe.desk.form import document_follow as core
from frappe.model import default_fields
from frappe.utils import get_url_to_form


@contextmanager
def _as_recipient(user):
	# Permission hooks may use session.user even when has_permission receives user=.
	# set_user would also reset the session; restore only the identity we change.
	original_user = frappe.session.user
	cache_names = ("cache", "role_permissions", "request_cache")
	original_caches = {name: getattr(frappe.local, name, None) for name in cache_names}
	for name in cache_names:
		setattr(frappe.local, name, {})
	frappe.session.user = user
	try:
		yield
	finally:
		frappe.session.user = original_user
		for name, original in original_caches.items():
			if original is None:
				delattr(frappe.local, name)
			else:
				setattr(frappe.local, name, original)


def _recipient_is_enabled(user, frequency):
	if not user or user == "Guest":
		return False
	settings = frappe.db.get_value(
		"User",
		user,
		["enabled", "document_follow_notify", "document_follow_frequency"],
		as_dict=True,
	)
	return bool(
		settings
		and settings.enabled
		and settings.document_follow_notify
		and settings.document_follow_frequency == frequency
	)


def _readable_document(doctype, name, user):
	try:
		doc = frappe.get_doc(doctype, name)
		if frappe.has_permission(doctype, "read", doc=doc, user=user):
			return doc
	except (frappe.DoesNotExistError, frappe.PermissionError):
		pass
	return None


class _CommentVisibility:
	"""Decisions are scoped to one document, recipient and collection pass."""

	def __init__(self, doctype, name, user, comments):
		self.doctype = doctype
		self.name = name
		self.user = user
		self.comments = {comment.name: comment for comment in comments}
		self.decisions = {}

	def _comment(self, name):
		if name not in self.comments:
			# Parents can be older than the digest's time window.
			rows = frappe.get_all("Comment", filters={"name": name}, fields="*", limit_page_length=1)
			self.comments[name] = rows[0] if rows else None
		return self.comments[name]

	def _allows_one(self, comment):
		if comment.reference_doctype != self.doctype or comment.reference_name != self.name:
			return False
		visibility = comment.get("custom_visibility")
		if visibility in (None, "", "Visible to everyone"):
			return True
		if visibility not in ("Visible to only you", "Visible to mentioned"):
			return False
		if self.user in ("Administrator", comment.owner):
			return True
		return bool(
			visibility == "Visible to mentioned"
			and frappe.db.exists(
				"User Group Member",
				{
					"user": self.user,
					"parent": comment.name,
					"parenttype": "Comment",
					"parentfield": "custom_mentions",
				},
			)
		)

	def allows(self, name):
		chain = set()
		current = name
		while current:
			if current in self.decisions:
				allowed = self.decisions[current]
				break
			if current in chain:
				allowed = False
				break
			chain.add(current)
			comment = self._comment(current)
			if not comment or not self._allows_one(comment):
				allowed = False
				break
			current = comment.get("custom_reply_to")
		else:
			allowed = True
		for ancestor in chain:
			self.decisions[ancestor] = allowed
		return allowed


def _get_comments(doctype, name, frequency, user):
	# This trusted service checks document access first and each row's visibility
	# before conversion or rendering; get_list alone does not enforce Comment Xt.
	comments = frappe.get_all(
		"Comment",
		filters=[
			["reference_doctype", "=", doctype],
			["reference_name", "=", name],
			*core._get_filters(frequency, user),
		],
		fields="*",
	)
	visibility = _CommentVisibility(doctype, name, user, comments)
	timeline = []
	for comment in comments:
		if not visibility.allows(comment.name):
			continue
		if comment.comment_type == "Like":
			by = f" By : <b>{comment.modified_by}<b>"
		elif comment.comment_type == "Comment":
			by = f"Commented by : <b>{comment.modified_by}<b>"
		else:
			by = ""
		timeline.append(
			{
				"time": comment.modified,
				"data": {
					"time": frappe.utils.format_datetime(comment.modified, "hh:mm a"),
					"comment": html2text(str(comment.content)),
					"by": by,
				},
				"doctype": doctype,
				"doc_name": name,
				"type": "comment",
			}
		)
	return timeline


def _readable_versions(doc, frequency, user):
	# Follow the Document read policy, including Table fields (which Meta's
	# get_permitted_fieldnames omits) and level-zero fields on shared documents.
	permlevels = set(doc.get_permlevel_access("read"))

	def readable_field(meta, name):
		field = meta.get_field(name)
		return bool(
			field and (not field.permlevel or user == "Administrator" or field.permlevel in permlevels)
		)

	child_meta = {}
	result = []
	for item in core.get_version(doc.doctype, doc.name, frequency, user):
		data = item["data"]
		if item["type"] == "field changed":
			allowed = data["field"] in default_fields or readable_field(doc.meta, data["field"])
		elif item["type"] in ("row changed", "row added"):
			table = data["table_field"] if item["type"] == "row changed" else data["to"]
			field = doc.meta.get_field(table)
			allowed = bool(
				field
				and field.fieldtype in ("Table", "Table MultiSelect")
				and readable_field(doc.meta, table)
			)
			if allowed and item["type"] == "row changed":
				if table not in child_meta:
					child_meta[table] = frappe.get_meta(field.options)
				allowed = readable_field(child_meta[table], data["field"])
		else:
			allowed = False
		if allowed:
			result.append(item)
	return result


def get_message_for_user(frequency, user):
	"""Collect only activity currently readable by this enabled follower."""
	if not _recipient_is_enabled(user, frequency):
		return [], []
	message, docinfo = [], []
	with _as_recipient(user):
		for follow in core.get_document_followed_by_user(user):
			doc = _readable_document(follow.ref_doctype, follow.ref_docname, user)
			if doc is None:
				continue
			content = _readable_versions(doc, frequency, user) + _get_comments(
				doc.doctype, doc.name, frequency, user
			)
			if not content:
				continue
			message.extend(sorted(content, key=lambda item: item["time"], reverse=True))
			docinfo.append(
				{
					"reference_docname": doc.name,
					"reference_doctype": doc.doctype,
					"reference_url": get_url_to_form(doc.doctype, doc.name),
				}
			)
	return message, docinfo


def send_email_alert(receiver, frequency):
	"""Rebuild at the mail boundary; never send stale, pre-rendered activity."""
	timeline, docinfo = get_message_for_user(frequency, receiver)
	if not timeline:
		return False
	frappe.sendmail(
		subject=_("Document Follow Notification"),
		recipients=[receiver],
		template="document_follow",
		args={"docinfo": docinfo, "timeline": timeline},
	)
	return True


def send_document_follow_mails(frequency):
	"""Own the Follow scheduler job's read and mail transaction boundaries."""
	for user in core.get_user_list(frequency):
		# End the previous read-only snapshot, including the recipient-list query.
		# This handler runs inside ScheduledJobType after Start logging commits.
		frappe.db.rollback()
		message, _docinfo = get_message_for_user(frequency, user)
		# A fresh SELECT in the same REPEATABLE-READ transaction is insufficient
		# for authorization revocation; the final pass needs a new snapshot.
		frappe.db.rollback()
		if message and send_email_alert(user, frequency):
			# Match the standard Follow job's per-recipient mail queue boundary.
			frappe.db.commit()


def send_hourly_updates():
	send_document_follow_mails("Hourly")


def send_daily_updates():
	send_document_follow_mails("Daily")


def send_weekly_updates():
	send_document_follow_mails("Weekly")
