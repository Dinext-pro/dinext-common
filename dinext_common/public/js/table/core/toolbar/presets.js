import { TOOLBAR_ICON_SVG } from "./icons.js";
import { normalizeToolbarItem } from "./utils.js";

function canUndoRedo(table) {
    return typeof table.isUndoRedoEnabled === "function" && table.isUndoRedoEnabled();
}

const TOOLBAR_PRESET_BUILDERS = {
    history(table) {
        if (!canUndoRedo(table)) {
            return [];
        }

        return [
            {
                id: "undo",
                title: "Undo",
                iconSvg: TOOLBAR_ICON_SVG.undo,
                onClick: ({ table: instance }) => {
                    instance.undoClipboard();
                }
            },
            {
                id: "redo",
                title: "Redo",
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
                title: "Expand all",
                iconSvg: TOOLBAR_ICON_SVG.expandAll,
                onClick: ({ table: instance }) => {
                    void instance.expandAll();
                }
            },
            {
                id: "collapse-all",
                title: "Collapse all",
                iconSvg: TOOLBAR_ICON_SVG.collapseAll,
                onClick: ({ table: instance }) => {
                    instance.collapseAll();
                }
            }
        ];
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
                title: "Copy",
                iconSvg: TOOLBAR_ICON_SVG.copy,
                onClick: ({ table: instance }) => {
                    void instance.copySelectionToClipboard();
                }
            },
            {
                id: "paste",
                title: "Paste",
                iconSvg: TOOLBAR_ICON_SVG.paste,
                onClick: ({ table: instance }) => {
                    void instance.pasteFromClipboard();
                }
            },
            {
                id: "clear",
                title: "Clear",
                iconSvg: TOOLBAR_ICON_SVG.clear,
                onClick: ({ table: instance }) => {
                    instance.clearSelectionCells();
                }
            },
            {
                id: "fill-down",
                title: "Fill down",
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
            title: "Fullscreen",
            iconSvg: TOOLBAR_ICON_SVG.fullscreen,
            hidden: ({ table: instance }) => instance.isFullscreen(),
            onClick: ({ table: instance }) => {
                void instance.enterFullscreen();
            }
        }, {
            id: "exit-fullscreen",
            align: "end",
            title: "Exit fullscreen",
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
    return items.map((item, index) => normalizeToolbarItem(item, index));
}

export function resolveToolbarItems(table, toolbarOptions = {}) {
    const presets = toolbarOptions.presets ?? ["history", "tree", "fullscreen"];
    const presetItems = resolveToolbarPresetItems(table, presets);
    const customItems = (toolbarOptions.items || []).map((item, index) => normalizeToolbarItem(item, index));

    const endItems = presetItems.filter(item => item.align === "end");
    const primaryItems = presetItems.filter(item => item.align !== "end");

    return [...primaryItems, ...customItems, ...endItems];
}
