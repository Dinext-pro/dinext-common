import logging
import os

def get_custom_logger(name="dinext_projects", log_file="has_permission.log", log_dir="/home/frappe/frappe-bench/logs", level=logging.INFO):
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.hasHandlers():
        file_handler = logging.FileHandler(os.path.join(log_dir, log_file))
        file_handler.setLevel(level)

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

    return logger



import frappe
logger = get_custom_logger()
logger.info("dinext_projects.permissions loaded successfully")

@frappe.whitelist()
def has_permission(
    doctype,
    ptype="read",
    doc=None,
    user=None,
    raise_exception=True,
    *,
    parent_doctype=None,
    debug=False,
) -> bool:
    #logger.info(
    #    f"has_permission called with arguments: doctype={doctype}, ptype={ptype}, doc={doc}, user={user}, raise_exception={raise_exception}, parent_doctype={parent_doctype}, debug={debug}")
    from frappe.permissions import has_permission as og_has_permission
    cur_user = frappe.session.user
    if user:
        frappe.set_user(user)
        logger.info(f"user set to: '{user}'")

    res = og_has_permission(doctype=doctype,
                            ptype=ptype,
                            doc=doc,
                            user=user,
                            raise_exception=raise_exception,
                            parent_doctype=parent_doctype,
                            debug=debug)
    #logger.info(f"Does user have {ptype} permission for {doc}? {res}")

    if user:
        frappe.set_user(cur_user)
        logger.info(f"user set back to: '{cur_user}'")

    return res

@frappe.whitelist()
def get_doc_permissions(doctype, doc, user=None, ptype=None, debug=False):

    #logger.info(f"get_doc_permissions called with arguments: doc={doc}, user={user}, ptype={ptype}, debug={debug}")
    meta = frappe.get_meta(doctype)
    #logger.info(f"pulled meta, got doc with get_doc('{meta.name}','{doc}'")
    doc = frappe.get_doc(meta.name, doc)

    cur_user = frappe.session.user
    if user:
        frappe.set_user(user)
        #logger.info(f"user set to: '{user}'")

    from frappe.permissions import get_doc_permissions as og_get_doc_permissions
    res = og_get_doc_permissions(doc=doc, user=user, ptype=ptype, debug=debug)
    #logger.info("Doc permissions: " + frappe.as_json(res))

    if user:
        frappe.set_user(cur_user)
        #logger.info(f"user set back to: '{cur_user}'")

    return res
#print("dinord_erpnext_customization.permissions loaded successfully")

@frappe.whitelist()
def get_users_with_role(role: str) -> list[str]:
    
    from frappe.utils.user import get_users_with_role as og_get_users_with_role
    
    cur_user = frappe.session.user
    frappe.set_user('Administrator')
    
    res = og_get_users_with_role(role)
    
    frappe.set_user(cur_user)
    return res