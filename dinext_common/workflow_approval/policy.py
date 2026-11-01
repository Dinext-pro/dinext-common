"""Pure policy and identity rules for parallel Workflow approvals."""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Literal, TypedDict, cast

ParallelPolicy = Literal["Any", "All", "Minimum"]
PARALLEL_POLICIES: tuple[ParallelPolicy, ...] = ("Any", "All", "Minimum")
MAX_COMMENT_CODEPOINTS = 4000
MAX_TASK_NAME_LENGTH = 140


class ZeroEligibleApproversError(ValueError):
	"""Raised when a transition snapshot would have no eligible approvers."""


class ReachedTransition(TypedDict):
	transition_uuid: str
	idx: int
	votes: int
	threshold: int


def normalize_policy(value: object) -> ParallelPolicy:
	"""Return a supported policy, treating an empty value as Any."""
	if value is None or str(value).strip() == "":
		return "Any"
	normalized = str(value).strip()
	if normalized not in PARALLEL_POLICIES:
		raise ValueError(f"Unsupported parallel approval policy: {normalized}")
	return cast(ParallelPolicy, normalized)


def required_approvals(
	policy: object,
	minimum_approvals: object,
	cohort_size: int,
) -> int:
	"""Calculate the immutable threshold for a transition snapshot."""
	if cohort_size <= 0:
		raise ZeroEligibleApproversError("A transition requires at least one eligible approver")

	normalized = normalize_policy(policy)
	if normalized == "Any":
		return 1
	if normalized == "All":
		return cohort_size

	try:
		minimum = int(minimum_approvals)
	except (TypeError, ValueError):
		raise ValueError("Minimum approvals must be a positive integer")
	if minimum <= 0:
		raise ValueError("Minimum approvals must be a positive integer")
	return min(minimum, cohort_size)


def is_threshold_reachable(*, threshold: int, votes: int, remaining: int) -> bool:
	"""Return whether current and remaining votes can still reach threshold."""
	return votes + remaining >= threshold


def select_reached_transition(
	transitions: Iterable[ReachedTransition],
) -> ReachedTransition | None:
	"""Choose a deterministic reached transition by row index and UUID."""
	reached = [row for row in transitions if row["votes"] >= row["threshold"]]
	if not reached:
		return None
	return min(reached, key=lambda row: (int(row["idx"]), row["transition_uuid"]))


def policy_from_legacy_flag(value: object) -> ParallelPolicy:
	"""Map the legacy all-users checkbox onto the new policy values."""
	if str(value).strip().lower() in {"1", "true", "yes"}:
		return "All"
	return "Any"


def transition_semantic_hash(transition: Mapping[str, object]) -> str:
	"""Hash only transition behavior that must match for vote reuse."""
	policy = normalize_policy(transition.get("policy"))
	payload = {
		"action": transition.get("action") or "",
		"allow_self_approval": int(bool(transition.get("allow_self_approval"))),
		"allowed": transition.get("allowed") or "",
		"condition": transition.get("condition") or "",
		"minimum_approvals": (
			int(transition["minimum_approvals"])
			if policy == "Minimum" and transition.get("minimum_approvals") not in (None, "")
			else None
		),
		"next_state": transition.get("next_state") or "",
		"policy": policy,
		"state": transition.get("state") or "",
	}
	serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
	return hashlib.sha256(serialized.encode()).hexdigest()


def _transition_identity(row: Mapping[str, object]) -> tuple[str, str, str]:
	return (
		str(row.get("transition_uuid") or ""),
		str(row.get("transition_semantic_hash") or ""),
		str(row.get("action") or ""),
	)


