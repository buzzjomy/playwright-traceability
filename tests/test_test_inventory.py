from backend.models import SourceTestRecord, TestRun, TestRunRecord
from backend.test_inventory import build_inventory


def _add_source(db, file, title, full_title=None, tags=None, jira_keys=None, source_type="static"):
    db.add(
        SourceTestRecord(
            source_type=source_type,
            title=title,
            full_title=full_title or title,
            file=file,
            line=1,
            column=1,
            tags=tags or [],
            jira_keys=jira_keys or [],
        )
    )


def _add_run(db, file, title, project, status, full_title=None, tags=None, jira_keys=None, is_flaky=False):
    run = TestRun()
    db.add(run)
    db.flush()
    db.add(
        TestRunRecord(
            run_id=run.id,
            spec_id="spec-1",
            title=title,
            full_title=full_title or title,
            file=file,
            line=1,
            column=1,
            project=project,
            tags=tags or [],
            jira_keys=jira_keys or [],
            status=status,
            duration_ms=100,
            retry_count=0,
            is_flaky=is_flaky,
            error_message=None,
        )
    )
    return run


def _db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.db import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_matched_test_shows_both_in_source_and_has_run():
    db = _db_session()
    _add_source(db, "auth.spec.ts", "should login", tags=["@smoke"])
    _add_run(db, "auth.spec.ts", "should login", "chromium", "passed")
    db.commit()

    entries = build_inventory(db)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.in_source is True
    assert entry.has_run is True
    assert entry.project == "chromium"
    assert entry.status == "passed"


def test_source_only_test_has_never_run():
    db = _db_session()
    _add_source(db, "auth.spec.ts", "should lock account", jira_keys=["PROJ-109"])
    db.commit()

    entries = build_inventory(db)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.in_source is True
    assert entry.has_run is False
    assert entry.project is None
    assert entry.status is None
    assert entry.jira_keys == ["PROJ-109"]


def test_run_only_test_has_no_matching_source():
    # e.g. a dynamically-generated title a static scan can never resolve,
    # or a test since deleted from source.
    db = _db_session()
    _add_run(db, "auth.spec.ts", "should see the admin dashboard", "chromium", "passed")
    db.commit()

    entries = build_inventory(db)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.in_source is False
    assert entry.has_run is True


def test_multi_project_test_produces_one_row_per_project():
    db = _db_session()
    _add_source(db, "auth.spec.ts", "should expire session")
    _add_run(db, "auth.spec.ts", "should expire session", "chromium", "failed")
    _add_run(db, "auth.spec.ts", "should expire session", "firefox", "passed")
    db.commit()

    entries = build_inventory(db)

    assert len(entries) == 2
    by_project = {e.project: e.status for e in entries}
    assert by_project == {"chromium": "failed", "firefox": "passed"}


def test_jira_keys_and_tags_are_unioned_across_source_and_run():
    db = _db_session()
    _add_source(db, "auth.spec.ts", "should login", tags=["@smoke"], jira_keys=["PROJ-101"])
    _add_run(db, "auth.spec.ts", "should login", "chromium", "passed", tags=["@regression"], jira_keys=["PROJ-999"])
    db.commit()

    entries = build_inventory(db)

    assert len(entries) == 1
    assert entries[0].tags == ["@regression", "@smoke"]
    assert entries[0].jira_keys == ["PROJ-101", "PROJ-999"]


def test_only_the_latest_run_per_project_is_used():
    db = _db_session()
    _add_source(db, "auth.spec.ts", "should login")
    _add_run(db, "auth.spec.ts", "should login", "chromium", "failed")
    _add_run(db, "auth.spec.ts", "should login", "chromium", "passed")  # a later push
    db.commit()

    entries = build_inventory(db)

    assert len(entries) == 1
    assert entries[0].status == "passed"


def test_history_accumulates_across_pushes_oldest_first():
    db = _db_session()
    _add_run(db, "auth.spec.ts", "should login", "chromium", "failed")
    _add_run(db, "auth.spec.ts", "should login", "chromium", "passed")
    _add_run(db, "auth.spec.ts", "should login", "chromium", "passed")
    db.commit()

    entries = build_inventory(db)

    assert len(entries) == 1
    history = entries[0].history
    assert [point.status for point in history] == ["failed", "passed", "passed"]
    # oldest first, so run_ids are strictly increasing
    assert [point.run_id for point in history] == sorted(point.run_id for point in history)


