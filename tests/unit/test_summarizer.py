"""Unit tests for the HaikuSummarizer."""
import uuid
import json
import pytest
from unittest.mock import MagicMock, patch
from niche.core.summarizer.haiku import HaikuSummarizer
from niche.core.models.types import Item


def make_item(title="Test title", body="Test body content."):
    return Item(
        id=str(uuid.uuid4()),
        feed_id="test-fixture",
        url="https://example.com/item",
        url_hash=uuid.uuid4().hex,
        title=title,
        body_raw=body,
        fetched_at="2026-04-28T10:00:00+00:00",
    )


def make_anthropic_response(text: str):
    """Build a minimal mock anthropic response."""
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    return response


def test_summarize_returns_summary_and_why():
    payload = json.dumps({"summary": "Short summary.", "why_it_matters": "Important for Tier-1s."})
    client = MagicMock()
    client.messages.create.return_value = make_anthropic_response(payload)
    summarizer = HaikuSummarizer(anthropic_client=client)
    item = make_item()
    result = summarizer.summarize(item, bundle=MagicMock())
    assert "summary" in result
    assert "why_it_matters" in result
    assert result["summary"] == "Short summary."
    assert result["why_it_matters"] == "Important for Tier-1s."


def test_summarize_fallback_non_json():
    """If LLM returns plain text (not JSON), use as summary."""
    client = MagicMock()
    client.messages.create.return_value = make_anthropic_response("A plain text summary here.")
    summarizer = HaikuSummarizer(anthropic_client=client)
    item = make_item()
    result = summarizer.summarize(item, bundle=MagicMock())
    assert result["summary"] == "A plain text summary here."
    assert result["why_it_matters"] == ""


def test_summarize_uses_body_translated_if_set():
    """body_translated takes priority over body_raw."""
    call_args_list = []

    def capture_create(**kwargs):
        call_args_list.append(kwargs)
        return make_anthropic_response(json.dumps({"summary": "ok", "why_it_matters": ""}))

    client = MagicMock()
    client.messages.create.side_effect = capture_create
    summarizer = HaikuSummarizer(anthropic_client=client)
    item = make_item(body="raw body")
    item.body_translated = "translated body content"
    summarizer.summarize(item, bundle=MagicMock())
    content = call_args_list[0]["messages"][0]["content"]
    assert "translated body content" in content


def test_summarize_retries_and_raises_on_persistent_failure():
    """After 2 failed attempts, raises RuntimeError."""
    client = MagicMock()
    client.messages.create.side_effect = Exception("API error")
    summarizer = HaikuSummarizer(anthropic_client=client)
    item = make_item()
    with pytest.raises(RuntimeError, match="failed after 2 attempts"):
        summarizer.summarize(item, bundle=MagicMock())
    assert client.messages.create.call_count == 2


def test_summarize_uses_prompt_meta_model():
    prompt_meta = MagicMock()
    prompt_meta.model = "claude-haiku-4-5"
    prompt_meta.body = "Summarize this."
    client = MagicMock()
    client.messages.create.return_value = make_anthropic_response(
        json.dumps({"summary": "s", "why_it_matters": "w"})
    )
    summarizer = HaikuSummarizer(anthropic_client=client, prompt_meta=prompt_meta)
    assert summarizer._model == "claude-haiku-4-5"
    item = make_item()
    summarizer.summarize(item, bundle=MagicMock())
    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5"
    assert call_kwargs["system"] == "Summarize this."
