from datetime import datetime

from backend.jira_requirements import JiraRequirement
from backend.models import RequirementLink
from backend.requirement_links import (
    COVERED,
    ORPHANED,
    STALE,
    SUSPECT,
    list_requirement_links,
    mark_reviewed,
    resolve_effective_state,
    sync_requirement_links,
)
from backend.test_inventory import InventoryEntry


def _db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.db import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _requirement(key="KAN-4", summary="Homepage loads", description_text="Loads.", acceptance_criteria=None):
    return JiraRequirement(
        key=key, summary=summary, description_text=description_text, acceptance_criteria=acceptance_criteria or []
    )


def _entry(file="homepage.spec.ts", title="should load", jira_keys=None):
    return InventoryEntry(
        file=file, title=title, full_title=title, project="chromium", status="passed", jira_keys=jira_keys or []
    )


def test_sync_creates_a_new_link_hashed_at_link_time():
    db = _db_session()
    requirement = _requirement()
    sync_requirement_links(db, [requirement], [_entry(jira_keys=["KAN-4"])])
    db.commit()

    links = db.query(RequirementLink).all()
    assert len(links) == 1
    assert links[0].jira_key == "KAN-4"
    assert links[0].state == COVERED
    assert links[0].content_snapshot["summary"] == "Homepage loads"


def test_sync_is_idempotent_and_does_not_touch_existing_links():
    db = _db_session()
    requirement = _requirement()
    entry = _entry(jira_keys=["KAN-4"])

    sync_requirement_links(db, [requirement], [entry])
    db.commit()
    link = db.query(RequirementLink).one()
    link.state = SUSPECT  # simulate drift having already flipped it
    db.commit()

    # A second sync call (e.g. a later dashboard load) must not recreate
    # or reset the link.
    sync_requirement_links(db, [requirement], [entry])
    db.commit()

    links = db.query(RequirementLink).all()
    assert len(links) == 1
    assert links[0].state == SUSPECT


def test_sync_skips_a_jira_key_with_no_matching_pulled_requirement():
    db = _db_session()
    sync_requirement_links(db, [], [_entry(jira_keys=["KAN-4"])])
    db.commit()

    assert db.query(RequirementLink).count() == 0


def test_resolve_effective_state_covered_by_default():
    link = RequirementLink(jira_key="KAN-4", test_file="a.spec.ts", test_title="t", state=COVERED, content_hash="h", content_snapshot={})
    assert resolve_effective_state(link, test_exists=True, requirement_exists=True) == COVERED


def test_resolve_effective_state_suspect_passes_through():
    link = RequirementLink(jira_key="KAN-4", test_file="a.spec.ts", test_title="t", state=SUSPECT, content_hash="h", content_snapshot={})
    assert resolve_effective_state(link, test_exists=True, requirement_exists=True) == SUSPECT


def test_resolve_effective_state_stale_when_test_missing():
    link = RequirementLink(jira_key="KAN-4", test_file="a.spec.ts", test_title="t", state=COVERED, content_hash="h", content_snapshot={})
    assert resolve_effective_state(link, test_exists=False, requirement_exists=True) == STALE


def test_resolve_effective_state_orphaned_when_requirement_missing():
    link = RequirementLink(jira_key="KAN-4", test_file="a.spec.ts", test_title="t", state=COVERED, content_hash="h", content_snapshot={})
    assert resolve_effective_state(link, test_exists=True, requirement_exists=False) == ORPHANED


def test_resolve_effective_state_orphaned_takes_priority_over_stale():
    link = RequirementLink(jira_key="KAN-4", test_file="a.spec.ts", test_title="t", state=COVERED, content_hash="h", content_snapshot={})
    assert resolve_effective_state(link, test_exists=False, requirement_exists=False) == ORPHANED


def test_list_requirement_links_scopes_by_project_key_prefix():
    db = _db_session()
    db.add(
        RequirementLink(
            jira_key="KAN-4", test_file="a.spec.ts", test_title="t", state=COVERED, content_hash="h", content_snapshot={}
        )
    )
    db.add(
        RequirementLink(
            jira_key="OTHER-1", test_file="b.spec.ts", test_title="t", state=COVERED, content_hash="h", content_snapshot={}
        )
    )
    db.commit()

    views = list_requirement_links(db, "KAN", [_requirement()], [_entry(jira_keys=["KAN-4"])])
    assert [v.jira_key for v in views] == ["KAN-4"]


def test_mark_reviewed_resets_state_and_hash():
    db = _db_session()
    old_requirement = _requirement(description_text="old text")
    sync_requirement_links(db, [old_requirement], [_entry(jira_keys=["KAN-4"])])
    db.commit()

    link = db.query(RequirementLink).one()
    link.state = SUSPECT
    link.change_summary = "the description changed"
    db.commit()

    new_requirement = _requirement(description_text="new text")
    reviewed_at = datetime(2026, 9, 18, 12, 0, 0)
    mark_reviewed(link, new_requirement, reviewed_at)
    db.commit()

    db.refresh(link)
    assert link.state == COVERED
    assert link.change_summary is None
    assert link.last_reviewed_at == reviewed_at
    assert link.content_snapshot["description_text"] == "new text"
