const DEFAULT_CONFIG = {
	// Если пусто, отслеживаются все поддерживаемые non-child поля формы.
	// Если указан список, он становится явным allowlist.
	fields: [],

	// Дополнительно включить поля поверх auto/allowlist.
	// Удобно для точечного включения child table или нестандартного поля.
	include_fields: [],

	// Исключить поля из итогового списка.
	exclude_fields: [],

	// Child tables по умолчанию включены (применяются целиком, без построчного merge).
	// exclude_child_tables — opt-out для отдельных таблиц.
	exclude_child_tables: [],

	// Legacy opt-in: false = ни одной child table; array = только перечисленные.
	// true и отсутствие ключа эквивалентны «все, кроме exclude_child_tables».
	include_child_tables: undefined,

	// "dialog" | "local_wins" | "server_wins" | "block"
	conflict_policy: "dialog",

	show_realtime_alert: true,
	show_applied_alert: true,
	highlight_server_changes: true,
	apply_server_changes_on_realtime: false,

	// Обновляет sidebar docinfo: Assigned To, attachments, timeline.
	refresh_docinfo_on_server_apply: false,

	// Универсальное отслеживание частей frm.get_docinfo(), например:
	// ["assignments", "attachments", "shared"].
	watch_docinfo_keys: [],
	show_docinfo_alert: true,
	docinfo_key_labels: {
		assignments: "назначения",
		attachments: "вложения",
		shared: "доступы",
		communications: "сообщения",
		comments: "комментарии",
	},
	docinfo_self_change_suppress_ms: 10000,

	// 0 = выключено. Полезно, если realtime/socket.io недоступен.
	poll_server_changes_interval_ms: 0,

	// Подробные логи в console с префиксом [FCM] (console.info / console.warn).
	// Также: localStorage.setItem("dinext_fcm_debug", "1") или window.__dinext_fcm_debug = true.
	debug_log: false,

	// Первичная стабилизация формы после onload/refresh: другие Client Script,
	// Quill и sidebar могут ещё менять клиентское состояние.
	startup_warmup_ms: 3000,
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

const HIGHLIGHT_STYLE_ID = "dinext-form-conflict-merge-highlight-style";
const SERVER_HIGHLIGHT_CLASS = "dinext-fcm-highlight-server";
const CONFLICT_HIGHLIGHT_CLASS = "dinext-fcm-highlight-conflict";
