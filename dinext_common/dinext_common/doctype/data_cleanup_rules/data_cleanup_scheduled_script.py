# Code for Server Script (Scheduler Event, Daily).
# Copy this entire file content into the Server Script "Script" field.
# Uses only safe_exec API: frappe.*, log. No imports.

def run():
	log("Data Cleanup: start")
	rules = frappe.get_doc("Data Cleanup Rules")
	today = frappe.utils.getdate()
	deleted_total = 0

	# 1. Version Cleanup Rule
	for row in (rules.version_rules or []):
		if not row.get("enabled") or not row.get("days"):
			continue
		cutoff = frappe.utils.add_days(today, -int(row.days))
		filters = [["creation", "<", cutoff]]
		if row.get("ref_doctype"):
			filters.append(["ref_doctype", "=", row.ref_doctype])
		names = frappe.get_all("Version", filters=filters, pluck="name")
		count = 0
		for name in names:
			try:
				frappe.delete_doc("Version", name, force=1)
				count += 1
			except Exception:
				log_error("Data Cleanup Version delete error for %s" % (name,))
		if count:
			frappe.db.commit()
		deleted_total += count
		log("Data Cleanup Version rule days=%s ref_doctype=%s deleted=%s" % (
			row.days, row.get("ref_doctype") or "", count))

	# 2. Comment Cleanup Rule (age = modified of linked document)
	for row in (rules.comment_rules or []):
		if not row.get("enabled") or not row.get("days"):
			continue
		cutoff = frappe.utils.add_days(today, -int(row.days))
		doctypes_to_consider = [row.reference_doctype] if row.get("reference_doctype") else frappe.get_all(
			"Comment", filters=[["reference_doctype", "!=", ""]], pluck="reference_doctype", distinct=1)
		count = 0
		for ref_dt in (doctypes_to_consider or []):
			if not ref_dt or not frappe.db.exists("DocType", ref_dt):
				continue
			ref_names = frappe.get_all(ref_dt, filters=[["modified", "<", cutoff]], pluck="name")
			if not ref_names:
				continue
			comment_filters = [["reference_doctype", "=", ref_dt], ["reference_name", "in", ref_names]]
			if row.get("comment_type"):
				comment_filters.append(["comment_type", "=", row.comment_type])
			comment_names = frappe.get_all("Comment", filters=comment_filters, pluck="name")
			for name in comment_names:
				try:
					frappe.delete_doc("Comment", name, force=1)
					count += 1
				except Exception:
					log_error("Data Cleanup Comment delete error for %s" % (name,))
		if count:
			frappe.db.commit()
		deleted_total += count
		log("Data Cleanup Comment rule days=%s reference_doctype=%s deleted=%s" % (
			row.days, row.get("reference_doctype") or "all", count))

	# 3. File Cleanup Rule (age = modified of attached document)
	for row in (rules.file_rules or []):
		if not row.get("enabled") or not row.get("days"):
			continue
		cutoff = frappe.utils.add_days(today, -int(row.days))
		doctypes_to_consider = [row.attached_to_doctype] if row.get("attached_to_doctype") else frappe.get_all(
			"File", filters=[["attached_to_doctype", "!=", ""]], pluck="attached_to_doctype", distinct=1)
		count = 0
		for ref_dt in (doctypes_to_consider or []):
			if not ref_dt or not frappe.db.exists("DocType", ref_dt):
				continue
			ref_names = frappe.get_all(ref_dt, filters=[["modified", "<", cutoff]], pluck="name")
			if not ref_names:
				continue
			file_filters = [["attached_to_doctype", "=", ref_dt], ["attached_to_name", "in", ref_names]]
			if row.get("file_type"):
				file_filters.append(["file_type", "=", row.file_type])
			if row.get("visibility") == "Private":
				file_filters.append(["is_private", "=", 1])
			elif row.get("visibility") == "Public":
				file_filters.append(["is_private", "=", 0])
			if row.get("folder"):
				file_filters.append(["folder", "=", row.folder])
			if row.get("file_size") is not None:
				file_filters.append(["file_size", "=", int(row.file_size)])
			if row.get("attached_to_field"):
				file_filters.append(["attached_to_field", "=", row.attached_to_field])
			file_names = frappe.get_all("File", filters=file_filters, pluck="name")
			for name in file_names:
				try:
					frappe.delete_doc("File", name, force=1)
					count += 1
				except Exception:
					log_error("Data Cleanup File delete error for %s" % (name,))
		if count:
			frappe.db.commit()
		deleted_total += count
		log("Data Cleanup File rule days=%s attached_to_doctype=%s deleted=%s" % (
			row.days, row.get("attached_to_doctype") or "all", count))

	# 4. Communication Cleanup Rule (age = modified of linked document)
	for row in (rules.communication_rules or []):
		if not row.get("enabled") or not row.get("days"):
			continue
		cutoff = frappe.utils.add_days(today, -int(row.days))
		doctypes_to_consider = [row.reference_doctype] if row.get("reference_doctype") else frappe.get_all(
			"Communication", filters=[["reference_doctype", "!=", ""]], pluck="reference_doctype", distinct=1)
		count = 0
		for ref_dt in (doctypes_to_consider or []):
			if not ref_dt or not frappe.db.exists("DocType", ref_dt):
				continue
			ref_names = frappe.get_all(ref_dt, filters=[["modified", "<", cutoff]], pluck="name")
			if not ref_names:
				continue
			comm_filters = [["reference_doctype", "=", ref_dt], ["reference_name", "in", ref_names]]
			if row.get("communication_type"):
				comm_filters.append(["communication_type", "=", row.communication_type])
			if row.get("communication_medium"):
				comm_filters.append(["communication_medium", "=", row.communication_medium])
			comm_names = frappe.get_all("Communication", filters=comm_filters, pluck="name")
			for name in comm_names:
				try:
					frappe.delete_doc("Communication", name, force=1)
					count += 1
				except Exception:
					log_error("Data Cleanup Communication delete error for %s" % (name,))
		if count:
			frappe.db.commit()
		deleted_total += count
		log("Data Cleanup Communication rule days=%s reference_doctype=%s deleted=%s" % (
			row.days, row.get("reference_doctype") or "all", count))

	# 5. Event Cleanup Rule (age = latest of starts_on, ends_on, repeat_till)
	for row in (rules.event_rules or []):
		if not row.get("enabled") or not row.get("days"):
			continue
		cutoff = frappe.utils.add_days(today, -int(row.days))
		query = """
			SELECT name FROM tabEvent
			WHERE GREATEST(
				COALESCE(starts_on, '1000-01-01 00:00:00'),
				COALESCE(ends_on, '1000-01-01 00:00:00'),
				COALESCE(CONCAT(IFNULL(repeat_till, '1000-01-01'), ' 00:00:00'), '1000-01-01 00:00:00')
			) < %s
		"""
		args = [cutoff]
		if row.get("event_category"):
			query += " AND event_category = %s"
			args.append(row.event_category)
		if row.get("event_type"):
			query += " AND event_type = %s"
			args.append(row.event_type)
		if row.get("status"):
			query += " AND status = %s"
			args.append(row.status)
		names = [r[0] for r in frappe.db.sql(query, tuple(args))]
		count = 0
		for name in names:
			try:
				frappe.delete_doc("Event", name, force=1)
				count += 1
			except Exception:
				log_error("Data Cleanup Event delete error for %s" % (name,))
		if count:
			frappe.db.commit()
		deleted_total += count
		log("Data Cleanup Event rule days=%s deleted=%s" % (row.days, count))

	# 6. Workflow Cleanup Rule (Workflow Action and Workflow Task; age = modified of record)
	for row in (rules.workflow_rules or []):
		if not row.get("enabled") or not row.get("days"):
			continue
		cutoff = frappe.utils.add_days(today, -int(row.days))
		# Workflow Action: reference_doctype, status Open/Completed
		filters_wa = [["modified", "<", cutoff]]
		if row.get("reference_doctype"):
			filters_wa.append(["reference_doctype", "=", row.reference_doctype])
		if row.get("status"):
			filters_wa.append(["status", "=", row.status])
		if frappe.db.exists("DocType", "Workflow Action"):
			names = frappe.get_all("Workflow Action", filters=filters_wa, pluck="name")
			count = 0
			for name in names:
				try:
					frappe.delete_doc("Workflow Action", name, force=1)
					count += 1
				except Exception:
					log_error("Data Cleanup Workflow Action delete error for %s" % (name,))
			if count:
				frappe.db.commit()
			deleted_total += count
			log("Data Cleanup Workflow rule days=%s doctype=Workflow Action deleted=%s" % (row.days, count))
		# Workflow Task: field doc for ref doctype; status Completed -> Completed|Cancelled, Open -> Working
		filters_wt = [["modified", "<", cutoff]]
		if row.get("reference_doctype"):
			filters_wt.append(["doc", "=", row.reference_doctype])
		if row.get("status"):
			if row.status == "Completed":
				filters_wt.append(["status", "in", ["Completed", "Cancelled"]])
			elif row.status == "Open":
				filters_wt.append(["status", "=", "Working"])
		if frappe.db.exists("DocType", "Workflow Task"):
			names = frappe.get_all("Workflow Task", filters=filters_wt, pluck="name")
			count = 0
			for name in names:
				try:
					frappe.delete_doc("Workflow Task", name, force=1)
					count += 1
				except Exception:
					log_error("Data Cleanup Workflow Task delete error for %s" % (name,))
			if count:
				frappe.db.commit()
			deleted_total += count
			log("Data Cleanup Workflow rule days=%s doctype=Workflow Task deleted=%s" % (row.days, count))

	log("Data Cleanup: finished total_deleted=%s" % (deleted_total,))

run()
