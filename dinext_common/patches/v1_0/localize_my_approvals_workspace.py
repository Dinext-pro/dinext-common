# ruff: noqa: RUF001 -- exact legacy metadata labels
"""Migrate the My Approvals Workspace without replacing site customizations."""

from dinext_common.setup.personal_workspace import localize_workspace


def execute():
	localize_workspace(
		'Мои согласования',
		'My Approvals',
		headings={
			'Мои согласования': 'My Approvals',
			'Контроль': 'Approval Control',
		},
		widgets={
			'My open approvals': 'Awaiting My Decision',
			'Новые сегодня': 'New Approvals Today',
			'My completed approvals': 'My Decisions in the Last 30 Days',
			'Автоматически выполнено за 30 дней': 'Automatic Decisions in the Last 30 Days',
			'My Approvals': 'My Approval Queue',
			'Открытые раунды': 'Open Approval Rounds',
			'Сбои': 'Approval Issues',
			'Самое долгое ожидание': 'Longest Approval Wait',
			'Решений за 30 дней': 'Decisions in the Last 30 Days',
		},
		public_without_module=True,
		hub_description=(
			"Персональная очередь, история и контроль согласований.",
			"Personal queue, history and approval monitoring.",
		),
	)
