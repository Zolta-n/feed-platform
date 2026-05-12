"""Unit tests for translation providers."""
import pytest
from unittest.mock import MagicMock, patch


# ── HaikuTranslator ──────────────────────────────────────────────────────────

def make_anthropic_response(text: str):
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    return response


def test_haiku_translator_returns_translated_text():
    from niche.core.translator.haiku_translator import HaikuTranslator
    client = MagicMock()
    client.messages.create.return_value = make_anthropic_response("Translated text here.")
    translator = HaikuTranslator(anthropic_client=client)
    result = translator.translate("Original text", target_language="en")
    assert result == "Translated text here."


def test_haiku_translator_empty_string_passthrough():
    """Empty input should be returned as-is without calling the API."""
    from niche.core.translator.haiku_translator import HaikuTranslator
    client = MagicMock()
    translator = HaikuTranslator(anthropic_client=client)
    result = translator.translate("   ", target_language="en")
    assert result.strip() == ""
    client.messages.create.assert_not_called()


def test_haiku_translator_raises_on_api_error():
    """API errors are propagated (no silent swallowing)."""
    from niche.core.translator.haiku_translator import HaikuTranslator
    client = MagicMock()
    client.messages.create.side_effect = Exception("API timeout")
    translator = HaikuTranslator(anthropic_client=client)
    with pytest.raises(Exception, match="API timeout"):
        translator.translate("Some text", target_language="en")


def test_haiku_translator_uses_prompt_meta_model():
    from niche.core.translator.haiku_translator import HaikuTranslator
    prompt_meta = MagicMock()
    prompt_meta.model = "claude-haiku-4-5"
    client = MagicMock()
    client.messages.create.return_value = make_anthropic_response("ok")
    translator = HaikuTranslator(anthropic_client=client, prompt_meta=prompt_meta)
    assert translator._model == "claude-haiku-4-5"
    translator.translate("Hello", target_language="de")
    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5"


# ── DeepLTranslator ───────────────────────────────────────────────────────────

def test_deepl_translator_not_available_without_package():
    """DeepLTranslator raises ImportError if deepl is not installed."""
    import sys
    original = sys.modules.get("deepl")
    sys.modules["deepl"] = None  # simulate missing package
    try:
        # Force reimport with patched modules
        if "niche.core.translator.deepl_translator" in sys.modules:
            del sys.modules["niche.core.translator.deepl_translator"]
        from niche.core.translator.deepl_translator import DeepLTranslator
        with pytest.raises(ImportError):
            DeepLTranslator(api_key="fake-key")
    finally:
        if original is None:
            sys.modules.pop("deepl", None)
        else:
            sys.modules["deepl"] = original
        # Force reimport on next access
        sys.modules.pop("niche.core.translator.deepl_translator", None)
