from backend.jira_requirements import JiraRequirement
from backend.requirement_hash import hash_requirement_content


def _requirement(**overrides) -> JiraRequirement:
    defaults = dict(key="KAN-4", summary="Homepage loads", description_text="Loads the homepage.", acceptance_criteria=["Search box is visible"])
    defaults.update(overrides)
    return JiraRequirement(**defaults)


def test_same_content_hashes_the_same():
    assert hash_requirement_content(_requirement()) == hash_requirement_content(_requirement())


def test_different_summary_changes_the_hash():
    assert hash_requirement_content(_requirement()) != hash_requirement_content(_requirement(summary="Homepage loads fast"))


def test_different_description_changes_the_hash():
    assert hash_requirement_content(_requirement()) != hash_requirement_content(
        _requirement(description_text="Loads the homepage in under 2s.")
    )


def test_different_acceptance_criteria_changes_the_hash():
    assert hash_requirement_content(_requirement()) != hash_requirement_content(
        _requirement(acceptance_criteria=["Search box is visible", "Logo is visible"])
    )


def test_key_is_not_part_of_the_hash():
    """The hash covers content only - the same content under a different
    key (e.g. after a Jira issue is moved) should still hash the same."""
    assert hash_requirement_content(_requirement(key="KAN-4")) == hash_requirement_content(_requirement(key="KAN-99"))
