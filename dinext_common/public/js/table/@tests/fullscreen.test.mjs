import test from "node:test";
import assert from "node:assert/strict";

import {
	FullscreenMixin,
	isElementHidden,
	isHostOnVisibleDeskPage
} from "../core/toolbar/fullscreen.js";

function makePage({ hidden = false, display = "", connected = true } = {}) {
	const page = {
		className: "page-container",
		hidden,
		isConnected: connected,
		style: { display, visibility: "" },
		closest(sel) {
			return sel === ".page-container" ? this : null;
		}
	};
	return page;
}

function makeHost(page, { connected = true } = {}) {
	return {
		isConnected: connected,
		closest(sel) {
			return sel === ".page-container" ? page : null;
		}
	};
}

test("isElementHidden reads jQuery hide and hidden attr", () => {
	assert.equal(isElementHidden(null), true);
	assert.equal(isElementHidden({ hidden: true, style: {} }), true);
	assert.equal(isElementHidden({ hidden: false, style: { display: "none" } }), true);
	assert.equal(isElementHidden({ hidden: false, style: { visibility: "hidden" } }), true);
	assert.equal(isElementHidden({ hidden: false, style: { display: "" } }), false);
});

test("isHostOnVisibleDeskPage false when page-container hidden", () => {
	const page = makePage({ display: "none" });
	assert.equal(isHostOnVisibleDeskPage(makeHost(page)), false);
});

test("isHostOnVisibleDeskPage true when desk page visible", () => {
	const page = makePage();
	assert.equal(isHostOnVisibleDeskPage(makeHost(page)), true);
});

test("isHostOnVisibleDeskPage false when host disconnected", () => {
	assert.equal(isHostOnVisibleDeskPage(makeHost(makePage(), { connected: false })), false);
	assert.equal(isHostOnVisibleDeskPage(null), false);
});

test("isHostOnVisibleDeskPage true without page-container (do not assume leave)", () => {
	const host = { isConnected: true, closest() { return null; } };
	assert.equal(isHostOnVisibleDeskPage(host), true);
});

test("exitFullscreenIfHostLeftPage exits only after page hide", () => {
	class Base {}
	const Table = FullscreenMixin(Base);
	const table = new Table();
	const page = makePage();
	const host = makeHost(page);
	let exits = 0;

	table._fullscreenActive = true;
	table.getFullscreenElement = () => host;
	table.exitFullscreen = async () => {
		exits += 1;
		return true;
	};

	assert.equal(table.exitFullscreenIfHostLeftPage(), false);
	assert.equal(exits, 0);

	page.style.display = "none";
	assert.equal(table.exitFullscreenIfHostLeftPage(), true);
	assert.equal(exits, 1);

	table._fullscreenActive = false;
	assert.equal(table.exitFullscreenIfHostLeftPage(), false);
	assert.equal(exits, 1);
});
