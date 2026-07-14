import os
from unittest.mock import MagicMock, patch

# Module-level instructor client requires these at import time (matches
# pipeline/embedding_pipeline.py's OPENAI_API_KEY pattern).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("EXTRACTION_MODEL", "claude-opus-4-8")

import extraction.claim_extractor as ce
from extraction.schema import ExtractedFacts
from loader.source_registry import SOURCE_REGISTRY


def test_source_hints_cover_every_registered_source():
    registry_ids = {s.source_id for s in SOURCE_REGISTRY}
    assert registry_ids == set(ce.SOURCE_HINTS.keys())


def test_extract_facts_passes_model_and_response_schema():
    expected = ExtractedFacts()
    with patch.object(ce.client.chat.completions, "create", return_value=expected) as create:
        result = ce.extract_facts("Zeus was the father of Athena.", "hesiod-theogony")

    assert result is expected
    kwargs = create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-4-8"
    assert kwargs["response_model"] is ExtractedFacts
    assert kwargs["messages"] == [{"role": "user", "content": "Zeus was the father of Athena."}]


def test_extract_facts_includes_source_hint_in_system_prompt():
    with patch.object(ce.client.chat.completions, "create", return_value=ExtractedFacts()) as create:
        ce.extract_facts("some text", "apollodorus-bibliotheca")

    system = create.call_args.kwargs["system"]
    assert ce.SOURCE_HINTS["apollodorus-bibliotheca"] in system
    assert ce.SYSTEM_PROMPT in system


def test_extract_facts_retries_on_transient_failure():
    # tenacity's @retry was already applied at import time with the real
    # wait_exponential, so patch time.sleep (what it actually calls) rather than the
    # wait strategy itself.
    expected = ExtractedFacts()
    flaky = MagicMock(side_effect=[RuntimeError("rate limited"), expected])
    with patch.object(ce.client.chat.completions, "create", flaky), patch("time.sleep", return_value=None):
        result = ce.extract_facts("some text", "hesiod-theogony")

    assert result is expected
    assert flaky.call_count == 2
