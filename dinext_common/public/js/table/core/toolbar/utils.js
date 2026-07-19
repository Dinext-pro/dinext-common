export function resolveToolbarFlag(value, ctx) {
    if (typeof value === "function") {
        return !!value(ctx);
    }
    return !!value;
}

/** Resolve string / SVG / fn fields at render time. */
export function resolveToolbarValue(value, ctx, fallback = "") {
    if (typeof value === "function") {
        const resolved = value(ctx);
        return resolved == null ? fallback : resolved;
    }
    return value == null ? fallback : value;
}

export function normalizeToolbarItem(item, index) {
    if (!item || item.type === "separator") {
        return { type: "separator", id: item?.id || `sep-${index}` };
    }
    if (item.type === "checkbox") {
        return {
            type: "checkbox",
            id: item.id || `item-${index}`,
            label: item.label || "",
            title: item.title || item.label || "",
            align: item.align || null,
            disabled: item.disabled,
            hidden: item.hidden,
            checked: item.checked,
            indeterminate: item.indeterminate,
            onChange: item.onChange
        };
    }
    return {
        type: "button",
        id: item.id || `item-${index}`,
        label: item.label || "",
        title: item.title || item.label || "",
        icon: item.icon || null,
        iconSvg: item.iconSvg || null,
        align: item.align || null,
        disabled: item.disabled,
        hidden: item.hidden,
        onClick: item.onClick
    };
}

export function getPersistStorageKey(persistKey) {
    return persistKey ? `dinext-table:toolbar:${persistKey}` : null;
}
