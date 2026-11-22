(() => {
	const form = document.getElementById("workflow-email-preview");
	const ticket = window.location.hash.slice(1);
	if (!form) {
		return;
	}
	if (ticket) {
		window.history.replaceState(null, "", window.location.pathname);
	}
	form.elements.namedItem("preview_token").value = ticket;
	form.submit();
})();
