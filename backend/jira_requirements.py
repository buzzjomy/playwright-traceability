"""Pull requirement/story data from Jira (Milestone 2, issue #7).

Builds on JiraClient.search_issues to fetch a project's Story/Task issues
and extract (key, summary, description, acceptance criteria). There's no
dedicated field for acceptance criteria on a standard Jira Cloud site
(confirmed against a real site: pwtrace.atlassian.net's issues have no
such custom field) - teams write them as an "Acceptance Criteria" heading
followed by a bullet list inside the description, same convention used by
this project's own demo/google-search Jira stories, so that's what's
parsed out here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.jira_client import JiraClient

_AC_HEADING_PATTERN = re.compile(r"acceptance criteria", re.IGNORECASE)

DEFAULT_ISSUE_TYPES = ["Story", "Task"]


@dataclass
class JiraRequirement:
    """One pulled Jira requirement/story."""

    key: str
    summary: str
    description_text: str
    acceptance_criteria: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict representation of this requirement."""
        return {
            "key": self.key,
            "summary": self.summary,
            "description_text": self.description_text,
            "acceptance_criteria": self.acceptance_criteria,
        }


def _adf_node_text(node: dict) -> str:
    """Recursively concatenate the plain text of one Atlassian Document Format node."""
    if node.get("type") == "text":
        return node.get("text", "")
    return "".join(_adf_node_text(child) for child in node.get("content", []))


def extract_plain_text(adf: dict | None) -> str:
    """Render an ADF node tree as readable plain text.

    Paragraphs and headings become lines; list items become "- " lines.
    Good enough for a readable description_text field - not a full ADF
    renderer (tables, panels, etc. are flattened to their inner text).
    """
    if not adf:
        return ""

    lines: list[str] = []

    def walk(node: dict) -> None:
        node_type = node.get("type")
        if node_type == "text":
            return
        if node_type in ("paragraph", "heading"):
            text = _adf_node_text(node)
            if text:
                lines.append(text)
        elif node_type == "listItem":
            text = _adf_node_text(node)
            if text:
                lines.append(f"- {text}")
        else:
            for child in node.get("content", []):
                walk(child)

    for node in adf.get("content", []):
        walk(node)

    return "\n".join(lines)


def extract_acceptance_criteria(adf: dict | None) -> list[str]:
    """Pull out the bullet/numbered list items following an "Acceptance
    Criteria" heading in an ADF description. Returns [] if no such
    heading is found, or if nothing follows it before the next heading.
    """
    if not adf:
        return []

    top_level = adf.get("content", [])
    for i, node in enumerate(top_level):
        if node.get("type") != "heading" or not _AC_HEADING_PATTERN.search(_adf_node_text(node)):
            continue

        for following in top_level[i + 1 :]:
            if following.get("type") in ("bulletList", "orderedList"):
                return [text for item in following.get("content", []) if (text := _adf_node_text(item).strip())]
            if following.get("type") == "heading":
                break  # hit the next heading with no list in between
        return []

    return []


def _build_requirement(issue: dict) -> JiraRequirement:
    """Build a JiraRequirement from one raw Jira issue payload (search or single-issue fetch)."""
    fields = issue["fields"]
    description = fields.get("description")
    return JiraRequirement(
        key=issue["key"],
        summary=fields.get("summary", ""),
        description_text=extract_plain_text(description),
        acceptance_criteria=extract_acceptance_criteria(description),
    )


def pull_requirements(
    client: JiraClient, project_key: str, issue_types: list[str] | None = None
) -> list[JiraRequirement]:
    """Pull every issue of the given type(s) in a Jira project as JiraRequirements."""
    issue_types = issue_types if issue_types is not None else DEFAULT_ISSUE_TYPES

    jql = f'project = "{project_key}"'
    if issue_types:
        types_clause = ", ".join(f'"{t}"' for t in issue_types)
        jql += f" AND issuetype in ({types_clause})"

    raw_issues = client.search_issues(jql, fields=["summary", "description"])
    return [_build_requirement(issue) for issue in raw_issues]


def pull_requirement(client: JiraClient, key: str) -> JiraRequirement | None:
    """Pull a single requirement by key, e.g. to re-check content for the
    suspect-link mechanism (issues #17/#20). Returns None if the key
    doesn't resolve (deleted issue, wrong key, or an issue this account
    can no longer see) - callers treat that as the "orphaned" case rather
    than an error.
    """
    issue = client.get_issue(key, fields=["summary", "description"])
    if issue is None:
        return None
    return _build_requirement(issue)
