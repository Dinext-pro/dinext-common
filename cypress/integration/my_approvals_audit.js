const commentCases = require("../../dinext_common/tests/fixtures/approval_comment_normalization.json");

describe("My Approvals audit corrections", () => {
	let fixture;
	before(() => cy.task("approvalAuditSeed").then((data) => { fixture = data; }));
	after(() => cy.task("approvalAuditCleanup"));

	function openReport(name, user = fixture.alice) {
		cy.login(user, fixture.password);
		cy.openDesk(`/app/query-report/${encodeURIComponent(name)}`);
		cy.window().should((win) => {
			expect(win.frappe.query_report.report_name).to.eq(name);
			expect(win.frappe.query_report.data).to.be.an("array");
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

	it("shows only personal actions and counts competing UUID thresholds separately", () => {
		openReport("My Approvals");
		cy.window().should((win) => {
			const row = win.frappe.query_report.data.find((item) => item.name === fixture.tasks.Main);
			expect(row.available_actions).to.eq("Approve");
			expect(row.progress).to.eq("Approve 1/2; Reject 0/1");
			expect(win.frappe.query_report.data.some((item) => item.name === fixture.tasks.Denied)).to.eq(false);
		});
		cy.window().then((win) => win.frappe.query_report.set_filter_value("action", "Reject"));
		cy.window().should((win) => expect(win.frappe.query_report.data).to.have.length(0));
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
		cy.contains(".dt-cell", "Вручную").should("be.visible");
		cy.contains(".dt-cell", "Выполнено").should("be.visible");
		cy.window().should((win) => {
			const report = win.frappe.query_report;
			expect(report.data.some((row) => row.completion_source === "Manual" && row.status === "Completed")).to.eq(true);
			expect(report.chart.data.datasets.map((set) => set.name)).to.include("Вручную");
		});
		for (const name of ["My Approvals", "Approval Monitoring", "Approval Load", "Approval Duration"]) {
			cy.openDesk(`/app/query-report/${encodeURIComponent(name)}`);
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

	it("commits the permitted bulk item and preserves the denied item's audit record", () => {
		cy.login(fixture.alice, fixture.password);
		cy.openDesk("/app/query-report/My%20Approvals");
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
