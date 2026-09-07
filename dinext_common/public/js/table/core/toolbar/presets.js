import { TOOLBAR_ICON_SVG } from "./icons.js";
import { normalizeToolbarItem } from "./utils.js";

function canUndoRedo(table) {
    return typeof table.isUndoRedoEnabled === "function" && table.isUndoRedoEnabled();
}

function createMoveRowToolbarItems() {
    return [
        {
            id: "move-row-up",
            title: __("Move selected row up"),
            iconSvg: TOOLBAR_ICON_SVG.moveUp,
            disabled: ({ table: instance }) => (
                typeof instance.canNudgeCheckedRow !== "function"
                    || !instance.canNudgeCheckedRow(-1)
            ),
            onClick: ({ table: instance }) => {
                instance.nudgeCheckedRow(-1);
            }
        },
        {
            id: "move-row-down",
            title: __("Move selected row down"),
            iconSvg: TOOLBAR_ICON_SVG.moveDown,
            disabled: ({ table: instance }) => (
                typeof instance.canNudgeCheckedRow !== "function"
                    || !instance.canNudgeCheckedRow(1)
            ),
            onClick: ({ table: instance }) => {
                instance.nudgeCheckedRow(1);
            }
        }
    ];
}

const TOOLBAR_PRESET_BUILDERS = {
    history(table) {
        if (!canUndoRedo(table)) {
            return [];
        }

        return [
            {
                id: "undo",
                title: __("Undo"),
                iconSvg: TOOLBAR_ICON_SVG.undo,
                onClick: ({ table: instance }) => {
                    instance.undoClipboard();
                }
            },
            {
                id: "redo",
                title: __("Redo"),
                iconSvg: TOOLBAR_ICON_SVG.redo,
                onClick: ({ table: instance }) => {
                    instance.redoClipboard();
                }
            }
        ];
    },

    tree(table) {
        if (typeof table.hasNestedRows !== "function" || !table.hasNestedRows()) {
            return [];
        }

        return [
            {
                id: "expand-all",
                title: __("Expand all"),
                iconSvg: TOOLBAR_ICON_SVG.expandAll,
                onClick: ({ table: instance }) => {
                    void instance.expandAll();
                }
            },
            {
                id: "collapse-all",
                title: __("Collapse all"),
                iconSvg: TOOLBAR_ICON_SVG.collapseAll,
                onClick: ({ table: instance }) => {
                    instance.collapseAll();
                }
            }
        ];
    },

    /**
     * @deprecated Prefer auto-inject via `table.getFilterToolbarItems()` (always on when enabled).
     * Kept so explicit `presets: ["filter"]` does not break.
     */
    filter(table) {
        if (typeof table.getFilterToolbarItems === "function") {
            return table.getFilterToolbarItems();
        }
        return [];
    },

    /**
     * Opt-in: add / delete / duplicate / move checked rows.
     * Requires `rowCheck.enabled`.
     * Move arrows require `rowReorder.enabled` (same reorder contour as gutter DnD).
     */
    rows(table) {
        if (typeof table.isRowCheckEnabled !== "function" || !table.isRowCheckEnabled()) {
            return [];
        }

        const checkedCount = () => (
            typeof table.getCheckedRowIds === "function"
                ? table.getCheckedRowIds().length
                : 0
        );

        const items = [];

        if (typeof table.hasRowCheckAddHook === "function" && table.hasRowCheckAddHook()) {
            items.push({
                id: "add-row",
                title: __("Add row"),
                iconSvg: TOOLBAR_ICON_SVG.addRow,
                onClick: ({ table: instance }) => {
                    void instance.addRow();
                }
            });
        }

        items.push({
            id: "delete-rows",
            title: __("Delete selected rows"),
            iconSvg: TOOLBAR_ICON_SVG.deleteRows,
            disabled: () => checkedCount() === 0,
            onClick: ({ table: instance }) => {
                void instance.deleteCheckedRows();
            }
        });

        if (typeof table.hasRowCheckDuplicateHook === "function" && table.hasRowCheckDuplicateHook()) {
            items.push({
                id: "duplicate-rows",
                title: __("Duplicate selected rows"),
                iconSvg: TOOLBAR_ICON_SVG.duplicateRows,
                disabled: () => checkedCount() === 0,
                onClick: ({ table: instance }) => {
                    void instance.duplicateCheckedRows();
                }
            });
        }

        const moveOn = typeof table.isRowReorderToolbarMoveEnabled === "function"
            ? table.isRowReorderToolbarMoveEnabled()
            : (typeof table.isRowReorderEnabled === "function" && table.isRowReorderEnabled());
        if (moveOn) {
            items.push(...createMoveRowToolbarItems());
        }

        return items;
    },

    /** Opt-in: copy/paste/clear/fill-down (hidden from default toolbar). */
    clipboard(table) {
        const canClipboard = typeof table.isClipboardEnabled === "function"
            ? table.isClipboardEnabled()
            : false;

        if (!canClipboard) {
            return [];
        }

        return [
            {
                id: "copy",
                title: __("Copy"),
                iconSvg: TOOLBAR_ICON_SVG.copy,
                onClick: ({ table: instance }) => {
                    void instance.copySelectionToClipboard();
                }
            },
            {
                id: "paste",
                title: __("Paste"),
                iconSvg: TOOLBAR_ICON_SVG.paste,
                onClick: ({ table: instance }) => {
                    void instance.pasteFromClipboard();
                }
            },
            {
                id: "clear",
                title: __("Clear"),
                iconSvg: TOOLBAR_ICON_SVG.clear,
                onClick: ({ table: instance }) => {
                    instance.clearSelectionCells();
                }
            },
            {
                id: "fill-down",
                title: __("Fill down"),
                iconSvg: TOOLBAR_ICON_SVG.fillDown,
                onClick: ({ table: instance }) => {
                    instance.fillDownSelection();
                }
            }
        ];
    },

    fullscreen(table) {
        if (typeof table.isFullscreenEnabled !== "function" || !table.isFullscreenEnabled()) {
            return [];
        }

        return [{
            id: "fullscreen",
            align: "end",
            title: __("Fullscreen"),
            iconSvg: TOOLBAR_ICON_SVG.fullscreen,
            hidden: ({ table: instance }) => instance.isFullscreen(),
            onClick: ({ table: instance }) => {
                void instance.enterFullscreen();
            }
        }, {
            id: "exit-fullscreen",
            align: "end",
            title: __("Exit fullscreen"),
            iconSvg: TOOLBAR_ICON_SVG.exitFullscreen,
            hidden: ({ table: instance }) => !instance.isFullscreen(),
            onClick: ({ table: instance }) => {
                void instance.exitFullscreen();
            }
        }];
    }
};

