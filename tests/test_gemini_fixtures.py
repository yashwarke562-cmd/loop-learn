"""Unit and mock fixture tests for the Gemini agent pathways."""
import json
from unittest.mock import MagicMock

import pytest

from app.agents.gemini import GeminiClient, Transcription, build_llm
from app.config import Settings


class MockGenAIResponse:
    def __init__(self, text: str, parsed=None):
        self.text = text
        self.parsed = parsed


def test_build_llm_without_keys():
    settings = Settings()
    settings.gemini_api_key = ""
    settings.use_vertex = False
    assert build_llm(settings) is None


def test_gemini_transcription_parsing(monkeypatch):
    settings = Settings()
    settings.gemini_api_key = "fake-key"
    settings.use_vertex = False

    mock_client = MagicMock()
    # Mock structured response
    expected_lines = ["2x + 3 = 11", "2x = 8", "x = 4"]
    mock_client.models.generate_content.return_value = MockGenAIResponse(
        text=json.dumps({"lines": expected_lines}),
        parsed=Transcription(lines=expected_lines),
    )

    client = GeminiClient.__new__(GeminiClient)
    client.model = "gemini-2.5-flash"
    client._types = MagicMock()
    client.client = mock_client

    result = client.transcribe(b"fake-image-bytes", "image/png")
    assert result == expected_lines
    assert len(result) == 3


def test_gemini_transcription_truncates_long_lines(monkeypatch):
    settings = Settings()
    mock_client = MagicMock()
    long_line = "x" * 120
    too_many_lines = [f"x = {i}" for i in range(25)]
    too_many_lines[0] = long_line
    mock_client.models.generate_content.return_value = MockGenAIResponse(
        text=json.dumps({"lines": too_many_lines}),
        parsed=None,
    )

    client = GeminiClient.__new__(GeminiClient)
    client.model = "gemini-2.5-flash"
    client._types = MagicMock()
    client.client = mock_client

    result = client.transcribe(b"fake-image-bytes", "image/png")
    assert len(result) == 15
    assert len(result[0]) == 80


def test_gemini_explain_handling():
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MockGenAIResponse(
        text="Remember that adding 3 turns to subtracting 3 when moving sides.",
    )

    client = GeminiClient.__new__(GeminiClient)
    client.model = "gemini-2.5-flash"
    client._types = MagicMock()
    client.client = mock_client

    facts = {
        "question": "2x + 3 = 11",
        "line_number": 1,
        "student_line": "2x = 11 + 3",
        "previous_line": "2x + 3 = 11",
        "mistake": "Sign slip when moving a number",
    }
    explanation = client.explain(facts)
    assert explanation is not None
    assert "adding 3" in explanation
