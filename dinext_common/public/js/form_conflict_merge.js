// Copyright (c) 2026, Dinext
// MIT License. See license.txt

/*
 * FormConflictMerge
 * -----------------
 * Универсальная клиентская утилита для Frappe Form, которая уменьшает риск
 * потери данных при параллельных изменениях одного документа.
 *
 * Как использовать в Client Script конкретного DocType:
 *
 * frappe.require("/assets/dinext_common/js/form_conflict_merge.js", () => {
 *     frappe.ui.form.on("Issue", {
 *         onload(frm) {
 *             dinext_common.formConflictMerge.install(frm, {
 *                 // fields: [] means all supported non-child fields.
 *                 include_fields: ["custom_z_user_group"],
 *                 include_child_tables: ["custom_z_user_group"],
 *                 exclude_fields: ["some_field_to_ignore"],
 *                 conflict_policy: "local_wins",
 *                 apply_server_changes_on_realtime: true,
 *                 refresh_docinfo_on_server_apply: true,
 *                 poll_server_changes_interval_ms: 5000,
 *             });
 *         },
 *     });
 * });
 *
 * Алгоритм сравнивает три состояния:
 * - initial: снимок формы при открытии;
 * - server: актуальный документ из БД;
 * - local: текущие значения в форме пользователя.
 *
 * Поля, изменённые только на сервере, подтягиваются в форму. Поля, изменённые
 * только пользователем, остаются локальными. Если одно и то же поле изменено
 * и на сервере, и локально, применяется conflict_policy.
 *
 * Важно: утилита не заменяет permissions, validations и серверные hooks.
 * Child tables сравниваются и применяются целиком, без построчного merge.
 */

