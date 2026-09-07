/**
 * Native Fullscreen only paints `fullscreenElement` subtree.
 * Overlays appended to `body` (datepicker, AG popup, Frappe Dialog) are invisible there.
 */

export const OVERLAY_Z_INDEX = "10050";
export const MODAL_Z_INDEX = "10050";
export const BACKDROP_Z_INDEX = "10040";

/** Desk / AG overlays that normally portal to body. */
export const OVERLAY_SELECTOR = [
	".datepicker",
	".ag-popup",
	".awesomplete > ul",
	"#freeze",
	"#dialog-container",
	".modal",
	".modal-backdrop",
	".frappe-toast-area",
].join(", ");

function nodeHasClass(node, name) {
	return String(node?.className || "")
		.split(/\s+/)
		.includes(name);
}

/** Bootstrap / Frappe viewport overlays — already position:fixed; do not snapshot rect. */
export function isViewportOverlay(node) {
	if (!node) {
		return false;
	}
	if (node.id === "freeze" || node.id === "dialog-container") {
		return true;
	}
	return (
		nodeHasClass(node, "modal") ||
		nodeHasClass(node, "modal-backdrop") ||
		nodeHasClass(node, "frappe-toast-area")
	);
}

function resolveAdoptNode(node, host) {
	if (nodeHasClass(node, "modal")) {
		return node;
	}
	const modalRoot = node.closest?.(".modal");
	if (modalRoot && modalRoot !== host) {
		return modalRoot;
	}
	return node;
}

function applyViewportOverlayZ(node) {
	if (!node?.style) {
		return;
	}
	if (nodeHasClass(node, "modal") || node.id === "dialog-container") {
		node.style.zIndex = MODAL_Z_INDEX;
	} else if (nodeHasClass(node, "modal-backdrop")) {
		node.style.zIndex = BACKDROP_Z_INDEX;
	} else if (node.id === "freeze") {
		node.style.zIndex = node.style.zIndex || "10060";
	}
}

export function getDocumentFullscreenElement(doc = typeof document !== "undefined" ? document : null) {
	if (!doc) {
		return null;
	}
	return (
		doc.fullscreenElement ||
		doc.webkitFullscreenElement ||
		doc.mozFullScreenElement ||
		doc.msFullscreenElement ||
		null
	);
}

/** Fullscreen host when active, else `document.body`. */
export function getOverlayHost(doc = typeof document !== "undefined" ? document : null) {
	if (!doc) {
		return null;
	}
	return getDocumentFullscreenElement(doc) || doc.body || null;
}

function applyFixedRect(node, rect) {
	if (!node?.style || !rect) {
		return;
	}
	node.style.position = "fixed";
	node.style.left = `${rect.left}px`;
	node.style.top = `${rect.top}px`;
	node.style.right = "auto";
	if (!node.style.zIndex) {
		node.style.zIndex = OVERLAY_Z_INDEX;
	}
}

/** Place overlay under an anchor (viewport / fullscreen containing block). */
export function placeOverlayNearAnchor(node, anchor) {
	if (!node?.style || !anchor?.getBoundingClientRect) {
		return;
	}
	const rect = anchor.getBoundingClientRect();
	node.style.position = "fixed";
	node.style.left = `${rect.left}px`;
	node.style.top = `${rect.bottom}px`;
	node.style.right = "auto";
	node.style.zIndex = OVERLAY_Z_INDEX;
}

/**
 * Move overlay into the current overlay host. No-op when host is body and
 * the node is already there. Preserves on-screen position after reparent.
 *
 * @returns {boolean} true if moved or repositioned
 */
export function adoptOverlay(node, { anchor, host, doc } = {}) {
	const ownerDoc = doc || node?.ownerDocument || (typeof document !== "undefined" ? document : null);
	const overlayHost = host || getOverlayHost(ownerDoc);
	if (!node || !overlayHost) {
		return false;
	}
	const target = resolveAdoptNode(node, overlayHost);
	if (overlayHost === ownerDoc?.body && target.parentNode === overlayHost) {
		return false;
	}
	if (target.parentNode !== overlayHost) {
		const rect =
			typeof target.getBoundingClientRect === "function"
				? target.getBoundingClientRect()
				: null;
		overlayHost.appendChild(target);
		if (isViewportOverlay(target)) {
			applyViewportOverlayZ(target);
			return true;
		}
		if (anchor) {
			placeOverlayNearAnchor(target, anchor);
		} else if (rect && (rect.width || rect.height)) {
			applyFixedRect(target, rect);
		} else {
			target.style.zIndex = target.style.zIndex || OVERLAY_Z_INDEX;
		}
		return true;
	}
	if (anchor) {
		placeOverlayNearAnchor(target, anchor);
		return true;
	}
	return false;
}

export function adoptMatchingOverlays(root, { host, doc } = {}) {
	const ownerDoc = doc || root?.ownerDocument || (typeof document !== "undefined" ? document : null);
	const scope = root || ownerDoc?.body;
	if (!scope?.querySelectorAll) {
		return 0;
	}
	let n = 0;
	for (const node of scope.querySelectorAll(OVERLAY_SELECTOR)) {
		if (adoptOverlay(node, { host, doc: ownerDoc })) {
			n += 1;
		}
	}
	return n;
}
