"""Prepare only the disposable CI site for existing app unit tests."""
import datetime
import os
from pathlib import Path
import sys
import frappe

site = sys.argv[1]
assert site == 'ci.test', 'This helper only supports the disposable CI site'
frappe.init(site=site, sites_path=str(Path.cwd()))
frappe.connect()
try:
    if 'erpnext' in frappe.get_installed_apps():
        from erpnext.setup.utils import before_tests
        before_tests()
        year = datetime.date.today().year
        for company in frappe.get_all('Company', pluck='name'):
            if frappe.db.get_value('Company', company, 'default_holiday_list'):
                continue
            name = f'CI Holidays {year}'
            if not frappe.db.exists('Holiday List', name):
                doc = frappe.get_doc({'doctype': 'Holiday List', 'holiday_list_name': name,
                    'from_date': f'{year}-01-01', 'to_date': f'{year}-12-31',
                    'weekly_off': 'Sunday'})
                doc.get_weekly_off_dates()
                doc.insert(ignore_permissions=True)
            frappe.db.set_value('Company', company, 'default_holiday_list', name, update_modified=False)
    else:
        from frappe.desk.page.setup_wizard.install_fixtures import install
        install()
    frappe.db.commit()
finally:
    frappe.destroy()
