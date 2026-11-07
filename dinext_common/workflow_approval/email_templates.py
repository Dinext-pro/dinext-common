"""Editable, escaped defaults shared by all workflow email profiles."""


def default_email_templates():
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
