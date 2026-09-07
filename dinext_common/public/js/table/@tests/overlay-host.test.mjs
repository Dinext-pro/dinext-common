import test from "node:test";
import assert from "node:assert/strict";

import {
	adoptMatchingOverlays,
	adoptOverlay,
	getDocumentFullscreenElement,
	getOverlayHost,
	placeOverlayNearAnchor
} from "../core/toolbar/overlay-host.js";

function makeDoc({ fullscreen = null } = {}) {
	const body = makeEl("body");
	const doc = {
		body,
		fullscreenElement: fullscreen,
		webkitFullscreenElement: null,
		mozFullScreenElement: null,
		msFullscreenElement: null,
		createElement(tag) {
			return makeEl(tag);
		}
	};
	body.ownerDocument = doc;
	if (fullscreen) {
		fullscreen.ownerDocument = doc;
		body.appendChild(fullscreen);
	}
	return doc;
}

function makeEl(tag) {
	const el = {
		tagName: String(tag).toUpperCase(),
		className: "",
		parentNode: null,
		children: [],
		style: {},
		ownerDocument: null,
		appendChild(child) {
			if (child.parentNode) {
				child.parentNode.removeChild(child);
			}
			child.parentNode = this;
			this.children.push(child);
			return child;
		},
		removeChild(child) {
			this.children = this.children.filter((c) => c !== child);
			child.parentNode = null;
			return child;
		},
		querySelectorAll(selector) {
			const cls = selector.replace(/^\./, "").split(",")[0].trim();
			const out = [];
			const walk = (node) => {
				for (const c of node.children || []) {
					if (String(c.className).split(/\s+/).includes(cls) || c.className === cls) {
						out.push(c);
					}
					walk(c);
				}
			};
			walk(this);
			return out;
		},
		getBoundingClientRect() {
			return { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 };
		}
	};
	return el;
}

test("getOverlayHost falls back to body", () => {
	const doc = makeDoc();
	assert.equal(getDocumentFullscreenElement(doc), null);
	assert.equal(getOverlayHost(doc), doc.body);
});

test("getOverlayHost uses fullscreenElement", () => {
	const shell = makeEl("div");
	const doc = makeDoc({ fullscreen: shell });
	assert.equal(getOverlayHost(doc), shell);
});

test("adoptOverlay no-op when already on body and not fullscreen", () => {
	const doc = makeDoc();
	const picker = makeEl("div");
	picker.className = "datepicker";
	doc.body.appendChild(picker);
	assert.equal(adoptOverlay(picker, { doc }), false);
	assert.equal(picker.parentNode, doc.body);
});

test("adoptOverlay moves body datepicker into fullscreen host", () => {
	const shell = makeEl("div");
	const doc = makeDoc({ fullscreen: shell });
	const picker = makeEl("div");
	picker.className = "datepicker";
	picker.getBoundingClientRect = () => ({ left: 10, top: 20, right: 110, bottom: 80, width: 100, height: 60 });
	doc.body.appendChild(picker);

	assert.equal(adoptOverlay(picker, { doc, host: shell }), true);
	assert.equal(picker.parentNode, shell);
	assert.equal(picker.style.position, "fixed");
	assert.equal(picker.style.left, "10px");
	assert.equal(picker.style.top, "20px");
	assert.equal(picker.style.zIndex, "10050");
});

test("placeOverlayNearAnchor sits below the cell", () => {
	const picker = makeEl("div");
	const anchor = makeEl("input");
	anchor.getBoundingClientRect = () => ({ left: 40, top: 10, bottom: 34, right: 120, width: 80, height: 24 });
	placeOverlayNearAnchor(picker, anchor);
	assert.equal(picker.style.position, "fixed");
	assert.equal(picker.style.left, "40px");
	assert.equal(picker.style.top, "34px");
});

test("adoptOverlay moves modal into fullscreen host without rewriting position", () => {
	const shell = makeEl("div");
	const doc = makeDoc({ fullscreen: shell });
	const modal = makeEl("div");
	modal.className = "modal";
	modal.getBoundingClientRect = () => ({
		left: 100,
		top: 80,
		right: 500,
		bottom: 400,
		width: 400,
		height: 320
	});
	doc.body.appendChild(modal);

	assert.equal(adoptOverlay(modal, { doc, host: shell }), true);
	assert.equal(modal.parentNode, shell);
	assert.equal(modal.style.position, undefined);
	assert.equal(modal.style.left, undefined);
	assert.equal(modal.style.zIndex, "10050");
});

test("adoptMatchingOverlays moves datepicker under host", () => {
	const shell = makeEl("div");
	const doc = makeDoc({ fullscreen: shell });
	const picker = makeEl("div");
	picker.className = "datepicker";
	doc.body.appendChild(picker);
	assert.equal(adoptMatchingOverlays(doc.body, { host: shell, doc }), 1);
	assert.equal(picker.parentNode, shell);
});