(function () {
	window.dinext_common = window.dinext_common || {};

	const DEFAULT_CONFIG = {
		// Если пусто, отслеживаются все поддерживаемые non-child поля формы.
		// Если указан список, он становится явным allowlist.
		fields: [],

		// Дополнительно включить поля поверх auto/allowlist.
		// Удобно для точечного включения child table или нестандартного поля.
		include_fields: [],

		// Исключить поля из итогового списка.
		exclude_fields: [],

		// Child tables по умолчанию выключены, так как они применяются целиком.
		// true = все child tables, array = только перечисленные child table поля.
		include_child_tables: false,

		// "dialog" | "local_wins" | "server_wins" | "block"
		conflict_policy: "dialog",

		show_realtime_alert: true,
		show_applied_alert: true,
		apply_server_changes_on_realtime: false,

		// Обновляет sidebar docinfo: Assigned To, attachments, timeline.
		refresh_docinfo_on_server_apply: false,

		// 0 = выключено. Полезно, если realtime/socket.io недоступен.
		poll_server_changes_interval_ms: 0,

		// Опциональный hook для DocType-specific реакции после server-only merge.
		on_server_apply: null,
	};

	const SYSTEM_FIELDS = [
		"name",
		"owner",
		"creation",
		"modified",
		"modified_by",
		"docstatus",
		"idx",
		"doctype",
		"parent",
		"parentfield",
		"parenttype",
		"_user_tags",
		"_comments",
		"_assign",
		"_liked_by",
		"__islocal",
		"__unsaved",
		"__last_sync_on",
		"__needs_refresh",
	];

	const registry = (window.__dinext_form_conflict_merge_registry =
		window.__dinext_form_conflict_merge_registry || {});

	function get_state(frm) {
		const key = `${frm.doctype}::${frm.docname}`;
		registry[key] = registry[key] || {};
		return registry[key];
	}

	function is_child_table(df) {
		return df && (df.fieldtype === "Table" || df.fieldtype === "Table MultiSelect");
	}

	function is_child_table_included(df, cfg) {
		if (!is_child_table(df)) return true;
		if (cfg.include_child_tables === true) return true;
		if (Array.isArray(cfg.include_child_tables)) return cfg.include_child_tables.includes(df.fieldname);
		return false;
	}

	function is_mergeable_field(df) {
		if (!df || !df.fieldname) return false;
		if (SYSTEM_FIELDS.includes(df.fieldname)) return false;
		if (["Section Break", "Column Break", "Tab Break"].includes(df.fieldtype)) return false;
		if (["HTML", "Button", "Fold"].includes(df.fieldtype)) return false;
		return true;
	}

	function is_supported_field(df, cfg) {
		return is_mergeable_field(df) && is_child_table_included(df, cfg);
	}

	function unique_fields(fields) {
		return Array.from(new Set((fields || []).filter(Boolean)));
	}

	function get_fields(frm, cfg) {
		const meta_fields = frm.meta.fields || [];
		const fields_by_name = {};
		meta_fields.forEach((df) => {
			if (df && df.fieldname) fields_by_name[df.fieldname] = df;
		});

		const base_fields =
			cfg.fields && cfg.fields.length
				? cfg.fields.filter((fieldname) => is_mergeable_field(fields_by_name[fieldname]))
				: meta_fields.filter((df) => is_supported_field(df, cfg)).map((df) => df.fieldname);

		const included_fields = (cfg.include_fields || []).filter((fieldname) =>
			is_mergeable_field(fields_by_name[fieldname])
		);
		const excluded_fields = new Set(cfg.exclude_fields || []);

		return unique_fields(base_fields.concat(included_fields)).filter((fieldname) => !excluded_fields.has(fieldname));
	}

	function normalize_child(row) {
		const out = {};
		Object.keys(row || {})
			.sort()
			.forEach((key) => {
				if (SYSTEM_FIELDS.includes(key)) return;
				out[key] = row[key];
			});
		return out;
	}

	function normalize_value(value) {
		if (value === undefined) return null;
		if (Array.isArray(value)) return value.map((row) => normalize_child(row));
		if (value && typeof value === "object") return JSON.parse(JSON.stringify(value));
		return value;
	}

	function snapshot(doc, fields) {
		const out = {};
		fields.forEach((fieldname) => {
			out[fieldname] = normalize_value(doc ? doc[fieldname] : null);
		});
		return out;
	}

	function equal(left, right) {
		return JSON.stringify(normalize_value(left)) === JSON.stringify(normalize_value(right));
	}

	function clone_raw_value(value) {
		if (value === undefined) return null;
		if (value && typeof value === "object") return JSON.parse(JSON.stringify(value));
		return value;
	}

	function is_child_table_field(frm, fieldname) {
		const field = frm.fields_dict && frm.fields_dict[fieldname];
		const df = field && field.df;
		return df && (df.fieldtype === "Table" || df.fieldtype === "Table MultiSelect");
	}

	function apply_child_table(frm, server_doc, fieldname) {
		const rows = Array.isArray(server_doc[fieldname]) ? server_doc[fieldname] : [];
		frappe.model.clear_table(frm.doc, fieldname);

		rows.forEach((row) => {
			const child = frm.add_child(fieldname);
			Object.keys(row || {}).forEach((key) => {
				if (SYSTEM_FIELDS.includes(key)) return;
				child[key] = clone_raw_value(row[key]);
			});
		});

		frm.refresh_field(fieldname);
	}

	function apply_field(frm, server_doc, fieldname) {
		if (is_child_table_field(frm, fieldname)) {
			apply_child_table(frm, server_doc, fieldname);
			return;
		}

		frm.doc[fieldname] = clone_raw_value(server_doc[fieldname]);
		const local_doc = locals[frm.doctype] && locals[frm.doctype][frm.docname];
		if (local_doc) local_doc[fieldname] = frm.doc[fieldname];
		frm.refresh_field(fieldname);
	}

	function apply_modified(frm, server_doc) {
		if (!server_doc || !server_doc.modified) return;
		frm.doc.modified = server_doc.modified;
		const local_doc = locals[frm.doctype] && locals[frm.doctype][frm.docname];
		if (local_doc) local_doc.modified = server_doc.modified;
	}

	function mark_clean(frm) {
		frm.doc.__unsaved = 0;
		const local_doc = locals[frm.doctype] && locals[frm.doctype][frm.docname];
		if (local_doc) local_doc.__unsaved = 0;

		if (frm.beforeUnloadListener) {
			removeEventListener("beforeunload", frm.beforeUnloadListener, { capture: true });
		}

		if (frm.toolbar) {
			frm.toolbar.set_indicator();
			frm.toolbar.show_title_as_dirty();
			frm.toolbar.set_primary_action();
		}
	}

	function refresh_docinfo(frm) {
		if (!frm.sidebar || !frm.sidebar.reload_docinfo) return;
		frm.sidebar.reload_docinfo();
	}

	function analyze(frm, server_doc, state) {
		const initial = state.initial_values || {};
		const local = snapshot(frm.doc, state.fields);
		const server = snapshot(server_doc, state.fields);
		const server_only = [];
		const local_only = [];
		const conflicts = [];

		state.fields.forEach((fieldname) => {
			const local_changed = !equal(local[fieldname], initial[fieldname]);
			const server_changed = !equal(server[fieldname], initial[fieldname]);

			if (!local_changed && server_changed) {
				server_only.push(fieldname);
				return;
			}

			if (local_changed && !server_changed) {
				local_only.push(fieldname);
				return;
			}

			if (local_changed && server_changed && !equal(local[fieldname], server[fieldname])) {
				conflicts.push(fieldname);
			}
		});

		return { server_only, local_only, conflicts };
	}

	function show_realtime_alert(data) {
		const changed_by = data && data.modified_by ? ` (${data.modified_by})` : "";
		frappe.show_alert({
			message: `Документ изменён на сервере${changed_by}. Выполняется сверка изменений.`,
			indicator: "orange",
		});
	}

	function show_applied_alert(analysis) {
		if (!analysis || !analysis.server_only.length) return;
		frappe.show_alert({
			message: `Подтянуты изменения с сервера: ${analysis.server_only.join(", ")}`,
			indicator: "blue",
		});
	}

	function apply_server_only_changes(frm, server_doc, state) {
		const was_dirty = frm.is_dirty();
		const analysis = analyze(frm, server_doc, state);

		analysis.server_only.forEach((fieldname) => {
			apply_field(frm, server_doc, fieldname);
			state.initial_values[fieldname] = normalize_value(server_doc[fieldname]);
		});

		apply_modified(frm, server_doc);
		state.server_changed = analysis.conflicts.length > 0;
		state.server_modified = server_doc.modified;
		state.server_modified_by = server_doc.modified_by;

		if (!state.server_changed) {
			state.initial_modified = server_doc.modified;
		}

		if (!was_dirty && !analysis.local_only.length && !analysis.conflicts.length) {
			mark_clean(frm);
		}

		if (analysis.server_only.length && state.cfg.refresh_docinfo_on_server_apply) {
			refresh_docinfo(frm);
		}

		if (analysis.server_only.length && typeof state.cfg.on_server_apply === "function") {
			state.cfg.on_server_apply(frm, analysis, server_doc);
		}

		return analysis;
	}

	function handle_doc_update(data) {
		const frm = cur_frm;
		if (!frm || !frm.doc || frm.is_new() || !data) return;
		if (data.doctype !== frm.doctype || data.name !== frm.docname) return;
		if (frappe.ui.form.is_saving) return;
		if (data.modified && data.modified === frm.doc.modified) return;

		const state = get_state(frm);
		if (!state.installed) return;

		state.server_changed = true;
		state.server_modified = data.modified;
		state.server_modified_by = data.modified_by;

		if (state.cfg.show_realtime_alert) {
			show_realtime_alert(data);
		}

		if (state.cfg.apply_server_changes_on_realtime) {
			fetch_server_doc(frm).then((server_doc) => {
				if (!server_doc || !server_doc.modified || server_doc.modified === state.initial_modified) return;
				const analysis = apply_server_only_changes(frm, server_doc, state);
				if (state.cfg.show_applied_alert) show_applied_alert(analysis);
			});
		}
	}

	function init_listener() {
		if (window.__dinext_form_conflict_merge_listener_ready) return;
		window.__dinext_form_conflict_merge_listener_ready = true;
		frappe.realtime.on("doc_update", handle_doc_update);
	}

	function check_server_changes(frm, state) {
		if (!frm || !frm.doc || frm.is_new() || !state.installed) return Promise.resolve();

		return fetch_server_doc(frm).then((server_doc) => {
			if (!server_doc || !server_doc.modified || server_doc.modified === state.initial_modified) return;
			const analysis = apply_server_only_changes(frm, server_doc, state);
			if (state.cfg.show_applied_alert) show_applied_alert(analysis);
			return analysis;
		});
	}

	function init_polling(frm, state) {
		const interval = Number(state.cfg.poll_server_changes_interval_ms || 0);
		if (!interval || interval < 1000) return;

		if (state.poll_timer) {
			clearInterval(state.poll_timer);
		}

		state.poll_timer = setInterval(() => {
			const current = cur_frm;
			if (!current || current.doctype !== frm.doctype || current.docname !== frm.docname) return;
			check_server_changes(current, state);
		}, interval);
	}

	function confirm_conflicts(conflicts, cfg) {
		if (!conflicts.length) return Promise.resolve("continue");
		if (cfg.conflict_policy === "local_wins") return Promise.resolve("local_wins");
		if (cfg.conflict_policy === "server_wins") return Promise.resolve("server_wins");
		if (cfg.conflict_policy === "block") return Promise.resolve("block");

		return new Promise((resolve) => {
			const message = [
				"Документ был изменён на сервере, и часть полей конфликтует с вашими правками.",
				"",
				`Конфликтующие поля: ${conflicts.join(", ")}`,
				"",
				"Выберите, как продолжить сохранение.",
			].join("<br>");

			const dialog = new frappe.ui.Dialog({
				title: "Конфликт изменений",
				fields: [{ fieldtype: "HTML", fieldname: "message", options: message }],
				primary_action_label: "Сохранить мои значения",
				primary_action() {
					dialog.hide();
					resolve("local_wins");
				},
				secondary_action_label: "Взять значения сервера",
				secondary_action() {
					dialog.hide();
					resolve("server_wins");
				},
			});

			dialog.$wrapper.find(".modal-footer").prepend(
				$(`<button class="btn btn-default btn-sm">${__("Отменить сохранение")}</button>`).on("click", () => {
					dialog.hide();
					resolve("block");
				})
			);

			dialog.show();
		});
	}

	function fetch_server_doc(frm) {
		return new Promise((resolve, reject) => {
			frappe.call({
				method: "frappe.client.get",
				type: "GET",
				args: {
					doctype: frm.doctype,
					name: frm.docname,
				},
				callback(r) {
					resolve(r.message);
				},
				error: reject,
			});
		});
	}

	function before_save(frm) {
		if (frm.is_new()) return Promise.resolve();

		const state = get_state(frm);
		if (!state.installed) return Promise.resolve();

		return fetch_server_doc(frm).then((server_doc) => {
			if (!server_doc || !server_doc.modified || server_doc.modified === state.initial_modified) return;

			const analysis = analyze(frm, server_doc, state);
			analysis.server_only.forEach((fieldname) => apply_field(frm, server_doc, fieldname));

			return confirm_conflicts(analysis.conflicts, state.cfg).then((decision) => {
				if (decision === "block") {
					frappe.validated = false;
					frappe.throw("Сохранение отменено: документ был изменён на сервере.");
				}

				if (decision === "server_wins") {
					analysis.conflicts.forEach((fieldname) => apply_field(frm, server_doc, fieldname));
				}

				apply_modified(frm, server_doc);
				state.server_changed = false;
			});
		});
	}

	function refresh_initial(frm) {
		const state = get_state(frm);
		if (!state.installed) return;
		state.initial_values = snapshot(frm.doc, state.fields);
		state.initial_modified = frm.doc.modified;
		state.server_changed = false;
		state.server_modified = null;
		state.server_modified_by = null;
		if (frm.dashboard) frm.dashboard.clear_headline();
	}

	function install(frm, opts) {
		opts = opts || {};
		if (!frm || !frm.doctype) frappe.throw("FormConflictMerge: вызовите из onload(frm)");

		const cfg = Object.assign({}, DEFAULT_CONFIG, opts);
		const state = get_state(frm);
		state.cfg = cfg;
		state.fields = get_fields(frm, cfg);
		state.installed = true;

		refresh_initial(frm);
		init_listener();
		init_polling(frm, state);

		if (window.__dinext_form_conflict_merge_doctype_hooks && window.__dinext_form_conflict_merge_doctype_hooks[frm.doctype]) {
			return;
		}

		window.__dinext_form_conflict_merge_doctype_hooks = window.__dinext_form_conflict_merge_doctype_hooks || {};
		window.__dinext_form_conflict_merge_doctype_hooks[frm.doctype] = true;

		frappe.ui.form.on(frm.doctype, {
			before_save,
			after_save: refresh_initial,
			refresh(frm) {
				const active = get_state(frm);
				if (!active.initial_values) refresh_initial(frm);
			},
		});
	}

	window.dinext_common.formConflictMerge = {
		install,
		check_server_changes,
		refresh_initial,
	};
})();
