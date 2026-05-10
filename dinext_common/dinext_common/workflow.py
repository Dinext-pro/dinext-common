import frappe

@frappe.whitelist()
def get_transitions(
	doc, user = None, workflow = None, raise_exception: bool = False
) -> list[dict]:
    from frappe.model.workflow import get_transitions as og_get_transitions
    cur_user = frappe.session.user
    if user:
        frappe.set_user(user)

    res = og_get_transitions(doc, workflow, raise_exception)

    if user:
        frappe.set_user(cur_user)
    return res