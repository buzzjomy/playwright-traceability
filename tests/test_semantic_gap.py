import json
from unittest.mock import MagicMock, patch

import pytest

from backend.semantic_gap import GapAnalysisError, LLMNotConfiguredError, analyze_gap
from backend.test_inventory import InventoryEntry


def _entry(title="should show search results", assertions=None) -> InventoryEntry:
    return InventoryEntry(
        file="search.spec.ts",
        title=title,
        full_title=title,
        project="chromium",
        status="passed",
        assertions=assertions or [],
        jira_keys=["KAN-5"],
    )


def _text_response(payload) -> MagicMock:
    text_block = MagicMock(type="text", text=json.dumps(payload))
    return MagicMock(content=[text_block])


def test_no_acceptance_criteria_returns_empty_list():
    assert analyze_gap([], [_entry()]) == []


def test_no_linked_tests_marks_every_criterion_uncovered_without_calling_claude():
    with patch("backend.semantic_gap.anthropic.Anthropic") as mock_anthropic:
        results = analyze_gap(["Results are shown", "Results can be filtered"], [])

    mock_anthropic.assert_not_called()
    assert len(results) == 2
    assert all(not r.covered for r in results)
    assert all("No tests are linked" in r.reasoning for r in results)


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMNotConfiguredError):
        analyze_gap(["Results are shown"], [_entry()])


def test_successful_analysis_zips_criteria_with_claude_results(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _text_response(
        [
            {"covered": True, "reasoning": "The title mentions search results."},
            {"covered": False, "reasoning": "Nothing mentions filtering."},
        ]
    )

    with patch("backend.semantic_gap.anthropic.Anthropic", return_value=mock_client):
        results = analyze_gap(
            ["Results are shown", "Results can be filtered"],
            [_entry(assertions=["expect(page.getByTestId('results')).toBeVisible()"])],
        )

    assert results[0].criterion == "Results are shown"
    assert results[0].covered is True
    assert results[1].criterion == "Results can be filtered"
    assert results[1].covered is False

    _, kwargs = mock_client.messages.create.call_args
    assert kwargs["model"] == "claude-opus-5"
    prompt = kwargs["messages"][0]["content"]
    assert "Results are shown" in prompt
    assert "expect(page.getByTestId('results')).toBeVisible()" in prompt


def test_malformed_json_raises_gap_analysis_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(content=[MagicMock(type="text", text="not json")])

    with patch("backend.semantic_gap.anthropic.Anthropic", return_value=mock_client):
        with pytest.raises(GapAnalysisError):
            analyze_gap(["Results are shown"], [_entry()])


def test_wrong_result_count_raises_gap_analysis_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _text_response([{"covered": True, "reasoning": "only one"}])

    with patch("backend.semantic_gap.anthropic.Anthropic", return_value=mock_client):
        with pytest.raises(GapAnalysisError):
            analyze_gap(["Results are shown", "Results can be filtered"], [_entry()])


def test_missing_fields_in_response_raises_gap_analysis_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _text_response([{"covered": True}])

    with patch("backend.semantic_gap.anthropic.Anthropic", return_value=mock_client):
        with pytest.raises(GapAnalysisError):
            analyze_gap(["Results are shown"], [_entry()])