def test_history_is_per_project_not_shared_across_projects():
    db = _db_session()
    _add_run(db, "auth.spec.ts", "should login", "chromium", "failed")
    _add_run(db, "auth.spec.ts", "should login", "firefox", "passed")
    db.commit()

    entries = build_inventory(db)

    by_project = {e.project: e for e in entries}
    assert [p.status for p in by_project["chromium"].history] == ["failed"]
    assert [p.status for p in by_project["firefox"].history] == ["passed"]


def test_history_is_capped_at_max_history_points():
    from backend.test_inventory import MAX_HISTORY_POINTS

    db = _db_session()
    for i in range(MAX_HISTORY_POINTS + 5):
        status = "passed" if i % 2 == 0 else "failed"
        _add_run(db, "auth.spec.ts", "should login", "chromium", status)
    db.commit()

    entries = build_inventory(db)

    assert len(entries) == 1
    assert len(entries[0].history) == MAX_HISTORY_POINTS
    # the most recent push (index MAX_HISTORY_POINTS + 4, even -> "passed")
    # must be the last (most recent) entry kept, not trimmed off
    assert entries[0].history[-1].status == "passed"


def test_source_only_test_has_no_history():
    db = _db_session()
    _add_source(db, "auth.spec.ts", "should lock account")
    db.commit()

    entries = build_inventory(db)

    assert len(entries) == 1
    assert entries[0].history == []


def test_is_flaky_reflects_the_latest_run():
    db = _db_session()
    _add_run(db, "auth.spec.ts", "should login", "chromium", "passed", is_flaky=True)
    db.commit()

    entries = build_inventory(db)

    assert len(entries) == 1
    assert entries[0].is_flaky is True


def test_is_flaky_uses_only_the_latest_run_not_history():
    db = _db_session()
    _add_run(db, "auth.spec.ts", "should login", "chromium", "passed", is_flaky=True)
    _add_run(db, "auth.spec.ts", "should login", "chromium", "passed", is_flaky=False)  # a later, clean push
    db.commit()

    entries = build_inventory(db)

    assert len(entries) == 1
    assert entries[0].is_flaky is False


def test_source_only_test_is_not_flaky():
    db = _db_session()
    _add_source(db, "auth.spec.ts", "should lock account")
    db.commit()

    entries = build_inventory(db)

    assert len(entries) == 1
    assert entries[0].is_flaky is False


def test_build_inventory_against_real_sample_fixtures():
    # Real parser output (via a real Node subprocess for static_parser),
    # not synthetic data - exercises the actual reconciliation gaps that
    # exist in these fixtures: "should lock account after 5 failed
    # attempts" and "should support the old single-page checkout flow"
    # are source-only (never run in samples/sample-report.json).
    from pathlib import Path

    from parser.report_parser import parse_report_file
    from parser.static_parser import parse_spec_directory

    samples_dir = Path(__file__).parent.parent / "samples"
    db = _db_session()

    for record in parse_report_file(samples_dir / "sample-report.json"):
        run = TestRun()
        db.add(run)
        db.flush()
        db.add(TestRunRecord(run_id=run.id, **record.to_dict()))

    # samples/sample-report.json's "file" is rootDir-relative (e.g.
    # "auth.spec.ts"), while parse_spec_directory(samples_dir /
    # "sample-specs") reports the path as given - here an absolute path,
    # since samples_dir is built from __file__. Stripping that prefix
    # simulates a real pipeline invoking both parsers with a consistent
    # working-directory convention - without it, reconciliation would
    # (correctly) treat every test as unmatched, which is the documented
    # (file, title) sharp edge, not a bug.
    for record in parse_spec_directory(samples_dir / "sample-specs"):
        record.file = str(Path(record.file).relative_to(samples_dir / "sample-specs"))
        db.add(SourceTestRecord(source_type="static", **record.to_dict()))

    db.commit()

    entries = build_inventory(db)
    by_title = {e.title: e for e in entries}

    assert by_title["should lock account after 5 failed attempts"].has_run is False
    assert by_title["should lock account after 5 failed attempts"].in_source is True
    assert by_title["should login with valid credentials"].has_run is True
    assert by_title["should login with valid credentials"].in_source is True


def test_reconciliation_requires_matching_file_paths():
    # The documented sharp edge, made explicit: report_parser and
    # static_parser were invoked with different path conventions here
    # (as they would be if a real CI pipeline weren't consistent about
    # it), so the same real test shows up as two unmatched rows instead
    # of one reconciled row.
    db = _db_session()
    _add_source(db, "samples/sample-specs/auth.spec.ts", "should login with valid credentials")
    _add_run(db, "auth.spec.ts", "should login with valid credentials", "chromium", "passed")
    db.commit()

    entries = build_inventory(db)

    assert len(entries) == 2
    assert {e.has_run for e in entries} == {True, False}
