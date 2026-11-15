"""Editable, escaped defaults shared by all workflow email profiles."""


def previous_email_templates():
    document = '<p><strong>{{ doc.doctype|e }} {{ doc.name|e }}</strong></p><p><a href="{{ document_link|e }}">{{ _("Open document") }}</a></p>'
    comments = ('{% for comment in entry_context.get("comments", []) %}'
        '<p>{% if comment.get("system") %}{{ _("Automatic workflow transition") }}: {% endif %}{{ comment.actor|e }} — {{ comment.at|e }}</p><pre>{{ comment.text|e }}</pre>{% endfor %}')
    digest = ('<p>{{ _("Pending workflow approvals") }}: {{ workflow_state|e }}</p><ul>'
        '{% for row in rows %}<li><a href="{{ row.link|e }}">{{ row.title|e }}</a>'
        '{% if row.count > 1 %} ({{ row.count }}){% endif %}</li>{% endfor %}</ul>')
    return {
        "Dinext Workflow Action": {
            "subject": '{{ _("Approval required") }}: {{ doc.doctype }} {{ doc.name }}',
            "response_html": '<p>{{ _("Approval required") }}</p>' + document,
        },
        "Dinext Workflow Correction": {
            "subject": '{{ _("Correction required") }}: {{ doc.doctype }} {{ doc.name }}',
            "response_html": '<p>{{ _("Correction required") }}</p>' + document + comments,
        },
        "Dinext Workflow Digest": {
            "subject": '{{ _("Pending workflow approvals") }}: {{ workflow_state }}',
            "response_html": digest,
        },
    }


def default_email_templates():
    names=("Dinext Workflow Action","Dinext Workflow Digest","Dinext Workflow Correction",
        "Dinext Workflow Deadline Digest")
    return {name:{"subject":('{{ header_title }}: {{ summary }}' if 'Digest' in name else
        '{{ header_title }}: {{ timesheet_title if is_timesheet else document_title|truncate(100) }}'),
        "response_html":'{% include "templates/emails/dinext_workflow.html" %}'} for name in names}


def _provided(hook):
    import frappe

    if not getattr(frappe.local, "site", None):
        return {}
    return {
        key: value
        for provider in frappe.get_hooks(hook)
        for key, value in frappe.get_attr(provider)().items()
    }


def renderable_email_templates():
    """Include defaults from installed apps without making them Common-owned seeds."""
    return default_email_templates() | {
        name: template["current"]
        for name, template in _provided("workflow_approval_email_template_providers").items()
    }


def domain_email_profiles():
    return _provided("workflow_approval_email_profile_providers")


def domain_email_template(tasks, field):
    profiles = domain_email_profiles()
    for task in tasks:
        template = profiles.get(task.reference_doctype, {}).get(field)
        if template:
            return template
    return None


def legacy_email_templates():
	templates = {
		"Dinext Workflow Action": {
			"subject": "Workflow Action on {{ doc.doctype }}: {{ doc.name }}",
			"response_html": (
				"<p>A workflow action is required for "
				"<strong>{{ doc.doctype }} {{ doc.name }}</strong>.</p>"
			),
		},
		"Dinext Workflow Correction": {
			"subject": "Correction required for {{ doc.doctype }}: {{ doc.name }}",
			"response_html": (
				"<p><strong>{{ doc.doctype }} {{ doc.name }}</strong> "
				"requires correction.</p>"
			),
		},
		"Dinext Workflow Digest": {
			"subject": "Pending workflow approvals",
			"response_html": (
				"<p>Pending workflow approvals:</p><ul>"
				"{% for row in rows %}<li><a href=\"{{ row.link }}\">"
				"{{ row.title }}</a>{% if row.count > 1 %} ({{ row.count }}){% endif %}"
				"</li>{% endfor %}</ul>"
			),
		},
	}
	return templates


def is_known_default_template(name, existing):
    if not existing.get("use_html"):
        return False
    provided = _provided("workflow_approval_email_template_providers").get(name)
    if provided:
        return any(
            all(existing.get(field) == value for field, value in version.items())
            for version in (provided["current"], *provided.get("previous", ()))
        )
    current = default_email_templates().get(name)
    if not current:
        return False
    previous = previous_email_templates().get(name, {})
    former = dict(previous)
    if not former:
        return all(existing.get(key) == item for key,item in current.items())
    former["response_html"] = former["response_html"].replace('{% if comment.get("system") %}{{ _("Automatic workflow transition") }}: {% endif %}', '')
    return any(all(existing.get(key) == item for key, item in version.items())
        for version in (current, previous, former, legacy_email_templates().get(name, {})) if version)
