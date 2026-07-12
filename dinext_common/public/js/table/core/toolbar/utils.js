export function resolveToolbarFlag(value, ctx) {
    if (typeof value === "function") {
        return !!value(ctx);
    }
    return !!value;
}

export function normalizeToolbarItem(item, index) {
    if (!item || item.type === "separator") {
        return { type: "separator", id: item?.id || `sep-${index}` };
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
