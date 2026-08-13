# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class DinextWorkspaceSettings(Document):
	pass


def has_permission(doc, ptype=None, user=None, debug=False):
	"""Deny read when the record lists roles the user does not hold."""
	if ptype and ptype != "read":
		return True

	roles = {row.role for row in (doc.get("roles") or []) if getattr(row, "role", None)}
	if not roles:
		return True

	user = user or frappe.session.user
	return bool(roles.intersection(frappe.get_roles(user)))
