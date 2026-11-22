"""Local Gunicorn factory with the site selection used by ``bench serve``."""

from frappe import app
from frappe.utils.bench_helper import get_sites


def create_application():
	"""Keep the configured default site and Frappe's static-asset middleware."""
	sites = get_sites("")
	app._site = sites[0] if sites else None
	app._sites_path = "."
	return app.application_with_statics()
