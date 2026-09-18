"""Plain-language summary of what changed in a Jira requirement (issue #19).

Drift detection (issue #17) already knows *that* a linked requirement's
content changed (the hash mismatched); this turns that into something a
human reviewing a Suspect link can actually use to decide whether their
existing test still covers it - e.g. "acceptance criterion 3 was reworded
to require login before checkout" instead of a wall of raw before/after
text.

This is enrichment on the suspect-link mechanism, not a prerequisite for
it: summarize_change returns None (and drift detection still flips the
link to Suspect) if ANTHROPIC_API_KEY isn't configured or the call fails,
so environments without an LLM key configured still get the core
suspect-flagging behavior.
"""

from __future__ import annotations

import os

import anthropic

from backend.jira_requirements import JiraRequirement

_MODEL = "claude-opus-5"

_PROMPT_TEMPLATE = """A Jira requirement changed after Playwright tests were linked to it. \
Describe in one or two plain-language sentences what meaningfully changed, for a QA \
engineer deciding whether their existing tests still cover the requirement. Be specific \
about which part changed (the summary, the description, or a particular acceptance \
criterion) - don't just say "the description changed".

BEFORE:
Summary: {before_summary}
Description: {before_description}
Acceptance Criteria: {before_ac}

AFTER:
Summary: {after_summary}
Description: {after_description}
Acceptance Criteria: {after_ac}"""


def summarize_change(previous: dict, current: JiraRequirement) -> str | None:
    """Ask Claude to describe what changed between two requirement snapshots.

    `previous` is a RequirementLink.content_snapshot dict (see
    JiraRequirement.to_dict); `current` is the freshly-pulled requirement.
    Returns None if no API key is configured.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    client = anthropic.Anthropic()
    prompt = _PROMPT_TEMPLATE.format(
        before_summary=previous.get("summary", ""),
        before_description=previous.get("description_text", ""),
        before_ac=previous.get("acceptance_criteria", []),
        after_summary=current.summary,
        after_description=current.description_text,
        after_ac=current.acceptance_criteria,
    )
    response = client.messages.create(
        model=_MODEL,
        max_tokens=300,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
    )
    return next((block.text for block in response.content if block.type == "text"), None)
