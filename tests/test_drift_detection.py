from unittest.mock import patch

from backend.drift_detection import detect_drift_for_issue
from backend.jira_client import JiraClient
from backend.models import RequirementLink
from backend.requirement_links import COVERED, SUSPECT


def _db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.db import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _fake_response(status_code: int, json_body: dict):
    class _Response:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            return json_body

        def raise_for_status(self):
            if status_code >= 400:
                import requests

                raise requests.exceptions.HTTPError(response=self)

    return _Response()


def _add_link(db, jira_key="KAN-4", state=COVERED, content_hash="original-hash", content_snapshot=None):
    link = RequirementLink(
        jira_key=jira_key,
        test_file="homepage.spec.ts",
        test_title="should load",
        state=state,
        content_hash=content_hash,
        content_snapshot=content_snapshot or {"summary": "Homepage loads", "description_text": "Loads.", "acceptance_criteria": []},
    )
    db.add(link)
    db.commit()
    return link


def test_no_links_for_the_issue_is_a_noop():
    db = _db_session()
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    with patch("backend.jira_client.requests.get") as mock_get:
        flipped = detect_drift_for_issue(db, client, "KAN-4")
    assert flipped == 0
    mock_get.assert_not_called()


def test_unchanged_content_does_not_flip_state():
    db = _db_session()
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    # Matches _issue()'s shape exactly - a None Jira description extracts
    # to an empty description_text/acceptance_criteria, so the snapshot
    # must too, or this "unchanged" fixture wouldn't actually be unchanged.
    snapshot = {"summary": "Homepage loads", "description_text": "", "acceptance_criteria": []}
    from backend.jira_requirements import JiraRequirement
    from backend.requirement_hash import hash_requirement_content

    unchanged_hash = hash_requirement_content(JiraRequirement(key="KAN-4", **snapshot))
    link = _add_link(db, content_hash=unchanged_hash, content_snapshot=snapshot)

    issue_response = {"key": "KAN-4", "fields": {"summary": "Homepage loads", "description": None}}
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, issue_response)
        flipped = detect_drift_for_issue(db, client, "KAN-4")

    assert flipped == 0
    db.commit()
    db.refresh(link)
    assert link.state == COVERED


def test_changed_content_flips_link_to_suspect():
    db = _db_session()
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    link = _add_link(db)

    issue_response = {"key": "KAN-4", "fields": {"summary": "Homepage loads fast now", "description": None}}
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, issue_response)
        with patch("backend.drift_detection.summarize_change", return_value="The summary was reworded.") as mock_summarize:
            flipped = detect_drift_for_issue(db, client, "KAN-4")

    assert flipped == 1
    db.commit()
    db.refresh(link)
    assert link.state == SUSPECT
    assert link.change_summary == "The summary was reworded."
    mock_summarize.assert_called_once()


def test_already_suspect_links_are_left_alone():
    db = _db_session()
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    link = _add_link(db, state=SUSPECT)

    with patch("backend.jira_client.requests.get") as mock_get:
        flipped = detect_drift_for_issue(db, client, "KAN-4")

    assert flipped == 0
    mock_get.assert_not_called()


def test_deleted_issue_is_not_treated_as_drift():
    db = _db_session()
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    link = _add_link(db)

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(404, {})
        flipped = detect_drift_for_issue(db, client, "KAN-4")

    assert flipped == 0
    db.commit()
    db.refresh(link)
    assert link.state == COVERED


def test_multiple_links_sharing_a_prior_hash_call_summarize_change_once():
    """10 tests linked to the same requirement, all linked against the same
    prior snapshot, must cost one Claude call, not ten (issue: LLM dedup)."""
    db = _db_session()
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    link_a = _add_link(db, content_hash="original-hash")
    link_b = RequirementLink(
        jira_key="KAN-4",
        test_file="checkout.spec.ts",
        test_title="should checkout",
        state=COVERED,
        content_hash="original-hash",
        content_snapshot={"summary": "Homepage loads", "description_text": "Loads.", "acceptance_criteria": []},
    )
    db.add(link_b)
    db.commit()

    issue_response = {"key": "KAN-4", "fields": {"summary": "Homepage loads fast now", "description": None}}
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, issue_response)
        with patch("backend.drift_detection.summarize_change", return_value="The summary was reworded.") as mock_summarize:
            flipped = detect_drift_for_issue(db, client, "KAN-4")

    assert flipped == 2
    db.commit()
    db.refresh(link_a)
    db.refresh(link_b)
    assert link_a.state == SUSPECT
    assert link_b.state == SUSPECT
    assert link_a.change_summary == "The summary was reworded."
    assert link_b.change_summary == "The summary was reworded."
    mock_summarize.assert_called_once()


def test_summarize_change_failure_still_flips_state():
    """A broken/unconfigured LLM call must not block the safety-relevant
    Suspect flag from being set (issue #19 is enrichment, not a
    prerequisite for issue #17's core behavior)."""
    db = _db_session()
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    link = _add_link(db)

    issue_response = {"key": "KAN-4", "fields": {"summary": "Homepage loads fast now", "description": None}}
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, issue_response)
        with patch("backend.drift_detection.summarize_change", side_effect=RuntimeError("boom")):
            flipped = detect_drift_for_issue(db, client, "KAN-4")

    assert flipped == 1
    db.commit()
    db.refresh(link)
    assert link.state == SUSPECT
    assert link.change_summary is None
