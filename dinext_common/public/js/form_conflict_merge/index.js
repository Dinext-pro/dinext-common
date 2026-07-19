const FormConflictMergeConfig = {
	CHILD_CELL_CONFLICT_CLASS,
	CHILD_CELL_SERVER_CLASS,
	CHILD_TABLE_REMOVED_CLASS,
	CHILD_ROW_ADDED_CLASS,
	CONFLICT_HIGHLIGHT_CLASS,
	DEFAULT_CONFIG,
	HIGHLIGHT_STYLE_ID,
	SERVER_HIGHLIGHT_CLASS,
	SYSTEM_FIELDS,
};

window.dinext_common.formConflictMerge = {
	install: FormMergeEngine.install,
	apply_local_seed: FormStartup.apply_local_seed,
	check_server_changes: FormMergeEngine.check_server_changes,
	clear_local_seed: FormMergeState.clear_local_seed,
	mark_local_seed: FormMergeState.mark_local_seed,
	refresh_initial: FormMergeState.refresh_initial,
	set_startup_value: FormStartup.set_startup_value,
	dump_debug_state: FormMergeDebug.dump_debug_state,
	__internals: {
		Config: FormConflictMergeConfig,
		DocInfoWatcher: FormDocInfoWatcher,
		FieldApplier: FormValueApplier,
		MergeEngine: FormMergeEngine,
		StateStore: FormMergeState,
		StartupValues: FormStartup,
		UiFeedback: FormMergeUi,
		ValueNormalizer: FormDiff,
		Debug: FormMergeDebug,
	},
};
