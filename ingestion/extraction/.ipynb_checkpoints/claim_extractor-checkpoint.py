import os

import instructor
from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from extraction.schema import ExtractedFacts

# ADR-008: offline extraction runs on Claude Opus 4.8 via instructor, a separate model
# (and separate env var) from the runtime chat model (LLM_CHAT_MODEL) and the embedding
# model (EMBEDDING_MODEL).
EXTRACTION_MODEL = os.environ["EXTRACTION_MODEL"]

client = instructor.from_anthropic(Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]))

# Per-source extraction hints — each mythographer/poet flags disagreement differently.
# `is_contested` is a soft signal for the prompt, never a storage gate (ADR-007 §1):
# every attributed claim is extracted regardless of whether the source itself flags it.
SOURCE_HINTS: dict[str, str] = {
    "apollodorus-bibliotheca": (
        "This is a mythographic handbook that routinely names competing genealogies in "
        "one sentence (e.g. 'some say ... but Hesiod says ...'). Extract each named "
        "alternative as its own variant_claims entry and set is_contested=true on any "
        "relationship it disagrees with."
    ),
    "hesiod-theogony": (
        "This is a cosmological genealogy poem. Extract parentage and marriage claims "
        "even when stated flatly, with no disagreement language."
    ),
    "hesiod-homeric-hymns": (
        "These are narrative hymns to individual gods. Extract parentage, marriage, and "
        "notable deeds the hymn asserts about its subject."
    ),
    "homer-iliad": (
        "Extract parentage, marriage, and death claims (how or by whom a warrior died) "
        "stated in the narrative, including patronymic epithets like 'son of'."
    ),
    "homer-odyssey": (
        "Extract parentage, marriage, and death claims stated in the narrative, "
        "including patronymic epithets like 'son of'."
    ),
    "ovid-metamorphoses": (
        "This is a Roman-era retelling that sometimes diverges from the Greek handbook "
        "tradition (different parentage, different manner of death or transformation). "
        "Flag such divergences as is_contested=true."
    ),
}

SYSTEM_PROMPT = (
    "You extract structured Greek/Roman mythology facts from a single passage of an "
    "ancient source. Extract every named entity (god, hero, mortal, monster, ...), "
    "every parent_of/married_to/killed_by relationship, and every attributed claim "
    "(parentage, marriage, death, or another notable claim type) stated or clearly "
    "implied in the passage. Use each entity's most common English name. Do not invent "
    "facts not present in the text. Set is_contested=true only when the passage itself "
    "signals a disagreement (e.g. 'some say', 'others hold', 'according to X, ... but "
    "according to Y, ...')."
)


@retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(5), reraise=True)
def extract_facts(segment_text: str, source_id: str) -> ExtractedFacts:
    hint = SOURCE_HINTS.get(source_id)
    system = f"{SYSTEM_PROMPT}\n\n{hint}" if hint else SYSTEM_PROMPT
    return client.chat.completions.create(
        model=EXTRACTION_MODEL,
        response_model=ExtractedFacts,
        # 4096 was too low for genealogically-dense segments (e.g. the
        # Titanomachy passage packs many entities/relationships/claims into one
        # segment) and raised IncompleteOutputException — retrying doesn't help
        # since the failure is deterministic, not transient. 16000 is Anthropic's
        # documented safe non-streaming default (well under the SDK's HTTP
        # timeout guard for large max_tokens).
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": segment_text}],
    )
