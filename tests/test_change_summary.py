from unittest.mock import MagicMock, patch

from backend.change_summary import summarize_change
from backend.jira_requirements import JiraRequirement


def test_returns_none_without_an_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = summarize_change({"summary": "old"}, JiraRequirement(key="KAN-4", summary="new", description_text="", acceptance_criteria=[]))
    assert result is None


def test_calls_claude_and_returns_its_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    text_block = MagicMock(type="text", text="The acceptance criteria were tightened.")
    mock_response = MagicMock(content=[text_block])
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("backend.change_summary.anthropic.Anthropic", return_value=mock_client) as mock_anthropic:
        result = summarize_change(
            {"summary": "old summary", "description_text": "old desc", "acceptance_criteria": ["a"]},
            JiraRequirement(key="KAN-4", summary="new summary", description_text="new desc", acceptance_criteria=["a", "b"]),
        )

    assert result == "The acceptance criteria were tightened."
    mock_anthropic.assert_called_once()
    _, kwargs = mock_client.messages.create.call_args
    assert kwargs["model"] == "claude-opus-5"
    assert "new summary" in kwargs["messages"][0]["content"]
    assert "old summary" in kwargs["messages"][0]["content"]


def test_anthropic_model_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5")

    text_block = MagicMock(type="text", text="Something changed.")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(content=[text_block])

    with patch("backend.change_summary.anthropic.Anthropic", return_value=mock_client):
        summarize_change(
            {"summary": "old", "description_text": "", "acceptance_criteria": []},
            JiraRequirement(key="KAN-4", summary="new", description_text="", acceptance_criteria=[]),
        )

    _, kwargs = mock_client.messages.create.call_args
    assert kwargs["model"] == "claude-sonnet-5"
