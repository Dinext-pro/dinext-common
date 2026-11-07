const commentCases = require("../../dinext_common/tests/fixtures/approval_comment_normalization.json");

describe("My Approvals audit corrections", () => {
	let fixture;
	let reportRequest = 0;
	before(() => cy.task("approvalAuditSeed").then((data) => { fixture = data; }));
	after(() => cy.task("approvalAuditCleanup"));

	function openReport(name, user = fixture.alice) {
		const alias = `readyReport${++reportRequest}`;
		cy.login(user, fixture.password);
		cy.intercept({method: "GET", pathname: "/api/method/frappe.desk.query_report.run", query: {report_name: name}}).as(alias);
		// The isolated acceptance site has no background workers. Use the
		// normal report route option to render prepared reports synchronously.
		cy.openDesk(`/app/query-report/${encodeURIComponent(name)}?ignore_prepared_report=1`);
		cy.wait(`@${alias}`).then(({response}) => {
			expect(response.statusCode).to.eq(200);
			const expected = response.body.message.result;
			cy.window().should((win) => {
				const report = win.frappe.query_report;
				expect(report.report_name).to.eq(name);
				expect(report.raw_data?.result).to.deep.eq(expected);
				expect(report.data).to.have.length(expected.length);
				if (expected.length) expect(report.datatable).to.be.ok;
			});
		});
	}

	function assertTranslatedReportCells() {
		cy.window().then((win) => {
			const report = win.frappe.query_report;
			const fields = ["reference_doctype", "workflow_state", "status", "round_status", "action", "completion_source", "group_label"];
			for (const field of fields) {
				const column = report.datatable.datamanager.getColumns().find((item) => item.id === field);
				if (!column) continue;
				const row = report.data.find((item) => item[field]);
				if (!row || (field === "group_label" && row.group_type !== "Document Type")) continue;
				const raw = row[field];
				const label = win.__(raw, null, field === "completion_source" ? "Approval completion source" : undefined);
				expect(label, `${report.report_name} ${field}`).to.match(/[А-Яа-яЁё]/);
				cy.contains(`.dt-scrollable .dt-cell--col-${column.colIndex}`, label).scrollIntoView().should("be.visible");
				if (field === "reference_doctype" || field === "group_label") expect(raw).to.eq("Note");
			}
			if (["My Approvals", "Approval Duration"].includes(report.report_name)) {
				expect(report.chart.data.labels).to.include(win.__("Note"));
			}
			if (report.data.some((row) => row.reference_doctype === "Note")) {
				cy.get('.dt-scrollable a[href*="/app/note/"]').should("exist");
			}
		});
	}

	function assertCommentValidity() {
		cy.get(".modal:visible [data-fieldname=comment] textarea").as("comment").should("be.focused");
		cy.get(".modal:visible .btn-modal-primary").as("submit").should("be.disabled");
		for (const text of ["   ", "<p>&nbsp;</p>", "\u200b\u0000", "x".repeat(4001)]) {
			cy.get("@comment").invoke("val", text).trigger("input");
			cy.get("@submit").should("be.disabled");
		}
		cy.get("@comment").invoke("val", "Reason for approval").trigger("input");
		cy.get("@submit").should("be.enabled");
		cy.get("@comment").invoke("val", " ").trigger("input");
		cy.get("@submit").should("be.disabled");
		cy.get(".modal:visible .modal-header .btn-modal-close").click();
	}

	it("filters canonical personal actions without setup read and counts UUID thresholds separately", () => {
		cy.intercept("POST", "**/api/method/frappe.client.validate_link").as("actionLinkValidation");
		openReport("My Approvals");
		cy.window().should((win) => {
			const row = win.frappe.query_report.data.find((item) => item.name === fixture.tasks.Main);
			expect(row.available_actions).to.eq("Approve");
			expect(row.progress).to.eq("Approve 1/2; Reject 0/1");
			expect(win.frappe.query_report.data.some((item) => item.name === fixture.tasks.Denied)).to.eq(false);
		});
		cy.window().should((win) => expect(win.frappe.query_report.get_filter("action").df.fieldtype).to.eq("Data"));
		cy.window().then((win) => win.frappe.query_report.set_filter_value("action", "Approve"));
		cy.window().should((win) => expect(win.frappe.query_report.data).to.have.length(1));
		cy.window().then((win) => win.frappe.query_report.set_filter_value("action", "Reject"));
		cy.window().should((win) => expect(win.frappe.query_report.data).to.have.length(0));
		cy.get("@actionLinkValidation.all").should("have.length", 0);
	});

	it("matches literal-control normalization in a real browser DOM", () => {
		cy.login(fixture.alice, fixture.password);
		cy.openDesk(`/app/note/${encodeURIComponent(fixture.prefix + "Main")}`);
		cy.window().then((win) => {
			const normalize = win.frappe.dinext.normalizeWorkflowComment;
			expect(normalize("\u200b\u0000")).to.eq("");
			expect(normalize("<p>&nbsp;</p>")).to.eq("");
			expect(normalize("&amp;lt;b&amp;gt;&amp;lt;/b&amp;gt;")).to.eq("&lt;b&gt;&lt;/b&gt;");
			for (const {raw, normalized} of commentCases) expect(normalize(raw), JSON.stringify(raw)).to.eq(normalized);
		});
	});

	it("disables normalized invalid comments in the single action dialog", () => {
		cy.login(fixture.alice, fixture.password);
		cy.openDesk(`/app/note/${encodeURIComponent(fixture.prefix + "Main")}`);
		cy.window().then((win) => win.frappe.dinext.withWorkflowComment({action: "Approve", comment_is_required: 1}, () => {
			throw new Error("Invalid-comment test must not submit a vote");
		}));
		assertCommentValidity();
	});

	it("applies the same validity and field focus to selected report rows", () => {
		openReport("My Approvals");
		cy.window().then((win) => {
			const report = win.frappe.query_report;
			report.datatable.rowmanager.checkRow(report.data.findIndex((row) => row.name === fixture.tasks.Main), true);
		});
		cy.contains("button", "Apply selected").click();
		assertCommentValidity();
	});

	it("renders Russian report values and legends while retaining canonical data", () => {
		openReport("My Approval History", fixture.bob);
		assertTranslatedReportCells();
		cy.contains(".dt-scrollable .dt-cell", "Вручную").scrollIntoView().should("be.visible");
		cy.window().then((win) => {
			const completed = win.__("Completed");
			expect(completed).to.match(/[А-Яа-яЁё]/);
			cy.contains(".dt-scrollable .dt-cell", completed).scrollIntoView().should("be.visible");
		});
		cy.window().should((win) => {
			const report = win.frappe.query_report;
			expect(report.data.some((row) => row.completion_source === "Manual" && row.status === "Completed")).to.eq(true);
			expect(report.chart.data.datasets.map((set) => set.name)).to.include("Вручную");
		});
		for (const name of ["My Approvals", "Approval Monitoring", "Approval Load", "Approval Duration"]) {
			openReport(name, fixture.bob);
			assertTranslatedReportCells();
			cy.window().should((win) => {
				const report = win.frappe.query_report;
				expect(report.report_name).to.eq(name);
				expect(report.data).to.have.length.greaterThan(0);
			});
		}
		cy.window().should((win) => {
			expect(win.frappe.query_report.chart.data.datasets.map((set) => set.name)).to.deep.eq(["Среднее", "Максимум"]);
		});
	});

	it("resets stale duration filters and uses the card's timestamp cutoff", () => {
		openReport("Approval Duration", fixture.monitor);
		cy.window().then(async (win) => {
			await win.frappe.query_report.set_filter_value("workflow", "stale-workflow");
			await win.frappe.query_report.set_filter_value("reference_doctype", "Issue");
			// A card is opened from another Desk page; same-path set_route is a no-op.
			// Keep this window so the cached report still contains stale filters.
			await win.frappe.set_route("Form", "Note", fixture.prefix + "Main");
			const card = await win.frappe.xcall("dinext_common.workflow_approval.api.control_decision_count");
			expect(card.route_options.completed_since).to.match(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}/);
			win.frappe.route_options = card.route_options;
			await win.frappe.set_route(...card.route);
		});
		cy.window().should((win) => {
			const report = win.frappe.query_report;
			expect(report.get_filter_value("workflow")).to.eq("");
			expect(report.get_filter_value("reference_doctype")).to.eq("");
			expect(report.get_filter_value("completed_since")).to.be.ok;
			expect(report.data.reduce((sum, row) => sum + row.manual_count, 0)).to.be.greaterThan(0);
		});
	});


	it("localizes the native completion filter and sends canonical Manual after report reuse", {defaultCommandTimeout: 15000}, () => {
		cy.intercept("GET", "**/api/method/frappe.desk.query_report.run*", (request) => {
			const url = new URL(request.url);
			if (url.searchParams.get("report_name") === "My Approval History" && JSON.parse(url.searchParams.get("filters") || "{}").completion_source === "Manual") request.alias = "canonicalManual";
		});
		for (const [user, label] of [[fixture.bob, "Вручную"], [fixture.alice, "Manual"]]) {
			openReport("My Approval History", user);
			for (let visit = 0; visit < 2; visit++) {
				cy.get('[data-fieldname="completion_source"] select option[value="Manual"]').should("have.text", label);
				cy.get('[data-fieldname="completion_source"] select').select("");
				cy.get('[data-fieldname="completion_source"] select').select("Manual").should("have.value", "Manual");
				cy.wait("@canonicalManual").then(({request, response}) => {
					expect(response.statusCode).to.eq(200);
					expect(JSON.parse(new URL(request.url).searchParams.get("filters")).completion_source).to.eq("Manual");
				});
				cy.window().should((win) => {
					expect(win.frappe.query_report.get_filter_value("completion_source")).to.eq("Manual");
					expect(win.frappe.query_report.data.length).to.be.greaterThan(0);
					expect(win.frappe.query_report.data.every((row) => row.completion_source === "Manual")).to.eq(true);
				});
				if (visit === 0) {
					cy.window().then((win) => win.frappe.set_route("query-report", "My Approvals"));
					cy.window().should((win) => expect(win.frappe.query_report.report_name).to.eq("My Approvals"));
					cy.window().then((win) => {
						win.frappe.route_options = {completion_source: "Manual", ignore_prepared_report: 1};
						return win.frappe.set_route("query-report", "My Approval History");
					});
					cy.window().should((win) => expect(win.frappe.query_report.report_name).to.eq("My Approval History"));
				}
			}
		}
	});

	it("returns localized HTTP validation for votes, bulk and reset without changing tasks", {defaultCommandTimeout: 30000}, () => {
		let before;
		async function post(win, method, args) {
			const response = await win.fetch(`/api/method/dinext_common.workflow_approval.${method}`, {
				method: "POST", headers: {"Content-Type": "application/json", "X-Frappe-CSRF-Token": win.frappe.csrf_token},
				body: JSON.stringify(args),
			});
			return {status: response.status, body: await response.json()};
		}
		function expected(language, long) {
			return language === "ru" ? (long ? "Комментарий процесса не может превышать 4000 символов" : "Для этого действия процесса требуется комментарий")
				: (long ? "Workflow comments cannot exceed 4000 characters" : "A comment is required for this workflow action");
		}
		function assertError(response, message) {
			expect(response.status).to.eq(417);
			expect(response.body.exc_type).to.eq("WorkflowCommentValidationError");
			const messages = JSON.parse(response.body._server_messages).map((entry) => JSON.parse(entry).message);
			expect(messages).to.deep.eq([message]);
		}
		openReport("My Approvals");
		cy.window().then(async (win) => {
			before = await win.frappe.xcall("frappe.client.get", {doctype: "Workflow Task", name: fixture.tasks.Main});
			for (const language of ["ru", "en"]) for (const long of [false, true]) {
				const comment = long ? "x".repeat(4001) : "<p>&nbsp;</p>";
				const args = {transition_uuid: fixture.transition_uuid, comment, _lang: language};
				assertError(await post(win, "api.vote", {...args, task_name: fixture.tasks.Main}), expected(language, long));
				assertError(await post(win, "api.apply_workflow", {...args, doc: {doctype: "Note", name: fixture.prefix + "Main"}, action: "Approve"}), expected(language, long));
				const bulk = await post(win, "api.bulk_task_vote", {...args, items: [{task_name: fixture.tasks.Main, transition_uuid: fixture.transition_uuid}]});
				expect(bulk.status).to.eq(200);
				expect(bulk.body.message.succeeded).to.have.length(0);
				expect(bulk.body.message.failed[0].error).to.eq(expected(language, long));
				expect(bulk.body._server_messages).to.be.undefined;
			}
			const after = await win.frappe.xcall("frappe.client.get", {doctype: "Workflow Task", name: fixture.tasks.Main});
			expect(after).to.deep.eq(before);
		});
		cy.login("Administrator");
		cy.openDesk(`/app/note/${encodeURIComponent(fixture.prefix + "Main")}`);
		cy.window().then(async (win) => {
			for (const language of ["ru", "en"]) for (const long of [false, true]) {
				const reason = long ? "x".repeat(4001) : "<p>&nbsp;</p>";
				assertError(await post(win, "api.reset_round", {round_id: before.approval_round_id, reason, _lang: language}), expected(language, long));
				assertError(await post(win, "api.reset_rounds", {round_ids: [before.approval_round_id], reason, _lang: language}), expected(language, long));
			}
			const after = await win.frappe.xcall("frappe.client.get", {doctype: "Workflow Task", name: fixture.tasks.Main});
			expect(after).to.deep.eq(before);
		});
	});

	it("commits the permitted bulk item and preserves the denied item's audit record", () => {
		openReport("My Approvals");
		cy.window().then(async (win) => {
			const result = await win.frappe.xcall("dinext_common.workflow_approval.api.bulk_task_vote", {
				items: [fixture.tasks.Main, fixture.tasks.Denied].map((name) => ({task_name: name, transition_uuid: fixture.transition_uuid, action: "Approve"})),
				comment: "Synthetic accepted bulk vote", request_id: fixture.prefix + "bulk",
			});
			expect(result.succeeded).to.have.length(1);
			expect(result.failed).to.have.length(1);
		});
		cy.login(fixture.bob, fixture.password);
		cy.openDesk(`/app/note/${encodeURIComponent(fixture.prefix + "Main")}`);
		cy.window().should((win) => expect(win.cur_frm.doc.title).to.eq("Approved"));
		cy.window().then(async (win) => {
			const task = await win.frappe.xcall("frappe.client.get", {doctype: "Workflow Task", name: fixture.tasks.Denied});
			expect(task.status).to.eq("Working");
			expect(task.vote_comment || "").to.eq("");
		});
	});
});