export function resolveToolbarPresetItems(table, presetNames = []) {
    const items = [];
    for (const name of presetNames) {
        const builder = TOOLBAR_PRESET_BUILDERS[name];
        if (builder) {
            items.push(...builder(table));
        }
    }
    return items;
}

export function resolveToolbarItems(table, toolbarOptions = {}) {
    const presets = toolbarOptions.presets ?? ["history", "tree", "fullscreen"];
    const filterItems = (
        typeof table.getFilterToolbarItems === "function"
            ? table.getFilterToolbarItems()
            : []
    );
    const rowCheckItems = (
        typeof table.getRowCheckToolbarItems === "function"
            ? table.getRowCheckToolbarItems()
            : []
    );
    const presetItems = resolveToolbarPresetItems(table, presets);
    const domainItems = (toolbarOptions.items || []).map(item => ({
        ...item,
        zone: item.zone || "custom"
    }));

    const endItems = presetItems.filter(item => item.align === "end");
    const primaryItems = presetItems.filter(item => item.align !== "end")
        // Avoid duplicate when consumer still lists presets: ["filter"].
        .filter(item => item.id !== "filter");

    // Zones: primary (presets+filter+rowCheck) | custom (domain) | end (fullscreen).
    const combined = [
        ...primaryItems,
        ...filterItems,
        ...rowCheckItems,
        ...domainItems,
        ...endItems
    ];
    return combined.map((item, index) => normalizeToolbarItem(item, index));
}
