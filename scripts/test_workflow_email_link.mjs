import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const script = fs.readFileSync(
	new URL("../dinext_common/public/js/workflow_email_link.js", import.meta.url),
	"utf8",
);
const destination = "/api/method/dinext_common.workflow_approval.signed_links.open_email_action";

for (const hash of ["#signed%2Bsynthetic", ""]) {
	const events = [];
	const input = { value: undefined };
	const form = {
		elements: {
			namedItem(name) {
				assert.equal(name, "preview_token");
				return input;
			},
		},
		submit() {
			events.push(["post", input.value]);
		},
	};
	vm.runInNewContext(script, {
		document: {
			getElementById(id) {
				assert.equal(id, "workflow-email-preview");
				return form;
			},
		},
		window: {
			location: { hash, pathname: destination },
			history: { replaceState: (...args) => events.push(["replace", ...args]) },
		},
	});
	assert.deepEqual(events, hash
		? [["replace", null, "", destination], ["post", hash.slice(1)]]
		: [["post", ""]]);
}

console.log("Link fragments are cleared before form submission and sent without decoding.");
