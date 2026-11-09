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
        "Dinext Timesheet Workflow Digest": {
            "subject": '{{ _("Timesheets awaiting approval") }}',
            "response_html": ('<p>{{ _("Timesheets awaiting approval") }}</p><ul>'
                '{% for row in rows %}<li><a href="{{ row.link|e }}">{{ row.title|e }}</a>'
                ' — {{ row.count }} {{ _("position(s)") }}</li>{% endfor %}</ul>'),
        },
        "Dinext Timesheet Workflow Correction": {
            "subject": '{{ _("Timesheet correction required") }}: {{ timesheet_title }} / {{ doc.name }}',
            "response_html": ('<p>{{ _("Timesheet correction required") }}</p>'
                '<p><a href="{{ timesheet_link|e }}">{{ timesheet_title|e }}</a></p>'
                '<p>{{ _("Position") }}: <strong>{{ doc.name|e }}</strong> {{ position_label|e }}</p>' + comments),
        },
    }


def default_email_templates():
    names=("Dinext Workflow Action","Dinext Workflow Digest","Dinext Workflow Correction",
        "Dinext Timesheet Workflow Digest","Dinext Timesheet Workflow Correction",
        "Dinext Workflow Deadline Digest","Dinext Timesheet Workflow Deadline Digest")
    return {name:{"subject":('{{ header_title }}: {{ summary }}' if 'Digest' in name else
        '{{ header_title }}: {{ timesheet_title if is_timesheet else document_title|truncate(100) }}'),
        "response_html":'{% include "templates/emails/dinext_workflow.html" %}'} for name in names}


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
		"Dinext Timesheet Workflow Digest": {
			"subject": "Timesheets awaiting approval",
			"response_html": (
				"<p>Timesheets awaiting approval:</p><ul>"
				"{% for row in rows %}<li><a href=\"{{ row.link }}\">"
				"{{ row.title }}</a> — {{ row.count }} position(s)</li>{% endfor %}</ul>"
			),
		},
	}
	return templates


def is_known_default_template(name, existing):
    if not existing.get("use_html"):
        return False
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
