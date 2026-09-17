from dataclasses import dataclass, field
from pathlib import Path

from parser.mapping_parser import apply_mapping, load_mapping_file

SAMPLE_MAPPING = Path(__file__).parent.parent / "samples" / "sample-mapping.json"


@dataclass
class _FakeRecord:
    """Minimal stand-in for TestRecord/StaticTestRecord/FeatureTestRecord."""

    file: str
    title: str
    jira_keys: list[str] = field(default_factory=list)


def test_load_mapping_file_parses_entries():
    mapping = load_mapping_file(SAMPLE_MAPPING)
    assert mapping[("samples/sample-specs/auth.spec.ts", "should reject invalid password")] == ["PROJ-150"]


def test_apply_mapping_adds_jira_keys_to_matching_record():
    records = [_FakeRecord(file="auth.spec.ts", title="should reject invalid password")]
    mapping = {("auth.spec.ts", "should reject invalid password"): ["PROJ-150"]}

    apply_mapping(records, mapping)

    assert records[0].jira_keys == ["PROJ-150"]


def test_apply_mapping_extends_rather_than_replaces_existing_jira_keys():
    records = [_FakeRecord(file="auth.spec.ts", title="should login", jira_keys=["PROJ-101"])]
    mapping = {("auth.spec.ts", "should login"): ["PROJ-999"]}

    apply_mapping(records, mapping)

    assert records[0].jira_keys == ["PROJ-101", "PROJ-999"]


def test_apply_mapping_does_not_duplicate_an_already_present_key():
    records = [_FakeRecord(file="auth.spec.ts", title="should login", jira_keys=["PROJ-101"])]
    mapping = {("auth.spec.ts", "should login"): ["PROJ-101"]}

    apply_mapping(records, mapping)

    assert records[0].jira_keys == ["PROJ-101"]


def test_apply_mapping_leaves_unmatched_records_untouched():
    records = [_FakeRecord(file="auth.spec.ts", title="should logout")]
    mapping = {("auth.spec.ts", "should login"): ["PROJ-101"]}

    apply_mapping(records, mapping)

    assert records[0].jira_keys == []


def test_apply_mapping_returns_the_set_of_matched_keys():
    records = [_FakeRecord(file="auth.spec.ts", title="should login")]
    mapping = {
        ("auth.spec.ts", "should login"): ["PROJ-101"],
        ("auth.spec.ts", "a stale entry"): ["PROJ-000"],
    }

    matched = apply_mapping(records, mapping)

    assert matched == {("auth.spec.ts", "should login")}
    unmatched = set(mapping) - matched
    assert unmatched == {("auth.spec.ts", "a stale entry")}
