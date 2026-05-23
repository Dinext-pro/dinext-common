frappe.pages["fixture-analysis"].on_page_load = function (wrapper) {
	wrapper.fixture_analysis_page = new dinext_common.FixtureAnalysisPage(wrapper);
};

frappe.pages["fixture-analysis"].refresh = function (wrapper) {
	if (wrapper.fixture_analysis_page) {
		wrapper.fixture_analysis_page.refresh();
	}
};

(function () {
	window.dinext_common = window.dinext_common || {};

	class FixtureAnalysisPage {
		constructor(wrapper) {
			this.wrapper = wrapper;
			this.state = {
				overview: null,
				selectedApp: null,
				selectedDoctype: null,
				selectedRecordKey: null,
				status: "all",
				searchText: "",
			};

			this.ensureStyles();
			this.page = frappe.ui.make_app_page({
				parent: wrapper,
				title: __("Fixture Analysis"),
				single_column: true,
			});
			this.page.set_primary_action(__("Refresh"), () => this.refresh());
			this.makeToolbar();
			this.makeLayout();
			this.refresh();
		}

		makeToolbar() {
			this.statusField = this.page.add_field({
				fieldname: "status_filter",
				label: __("Status"),
				fieldtype: "Select",
				options: ["all", "file_only", "db_only", "changed", "equal"],
				default: "all",
				change: () => {
					this.state.status = this.statusField.get_value() || "all";
					this.loadRecords();
				},
			});

			this.searchField = this.page.add_field({
				fieldname: "search_text",
				label: __("Search"),
				fieldtype: "Data",
				change: () => {
					this.state.searchText = this.searchField.get_value() || "";
					this.debounceLoadRecords();
				},
			});
		}

		makeLayout() {
			$(this.page.main).html(`
				<div class="fixture-analysis-page">
					<div class="fixture-analysis-pane fixture-analysis-nav">
						<div class="fixture-analysis-pane-title">${__("Apps and DocTypes")}</div>
						<div class="fixture-analysis-pane-body fixture-analysis-apps"></div>
					</div>
					<div class="fixture-analysis-pane fixture-analysis-records-pane">
						<div class="fixture-analysis-pane-title">${__("Records")}</div>
						<div class="fixture-analysis-pane-body fixture-analysis-records"></div>
					</div>
					<div class="fixture-analysis-pane fixture-analysis-detail-pane">
						<div class="fixture-analysis-pane-title">${__("Details")}</div>
						<div class="fixture-analysis-pane-body fixture-analysis-detail"></div>
					</div>
				</div>
			`);

			this.$apps = $(this.page.main).find(".fixture-analysis-apps");
			this.$records = $(this.page.main).find(".fixture-analysis-records");
			this.$detail = $(this.page.main).find(".fixture-analysis-detail");
		}

		ensureStyles() {
			if (document.getElementById("fixture-analysis-page-styles")) {
				return;
			}

			const style = document.createElement("style");
			style.id = "fixture-analysis-page-styles";
			style.textContent = `
				.fixture-analysis-page {
					display: grid;
					grid-template-columns: minmax(280px, 0.9fr) minmax(320px, 1fr) minmax(360px, 1.2fr);
					gap: 16px;
					padding: 16px 0 8px;
				}
				.fixture-analysis-pane {
					border: 1px solid var(--border-color);
					background: var(--card-bg);
					min-height: 70vh;
					display: flex;
					flex-direction: column;
				}
				.fixture-analysis-pane-title {
					padding: 12px 14px;
					border-bottom: 1px solid var(--border-color);
					font-weight: 600;
				}
				.fixture-analysis-pane-body {
					padding: 12px;
					overflow: auto;
				}
				.fixture-analysis-app-card {
					border: 1px solid var(--border-color);
					margin-bottom: 10px;
				}
				.fixture-analysis-app-header {
					display: flex;
					justify-content: space-between;
					align-items: center;
					padding: 10px 12px;
					cursor: pointer;
					font-weight: 600;
				}
				.fixture-analysis-app-header.is-selected {
					background: var(--subtle-fg);
				}
				.fixture-analysis-counts,
				.fixture-analysis-record-meta {
					display: flex;
					flex-wrap: wrap;
					gap: 6px;
				}
				.fixture-analysis-record-header,
				.fixture-analysis-detail-header {
					display: flex;
					justify-content: space-between;
					align-items: flex-start;
					gap: 10px;
				}
				.fixture-analysis-detail-header {
					margin-bottom: 12px;
				}
				.fixture-analysis-record-link {
					font-size: 12px;
					white-space: nowrap;
				}
				.fixture-analysis-badge {
					border: 1px solid var(--border-color);
					border-radius: 999px;
					padding: 2px 8px;
					font-size: 11px;
					white-space: nowrap;
				}
				.fixture-analysis-badge.status-changed { color: var(--orange-600); }
				.fixture-analysis-badge.status-file_only { color: var(--green-600); }
				.fixture-analysis-badge.status-db_only { color: var(--red-600); }
				.fixture-analysis-badge.status-equal { color: var(--text-muted); }
				.fixture-analysis-doctypes {
					padding: 0 8px 10px;
				}
				.fixture-analysis-doctype {
					display: flex;
					justify-content: space-between;
					align-items: center;
					padding: 8px 10px;
					margin-top: 6px;
					cursor: pointer;
					border-radius: var(--border-radius-md);
				}
				.fixture-analysis-doctype.is-selected,
				.fixture-analysis-record.is-selected {
					background: var(--subtle-fg);
				}
				.fixture-analysis-record {
					border: 1px solid var(--border-color);
					padding: 10px 12px;
					margin-bottom: 10px;
					cursor: pointer;
				}
				.fixture-analysis-record-name {
					font-weight: 600;
					margin-bottom: 6px;
				}
				.fixture-analysis-field-card {
					border: 1px solid var(--border-color);
					padding: 10px 12px;
					margin-bottom: 10px;
				}
				.fixture-analysis-field-path {
					font-weight: 600;
					margin-bottom: 6px;
				}
				.fixture-analysis-values {
					display: grid;
					grid-template-columns: 1fr 1fr;
					gap: 10px;
					margin-top: 10px;
				}
				.fixture-analysis-value pre,
				.fixture-analysis-text-diff {
					margin: 0;
					white-space: pre-wrap;
					word-break: break-word;
				}
				.fixture-analysis-text-diff-hunk {
					border: 1px solid var(--border-color);
					margin-top: 10px;
					overflow: hidden;
				}
				.fixture-analysis-text-diff-line {
					display: grid;
					grid-template-columns: 48px 48px 20px minmax(0, 1fr);
					font-family: var(--font-monospace);
					font-size: 12px;
					line-height: 1.55;
					border-top: 1px solid var(--border-color);
				}
				.fixture-analysis-text-diff-line:first-child {
					border-top: none;
				}
				.fixture-analysis-text-diff-line.is-added {
					background: color-mix(in srgb, var(--green-100) 40%, transparent);
				}
				.fixture-analysis-text-diff-line.is-removed {
					background: color-mix(in srgb, var(--red-100) 40%, transparent);
				}
				.fixture-analysis-text-diff-line.is-context {
					background: transparent;
				}
				.fixture-analysis-text-diff-lineno,
				.fixture-analysis-text-diff-marker,
				.fixture-analysis-text-diff-code {
					padding: 4px 8px;
				}
				.fixture-analysis-text-diff-lineno {
					text-align: right;
					color: var(--text-muted);
					border-right: 1px solid var(--border-color);
				}
				.fixture-analysis-text-diff-marker {
					text-align: center;
					border-right: 1px solid var(--border-color);
					color: var(--text-muted);
				}
				.fixture-analysis-text-diff-code {
					white-space: pre-wrap;
					word-break: break-word;
				}
				.fixture-analysis-value details {
					margin-top: 8px;
				}
				.fixture-analysis-value summary {
					cursor: pointer;
					color: var(--text-muted);
				}
				.fixture-analysis-muted {
					color: var(--text-muted);
				}
				.fixture-analysis-warning {
					margin-top: 8px;
					color: var(--orange-600);
					font-size: 12px;
				}
				@media (max-width: 1360px) {
					.fixture-analysis-page {
						grid-template-columns: 1fr;
					}
					.fixture-analysis-pane {
						min-height: auto;
					}
				}
			`;
			document.head.appendChild(style);
		}

		refresh() {
			this.$apps.html(this.renderLoading(__("Loading fixture overview...")));
			this.$records.html(this.renderEmpty(__("Select a DocType to inspect records.")));
			this.$detail.html(this.renderEmpty(__("Select a record to inspect field diffs.")));

			this.call("dinext_common.fixture_analysis_api.get_fixture_analysis_overview")
				.then((message) => {
					this.state.overview = message;
					this.renderOverview();
					this.selectInitialDoctype();
				})
				.catch((error) => this.showError(this.$apps, error));
		}

		selectInitialDoctype() {
			if (this.state.selectedDoctype) {
				this.loadRecords();
				return;
			}

			const firstApp = (this.state.overview && this.state.overview.apps || [])[0];
			const firstDoctype = firstApp && firstApp.doctypes && firstApp.doctypes[0];
			if (firstApp && firstDoctype) {
				this.state.selectedApp = firstApp.app;
				this.state.selectedDoctype = firstDoctype.doctype;
				this.renderOverview();
				this.loadRecords();
			}
		}

		renderOverview() {
			const apps = (this.state.overview && this.state.overview.apps) || [];
			if (!apps.length) {
				this.$apps.html(this.renderEmpty(__("No installed apps with fixtures were discovered.")));
				return;
			}

			this.$apps.empty();
			apps.forEach((appInfo) => {
				const $card = $('<div class="fixture-analysis-app-card"></div>');
				const $header = $('<div class="fixture-analysis-app-header"></div>');
				const isSelected = this.state.selectedApp === appInfo.app;
				if (isSelected) {
					$header.addClass("is-selected");
				}

				$header.append($("<div></div>").text(appInfo.app));
				$header.append(this.makeCounts(appInfo.counts));
				$header.on("click", () => {
					this.state.selectedApp = appInfo.app;
					if (!appInfo.doctypes.some((item) => item.doctype === this.state.selectedDoctype)) {
						this.state.selectedDoctype = null;
						this.state.selectedRecordKey = null;
					}
					this.renderOverview();
					this.selectInitialDoctype();
				});

				$card.append($header);

				if (isSelected) {
					const $doctypes = $('<div class="fixture-analysis-doctypes"></div>');
					appInfo.doctypes.forEach((doctypeInfo) => {
						const $doctype = $('<div class="fixture-analysis-doctype"></div>');
						if (this.state.selectedDoctype === doctypeInfo.doctype) {
							$doctype.addClass("is-selected");
						}
						$doctype.append($("<div></div>").text(doctypeInfo.doctype));
						$doctype.append(this.makeCounts(doctypeInfo.counts));
						$doctype.on("click", () => {
							this.state.selectedApp = appInfo.app;
							this.state.selectedDoctype = doctypeInfo.doctype;
							this.state.selectedRecordKey = null;
							this.renderOverview();
							this.loadRecords();
						});

						if ((doctypeInfo.warnings || []).length) {
							$doctype.append(
								$('<div class="fixture-analysis-warning"></div>').text(
									doctypeInfo.warnings.join(", ")
								)
							);
						}

						$doctypes.append($doctype);
					});
					$card.append($doctypes);
				}

				this.$apps.append($card);
			});
		}

		loadRecords() {
			if (!this.state.selectedApp || !this.state.selectedDoctype) {
				return;
			}

			this.$records.html(this.renderLoading(__("Loading records...")));
			this.$detail.html(this.renderEmpty(__("Select a record to inspect field diffs.")));

			this.call("dinext_common.fixture_analysis_api.get_fixture_analysis_records", {
				app: this.state.selectedApp,
				doctype: this.state.selectedDoctype,
				status: this.state.status,
				search_text: this.state.searchText || null,
			})
				.then((message) => {
					this.state.recordsPayload = message;
					this.renderRecords();
				})
				.catch((error) => this.showError(this.$records, error));
		}

		renderRecords() {
			const payload = this.state.recordsPayload;
			const records = (payload && payload.records) || [];
			if (!records.length) {
				this.$records.html(this.renderEmpty(__("No records match the current filters.")));
				return;
			}

			this.$records.empty();
			records.forEach((record) => {
				const $record = $('<div class="fixture-analysis-record"></div>');
				if (this.state.selectedRecordKey === record.record_key) {
					$record.addClass("is-selected");
				}

				const $header = $('<div class="fixture-analysis-record-header"></div>');
				$header.append($('<div class="fixture-analysis-record-name"></div>').text(record.record_key));
				if (record.system_route) {
					$header.append(this.makeRecordLink(record.system_route));
				}
				$record.append($header);
				$record.append(
					$('<div class="fixture-analysis-record-meta"></div>')
						.append(this.makeBadge(record.status, record.status))
						.append(this.makeBadge(`${record.field_diff_count} fields`))
						.append(this.makeBadge(`${record.text_diff_count} text diffs`))
				);
				if ((record.changed_paths_preview || []).length) {
					$record.append(
						$('<div class="fixture-analysis-muted" style="margin-top: 8px;"></div>').text(
							record.changed_paths_preview.join(", ")
						)
					);
				}

				$record.on("click", () => {
					this.state.selectedRecordKey = record.record_key;
					this.renderRecords();
					this.loadRecordDetail(record.record_key);
				});

				this.$records.append($record);
			});
		}

		loadRecordDetail(recordKey) {
			this.$detail.html(this.renderLoading(__("Loading record details...")));

			this.call("dinext_common.fixture_analysis_api.get_fixture_analysis_record_detail", {
				app: this.state.selectedApp,
				doctype: this.state.selectedDoctype,
				record_key: recordKey,
			})
				.then((message) => {
					this.state.detailPayload = message;
					this.renderDetail();
				})
				.catch((error) => this.showError(this.$detail, error));
		}

		renderDetail() {
			const detail = this.state.detailPayload;
			const fieldDiffs = (detail && detail.field_diffs) || [];
			if (!detail) {
				this.$detail.html(this.renderEmpty(__("Select a record to inspect field diffs.")));
				return;
			}

			this.$detail.empty();
			const $detailHeader = $('<div class="fixture-analysis-detail-header"></div>');
			const $detailTitle = $("<div></div>")
				.append($('<div class="fixture-analysis-record-name"></div>').text(detail.record_key))
				.append(this.makeBadge(detail.status, detail.status));
			$detailHeader.append($detailTitle);
			if (detail.system_route) {
				$detailHeader.append(this.makeRecordLink(detail.system_route));
			}
			this.$detail.append($detailHeader);

			if (!fieldDiffs.length) {
				this.$detail.append(this.renderEmpty(__("The selected record has no field-level differences.")));
				return;
			}

			fieldDiffs.forEach((field) => {
				const $card = $('<div class="fixture-analysis-field-card"></div>');
				$card.append($('<div class="fixture-analysis-field-path"></div>').text(field.path));
				$card.append(this.makeBadge(field.change_type, field.change_type));

				const $values = $('<div class="fixture-analysis-values"></div>');
				$values.append(this.makeValueBlock(__("Fixture"), field.file_value));
				$values.append(this.makeValueBlock(__("Database"), field.db_value));
				$card.append($values);

				if (field.text_diff) {
					$card.append($("<hr>"));
					$card.append($("<div></div>").text(__("Text diff")));
					$card.append(this.renderTextDiff(field));
				}

				this.$detail.append($card);
			});
		}

		makeValueBlock(label, value) {
			const $wrapper = $('<div class="fixture-analysis-value"></div>');
			$wrapper.append($("<div></div>").text(label));
			if (this.shouldCollapseValue(value)) {
				const meta = this.describeValue(value);
				const $details = $("<details></details>");
				$details.append(
					$("<summary></summary>").text(__("Show full value") + ` (${meta})`)
				);
				$details.append($("<pre></pre>").text(this.stringify(value)));
				$wrapper.append($details);
			} else {
				$wrapper.append($("<pre></pre>").text(this.stringify(value)));
			}
			return $wrapper;
		}

		renderTextDiff(field) {
			if (!field.text_diff_hunks || !field.text_diff_hunks.length) {
				return $('<pre class="fixture-analysis-text-diff"></pre>').text(field.text_diff);
			}

			const $wrapper = $('<div class="fixture-analysis-text-diff-wrapper"></div>');
			field.text_diff_hunks.forEach((hunk) => {
				const $hunk = $('<div class="fixture-analysis-text-diff-hunk"></div>');
				(hunk.lines || []).forEach((line) => {
					const marker = line.kind === "added" ? "+" : line.kind === "removed" ? "-" : " ";
					const $line = $('<div class="fixture-analysis-text-diff-line"></div>').addClass(
						`is-${line.kind}`
					);
					$line.append(
						$('<div class="fixture-analysis-text-diff-lineno"></div>').text(
							line.old_lineno || ""
						)
					);
					$line.append(
						$('<div class="fixture-analysis-text-diff-lineno"></div>').text(
							line.new_lineno || ""
						)
					);
					$line.append($('<div class="fixture-analysis-text-diff-marker"></div>').text(marker));
					$line.append($('<div class="fixture-analysis-text-diff-code"></div>').text(line.text || ""));
					$hunk.append($line);
				});
				$wrapper.append($hunk);
			});
			return $wrapper;
		}

		makeCounts(counts) {
			const $counts = $('<div class="fixture-analysis-counts"></div>');
			["changed", "file_only", "db_only"].forEach((key) => {
				if (counts[key]) {
					$counts.append(this.makeBadge(`${key}:${counts[key]}`, key));
				}
			});
			if (!counts.changed && !counts.file_only && !counts.db_only) {
				$counts.append(this.makeBadge(`equal:${counts.equal || 0}`, "equal"));
			}
			return $counts;
		}

		makeBadge(label, status) {
			const $badge = $('<span class="fixture-analysis-badge"></span>').text(label);
			if (status) {
				$badge.addClass(`status-${status}`);
			}
			return $badge;
		}

		makeRecordLink(systemRoute) {
			const $link = $('<a class="fixture-analysis-record-link"></a>')
				.attr("href", "#")
				.text(__("Open in System"));
			$link.on("click", (event) => {
				event.preventDefault();
				frappe.set_route("Form", systemRoute.doctype, systemRoute.name);
			});
			return $link;
		}

		renderLoading(message) {
			return `<div class="fixture-analysis-muted">${message}</div>`;
		}

		renderEmpty(message) {
			return `<div class="fixture-analysis-muted">${message}</div>`;
		}

		showError($target, error) {
			const message = (error && error.message) || __("Unable to load fixture analysis data.");
			$target.html(`<div class="text-danger">${message}</div>`);
		}

		stringify(value) {
			if (value === undefined || value === null) {
				return "";
			}
			if (typeof value === "string") {
				return value;
			}
			return JSON.stringify(value, null, 2);
		}

		shouldCollapseValue(value) {
			if (typeof value !== "string") {
				return false;
			}
			return value.length > 400 || value.split("\n").length > 12;
		}

		describeValue(value) {
			if (typeof value !== "string") {
				return "";
			}
			const lineCount = value ? value.split("\n").length : 0;
			return `${lineCount} ${__("lines")}, ${value.length} ${__("chars")}`;
		}

		call(method, args) {
			return frappe.call({ method, args }).then((response) => response.message);
		}

		debounceLoadRecords() {
			clearTimeout(this.recordsDebounce);
			this.recordsDebounce = setTimeout(() => this.loadRecords(), 250);
		}
	}

	window.dinext_common.FixtureAnalysisPage = FixtureAnalysisPage;
})();
