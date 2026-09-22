frappe.provide("dinext_common.my_approvals");

dinext_common.my_approvals.mount = function (root) {
	const element = root?.querySelector?.(".dinext-my-approvals") || root;
	const $root = $(element);
	const escape = (value) => frappe.utils.escape_html(String(value ?? ""));

	const routeLink = (row) =>
		`<a href="/app/${frappe.router.slug(row.reference_doctype)}/${encodeURIComponent(
			row.reference_name
		)}">${escape(row.source_title || row.reference_name)}</a>`;

	const vote = (task, transition) => {
		const submit = async (comment = "") => {
			await frappe.xcall("dinext_common.workflow_approval.api.vote", {
				task_name: task.name,
				transition_uuid: transition.transition_uuid,
				comment,
				request_id:
					window.crypto?.randomUUID?.() ||
					`${Date.now()}-${Math.random().toString(16).slice(2)}`,
			});
			frappe.show_alert({ message: __("Workflow action recorded"), indicator: "green" });
			load();
		};
		if (!transition.comment_is_required) return submit();
		frappe.prompt(
			[
				{
					fieldname: "comment",
					fieldtype: "Small Text",
					label: __("Comment"),
					reqd: 1,
				},
			],
			(values) => submit(values.comment),
			__("Comment required for {0}", [__(transition.action)]),
			__("Apply")
		);
	};

	const actionButtons = (row) =>
		(row.available_transitions || [])
			.map(
				(transition) =>
					`<button class="btn btn-xs btn-default dinext-approval-action"
						data-task="${escape(row.name)}"
						data-transition="${escape(transition.transition_uuid)}">
						${escape(__(transition.action))}
					</button>`
			)
			.join(" ");

	const table = (rows, { actions = false } = {}) => {
		if (!rows.length) return `<p class="text-muted">${__("No records")}</p>`;
		return `<div class="table-responsive"><table class="table table-bordered">
			<thead><tr>
				<th>${__("Document")}</th><th>${__("Workflow")}</th>
				<th>${__("State")}</th><th>${actions ? __("Actions") : __("Result")}</th>
			</tr></thead>
			<tbody>${rows
				.map(
					(row) => `<tr>
						<td>${routeLink(row)}<div class="text-muted small">${escape(
							row.reference_doctype
						)}</div></td>
						<td>${escape(row.workflow)}</td>
						<td>${escape(row.workflow_state)}</td>
						<td>${actions ? actionButtons(row) : escape(row.action || row.status)}</td>
					</tr>`
				)
				.join("")}</tbody>
		</table></div>`;
	};

	const chart = (rows) => {
		if (!rows.length) return `<p class="text-muted">${__("No pending approvals")}</p>`;
		const max = Math.max(...rows.map((row) => row.count), 1);
		return `<div class="dinext-approval-chart" role="img" aria-label="${escape(
			__("Pending approvals by document type")
		)}">${rows
			.map(
				(row) => `<div class="dinext-approval-bar">
					<span>${escape(row.doctype)}</span>
					<div style="width:${Math.max(8, (row.count / max) * 100)}%">${row.count}</div>
				</div>`
			)
			.join("")}</div>`;
	};

	const render = (data) => {
		const monitoringTasks = data.monitoring.reduce(
			(total, row) => total + row.active_task_count,
			0
		);
		const monitoringApprovers = new Set(
			data.monitoring.flatMap((row) => row.pending_approvers.split(", ").filter(Boolean))
		).size;
		const monitoringAge = data.monitoring.reduce(
			(maximum, row) => Math.max(maximum, row.age_hours),
			0
		);
		const monitoring = data.can_monitor
			? `<section><h3>${__("Monitoring")}</h3>
				<div class="row">
					<div class="col-sm-3"><strong>${monitoringTasks}</strong><br>${__(
						"Active Tasks"
					)}</div>
					<div class="col-sm-3"><strong>${data.monitoring.length}</strong><br>${__(
						"Documents in approval"
					)}</div>
					<div class="col-sm-3"><strong>${monitoringApprovers}</strong><br>${__(
						"Pending Approvers"
					)}</div>
					<div class="col-sm-3"><strong>${monitoringAge.toFixed(1)}</strong><br>${__(
						"Maximum age (hours)"
					)}</div>
				</div>
				<p><a href="/app/query-report/Approval%20Monitoring">${__(
					"Open approval monitoring report"
				)}</a></p>
				${table(data.monitoring)}
			</section>`
			: "";
		$root.html(`
			<section><h3>${__("Pending approvals by document type")}</h3>${chart(
				data.by_doctype
			)}</section>
			<section><h3>${__("My approval queue")}</h3>${table(data.queue, {
				actions: true,
			})}</section>
			<section><h3>${__("My approval history")}</h3>${table(data.history)}</section>
			${monitoring}
		`);
		$root.find(".dinext-approval-action").on("click", function () {
			const task = data.queue.find((row) => row.name === this.dataset.task);
			const transition = task?.available_transitions.find(
				(row) => row.transition_uuid === this.dataset.transition
			);
			if (task && transition) vote(task, transition);
		});
	};

	const load = async () => {
		$root.html(`<div class="text-muted">${__("Loading…")}</div>`);
		const data = await frappe.xcall(
			"dinext_common.workflow_approval.api.get_approval_dashboard"
		);
		render(data);
	};

	load();
};
