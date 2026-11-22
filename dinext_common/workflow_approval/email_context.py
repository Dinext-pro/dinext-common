"""Immutable entry context for messages about the round's incoming transition."""

import frappe


def entry_context_for_round(round_id: str, winner: dict) -> dict:
	votes = frappe.get_all(
		"Workflow Task",
		filters={"approval_round_id": round_id, "transition_uuid": winner["transition_uuid"], "status": "Completed"},
		fields=["approver", "vote_comment", "completed_at"], order_by="completed_at asc, name asc",
	)
	return {
		"round_id": round_id, "transition_uuid": winner["transition_uuid"],
		"action": winner["action"], "next_state": winner["next_state"],
		"comments": [{"actor": row.approver, "text": row.vote_comment, "at": str(row.completed_at or "")}
			for row in votes if row.vote_comment],
		"actor": votes[-1].approver if votes else "",
		"at": str(votes[-1].completed_at or "") if votes else "",
	}
