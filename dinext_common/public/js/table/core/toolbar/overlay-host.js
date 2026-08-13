/**
 * Native Fullscreen only paints `fullscreenElement` subtree.
 * Overlays appended to `body` (Frappe datepicker, AG popup) are invisible there.
 */

export const OVERLAY_Z_INDEX = "10050";

/** Desk / AG overlays that normally portal to body. */
export const OVERLAY_SELECTOR = ".datepicker, .ag-popup";

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
	if (overlayHost === ownerDoc?.body && node.parentNode === overlayHost) {
		return false;
	}
	if (node.parentNode !== overlayHost) {
		const rect = typeof node.getBoundingClientRect === "function" ? node.getBoundingClientRect() : null;
		overlayHost.appendChild(node);
		if (anchor) {
			placeOverlayNearAnchor(node, anchor);
		} else if (rect && (rect.width || rect.height)) {
			applyFixedRect(node, rect);
		} else {
			node.style.zIndex = node.style.zIndex || OVERLAY_Z_INDEX;
		}
		return true;
	}
	if (anchor) {
		placeOverlayNearAnchor(node, anchor);
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
