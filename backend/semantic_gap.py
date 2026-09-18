"""Semantic gap detection: does a requirement's linked test evidence
actually cover each of its acceptance criteria (Milestone 5, issues
#21/#22)?

This is the differentiator CLAUDE.md describes: every earlier milestone
answers "does at least one test exist for this requirement" (coverage,
issue #13) or "has the requirement's content changed since linking"
(suspect links, issue #17). Neither checks whether the linked test's
actual content still substantively matches what the requirement asks
for. This does, per acceptance-criterion (issue #22), using each linked
test's title and statically-extracted assertions (issue #21) as the
evidence Claude judges against - there is no non-LLM fallback for this
one, unlike issue #19's enrichment-only change summary: a wrong "gap
analysis unavailable" is more honest than a silently-guessed answer.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import anthropic

from backend.test_inventory import InventoryEntry

_MODEL = "claude-opus-5"

_PROMPT_TEMPLATE = """A QA engineer wants to know which specific acceptance criteria of a Jira \
requirement are actually verified by its linked automated tests. Judge only from the test \
titles and their assertion source text below - you have no access to the tests' full source \
or runtime behavior.

Acceptance Criteria:
{criteria_block}

Linked Tests:
{tests_block}

Respond with ONLY a JSON array, no other text, with exactly {count} entries - one per \
acceptance criterion above, in the same order - in this exact form:
[{{"covered": true, "reasoning": "one short sentence"}}, ...]"""


class GapAnalysisError(Exception):
    """Raised when gap analysis can't produce a trustworthy result."""


class LLMNotConfiguredError(GapAnalysisError):
    """Raised when ANTHROPIC_API_KEY isn't set - there's no fallback for this feature."""


@dataclass
class CriterionGapResult:
    """Whether one acceptance criterion is covered by the linked tests' evidence."""

    criterion: str
    covered: bool
    reasoning: str

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict representation of this result."""
        return {"criterion": self.criterion, "covered": self.covered, "reasoning": self.reasoning}


def _format_tests_block(linked_tests: list[InventoryEntry]) -> str:
    """Render each linked test's title and assertions as a readable block."""
    blocks = []
    for entry in linked_tests:
        lines = [f"- {entry.full_title}"]
        for assertion in entry.assertions:
            lines.append(f"    {assertion}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def analyze_gap(acceptance_criteria: list[str], linked_tests: list[InventoryEntry]) -> list[CriterionGapResult]:
    """Judge each acceptance criterion as covered or not by the linked tests' evidence.

    Returns [] if there are no acceptance criteria to judge. If there are
    criteria but no linked tests, every criterion is trivially uncovered -
    no LLM call needed, since there's no evidence at all to evaluate.
    """
    if not acceptance_criteria:
        return []

    if not linked_tests:
        return [
            CriterionGapResult(criterion=c, covered=False, reasoning="No tests are linked to this requirement.")
            for c in acceptance_criteria
        ]

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise LLMNotConfiguredError("ANTHROPIC_API_KEY is not configured on this server")

    criteria_block = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(acceptance_criteria))
    prompt = _PROMPT_TEMPLATE.format(
        criteria_block=criteria_block,
        tests_block=_format_tests_block(linked_tests),
        count=len(acceptance_criteria),
    )

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        raise GapAnalysisError(f"Claude API call failed: {exc}") from exc

    text = next((block.text for block in response.content if block.type == "text"), "")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GapAnalysisError(f"Claude did not return valid JSON: {exc}") from exc

    if not isinstance(parsed, list) or len(parsed) != len(acceptance_criteria):
        raise GapAnalysisError(
            f"Expected {len(acceptance_criteria)} results from Claude, got {len(parsed) if isinstance(parsed, list) else 'non-list'}"
        )

    try:
        return [
            CriterionGapResult(criterion=criterion, covered=bool(item["covered"]), reasoning=str(item["reasoning"]))
            for criterion, item in zip(acceptance_criteria, parsed)
        ]
    except (KeyError, TypeError) as exc:
        raise GapAnalysisError(f"Claude's response was missing expected fields: {exc}") from exc