def classify_round_configuration(
	snapshot: Iterable[Mapping[str, object]],
	current: Iterable[Mapping[str, object]],
	completed_votes: Iterable[Mapping[str, object]],
) -> dict[str, list[dict[str, object]]]:
	"""Split a round snapshot against the live transitions of the same state.

	A stable row has the same UUID and semantic hash. An empty snapshot UUID
	matches one current row with the same hash and does not become a conflict.
	A different non-empty UUID is not the same transition. Completed votes on
	a removed or changed row are void; the same row with no votes is dropped.
	"""
	snapshot_rows = [dict(row) for row in snapshot]
	current_rows = [dict(row) for row in current]
	votes_by_uuid: dict[str, list[str]] = {}
	for vote in completed_votes:
		uuid = str(vote.get("transition_uuid") or "")
		approver = str(vote.get("approver") or "")
		if approver and approver not in votes_by_uuid.setdefault(uuid, []):
			votes_by_uuid[uuid].append(approver)
	for approvers in votes_by_uuid.values():
		approvers.sort()

	used: set[int] = set()
	keep: list[dict[str, object]] = []
	void: list[dict[str, object]] = []
	dropped: list[dict[str, object]] = []
	stable_votes: list[dict[str, object]] = []

	def describe(uuid: str, action: str, change: str) -> dict[str, object]:
		return {
			"transition_uuid": uuid,
			"action": action,
			"change": change,
			"approvers": list(votes_by_uuid.get(uuid, [])),
		}

	for snapshot_row in snapshot_rows:
		uuid, snap_hash, action = _transition_identity(snapshot_row)
		match: int | None = None
		if uuid:
			for index, current_row in enumerate(current_rows):
				current_uuid, current_hash, _current_action = _transition_identity(current_row)
				if index not in used and current_uuid == uuid and current_hash == snap_hash:
					match = index
					break
		else:
			candidates = [
				index
				for index, current_row in enumerate(current_rows)
				if index not in used and _transition_identity(current_row)[1] == snap_hash
			]
			if len(candidates) == 1:
				match = candidates[0]
		if match is not None:
			used.add(match)
			keep.append(snapshot_row)
			approvers = votes_by_uuid.get(uuid, [])
			if approvers:
				stable_votes.append(
					{
						"transition_uuid": uuid,
						"action": action,
						"approvers": approvers,
					}
				)
			continue
		current_match = next(
			(
				current_row
				for current_row in current_rows
				if _transition_identity(current_row)[0] == uuid and uuid
			),
			None,
		)
		change = "semantic" if current_match is not None else "removed"
		described = describe(uuid, action, change)
		if described["approvers"]:
			void.append(described)
		else:
			dropped.append(described)

	add: list[dict[str, object]] = []
	added: list[dict[str, object]] = []
	for index, current_row in enumerate(current_rows):
		if index in used:
			continue
		uuid, _current_hash, action = _transition_identity(current_row)
		add.append(dict(current_row))
		added.append({"transition_uuid": uuid, "action": action})
	return {
		"keep": keep,
		"add": add,
		"void": void,
		"dropped": dropped,
		"stable": stable_votes,
		"added": added,
	}


def configuration_change_metadata(
	classification: Mapping[str, list[dict[str, object]]],
) -> dict[str, object]:
	"""JSON stored on a round conflicted by a workflow configuration change."""
	return {
		"reason": "configuration_changed",
		"stable": list(classification.get("stable") or []),
		"void": list(classification.get("void") or []),
		"added": list(classification.get("added") or []),
	}


def normalize_comment(
	value: object,
	*,
	required: bool = False,
	max_codepoints: int = MAX_COMMENT_CODEPOINTS,
) -> str:
	"""Normalize a comment to bounded, control-free plain text."""
	text = html.unescape(str(value or ""))
	text = re.sub(r"<[^>]*>", "", text)
	text = "".join(character for character in text if unicodedata.category(character) not in {"Cc", "Cf"})
	text = text.strip()
	if required and not text:
		raise ValueError("A comment is required for this workflow action")
	if len(text) > max_codepoints:
		raise ValueError(f"Workflow comments cannot exceed {max_codepoints} characters")
	return text


def make_task_name(round_id: str, approver: str) -> str:
	"""Build the bounded deterministic Workflow Task identifier."""
	identity = f"{round_id}\0{approver}".encode()
	name = f"WT-{hashlib.sha256(identity).hexdigest()}"
	return name[:MAX_TASK_NAME_LENGTH]


def missing_task_names(
	round_id: str,
	approvers: Iterable[str],
	existing_names: Iterable[str],
) -> set[str]:
	"""Return only deterministic task names missing from a round manifest."""
	expected = {make_task_name(round_id, approver) for approver in approvers}
	return expected.difference(existing_names)
