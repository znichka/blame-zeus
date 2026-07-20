# ADR-012: External-Text Reference Identification (Allusion Detection with Corpus-Grounded Explanation)

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-12  |
| **Status**   | Proposed    |
| **Amends**   | Nothing yet (new consumer flow; extends the grounding policy in `CONCEPT.md §5, §10`) |

---

> **Web-only note (ADR-016, DEV-058):** this proposal's "Telegram bot as photo entry point" framing
> (below, and Action Item 1's "alongside the Telegram bot" phasing) predates the web-only pivot —
> `telegram-bot` was removed. If this ADR is ever accepted, the photo-input affordance would need
> to land on the web UI (or a future consumer) instead; the rest of the design (detect → verify →
> reformulate → reuse pipeline) is unaffected. Left as originally written below for history.

---

## Context

A reader encounters a passage in a **modern book** that alludes to Greek myth — sometimes by name
("she wove like Arachne herself"), often obliquely ("he flew too close to the sun", "the face
that launched a thousand ships") — and wants to send that text chunk (or a photo of the page) and
get the reference explained: which myth, which figures, what the ancient sources actually say.

This breaks the product's core assumption in one specific place. Every existing flow answers
*from* the corpus: the question names something, retrieval finds it. Here the **input text is not
in the corpus and never will be** — the connection between "flew too close to the sun" and Icarus
exists only in the LLM's world knowledge. No retrieval, schema, or extraction improvement changes
that. Recognizing the allusion *requires* letting the model use its training knowledge — the
capability the product otherwise deliberately fences off (`CONCEPT.md §2`: hallucination and
false certainty are the named failure modes).

At the same time, this use case is where the product's differentiator lands hardest: a modern
author's "Achilles heel" reference rests on a *late* tradition (Statius; Homer never mentions
it — `CONCEPT.md §2` uses exactly this example). A generic assistant retells the pop-culture
version; this product can explain what the curated ancient sources actually say, attributed, and
flag that the alluded-to version is post-Homeric.

**Related but distinct — out of scope here:** verbatim quote lookup ("which ancient source is
this exact quote from?") is a retrieval problem over `narrative_chunks` (lexical `pg_trgm` +
semantic search) with no world-knowledge component. If wanted, it is a separate, smaller
decision; conflating it with allusion detection would blur this ADR's policy boundary.

## Decision

### 1. Policy: LLM world knowledge is permitted for *detection only*; every explanation is corpus-grounded

This is the ADR's core decision and the boundary all implementation must respect:

- The model may use training knowledge to **recognize** that a passage alludes to a myth or
  figure and to name the candidate.
- Nothing detected is ever **explained** from training knowledge. Explanations are produced by
  the existing grounded pipeline (retrieval + citations + conflict enrichment + grounded
  refusal). A detected reference the corpus cannot substantiate is reported as such, never
  narrated from memory.

This *extends* the grounding guarantee rather than weakening it: the assertion surface (answers,
citations, conflicts) remains 100% corpus-backed; only the *lookup key* may come from the model.

### 2. New entry point, not a new route

`POST /api/v1/explain-references` accepting `{text}` or an image. The input is a passage, not a
question — it does **not** pass through `QueryRouter` (same reasoning as ADR-007: don't ask a
classifier to guess what a different mechanism can determine). The web UI gets a second input
affordance; the Phase 2 Telegram bot forwards photos here (sending a snapshot of a book page is
this feature's natural habitat).

### 3. Pipeline: detect → verify → reformulate → reuse

```
image? → one vision transcription call (AnthropicChatModel supports image content;
         stays inside the @AiService-only guardrail)
text   → AllusionExtractor (@AiService, temp 0.0)
         → [{phrase, candidateEntity, candidateMyth, confidence}], cap 3
for each candidate:
   resolve against entities → entity_aliases → trigram      ← the verification gate
   unresolved → report honestly ("possibly alludes to X; the curated sources
                contain nothing matching") — never silently dropped, never narrated
   resolved   → reformulate as an internal question
                ("Who was Icarus and what happened to him?")
                → existing QueryService pipeline, unchanged
                  (route → retrieve → cite → conflict enrichment)
response: per reference — the alluding phrase, the resolved figure/myth,
          a cited explanation, conflicts[], or the grounded not-in-corpus note
```

- **The corpus is the hallucination filter.** The failure mode of allusion detection is seeing
  myths where none exist. A candidate must resolve against the entity tables (or, fallback,
  retrieve above `minScore`) before anything is asserted about it. The LLM proposes; the data
  disposes.
- **`entity_aliases` (V14) becomes load-bearing.** Modern literature overwhelmingly uses Roman
  names (Venus, Jove, Ulysses, Hercules); the alias + trigram resolution chain built for user
  typos is exactly the bridge this feature needs. The V14 seed (~20 aliases) should be reviewed
  for coverage once this ADR is accepted.
- **Reuse, not rebuild.** Each resolved reference becomes an ordinary internal question through
  the existing pipeline — SQL safety, citations, conflict surfacing, and refusals all hold by
  construction. New code is a front door: one endpoint, one extractor `@AiService`, a fan-out
  loop, one response DTO.

### 4. Response semantics for post-classical allusions

When the alluded-to version is not what the curated sources say (the Achilles-heel case), the
response must do both: (a) surface what the sources *do* say via the normal pipeline (the seeded
Achilles death conflict flows through enrichment as always), and (b) state that the specific
version referenced is not attested in the curated corpus. This is the grounded-refusal stance
(`CONCEPT.md §13`) applied to attribution, and it is the feature's headline moment, not an
apology.

### 5. Cost and bounds

Per request: ≤1 vision call + 1 detection call + per-reference pipeline runs (~2–4 calls each),
references capped at 3 → statically bounded. Detection and transcription run at temperature 0.0.

## Rationale

1. **The capability is impossible without world knowledge, so the honest design is to admit it
   and fence it** — one named, auditable crossing point (the extractor) rather than knowledge
   leaking implicitly through prompts.
2. **The verification gate converts the product's data into a trust mechanism.** Entities,
   aliases, and retrieval thresholds — all already built — become the check on the one
   ungrounded step.
3. **This is the differentiator's best input.** Conflict awareness and source attribution matter
   most precisely when a modern text flattens a contested or late tradition into a throwaway
   allusion.
4. **Near-zero backend cost.** The pipeline, guardrails, and evaluation machinery are reused
   wholesale; the feature is additive at the edge.

## Consequences

**Positive**
- A genuinely new user scenario (reading companion) on top of the unchanged grounded backend.
- The world-knowledge boundary is written down before implementation, not discovered in review.
- Natural fit for the Phase 2 Telegram bot (photo → explanation).

**Negative / trade-offs**
- **Detection recall/precision is a new, LLM-judgment failure surface.** An oblique allusion may
  be missed (acceptable: feature degrades to "no references found") or over-detected (mitigated
  by the resolution gate and confidence threshold; residual risk accepted).
- The resolution gate inherits seed-data coverage limits: an allusion to a figure not in the
  ~60–100 seeded entities reports "nothing matching" even when the corpus narrative mentions the
  figure. The retrieval-above-`minScore` fallback softens but does not remove this.
- Vision transcription adds an input-quality dependency (photo legibility) outside the system's
  control; transcription failures must produce a clear user-facing message, not a silent empty
  detection.
- New evaluation surface: needs its own small gold set — direct-name passage, oblique allusion,
  Roman-name allusion, post-classical allusion (Achilles heel), and a no-reference bait passage
  expecting "no references found" (coordinate with ADR-010).

## Alternatives Considered

- **Single LLM call that detects and explains.** Rejected: the explanation would be training-data
  narration — the exact hallucination/false-certainty failure the product exists to prevent.
- **Embed the pasted passage and search `narrative_chunks` directly (pure RAG, no detection).**
  Rejected as the primary mechanism: modern prose embeds far from ancient translation style, and
  oblique allusions ("flew too close to the sun") retrieve unreliably; it also cannot say *which
  phrase* alludes. Retained only as the fallback resolution check in §3.
- **Route pasted passages through `QueryRouter` as a fourth route.** Rejected: a passage is not a
  question; a dedicated endpoint is deterministic where a router guess is not (same principle
  that removed the CONFLICT route in ADR-007).
- **Bundle verbatim quote lookup into this feature.** Rejected: different mechanism (no world
  knowledge, pure retrieval), different trust story; kept as a separate potential decision so
  this ADR's policy boundary stays crisp.

## Traceability

- `CONCEPT.md §2` (hallucination / false certainty; the Achilles-heel example), `§5, §10`
  (grounding policy), `§13` (grounded refusal), `§15` (persona layer — same "new consumer on a
  grounded backend" pattern).
- ADR-007 §5: conflict enrichment reused per reference; "don't ask a router to guess what a
  mechanism can determine".
- ADR-008: Anthropic chat model (vision-capable) via LangChain4j.
- `IMPLEMENTATION_PLAN.md §3` (V14 `entity_aliases`), `§5` (`QueryService`, entity-resolution
  chain), `§6` (Telegram bot as photo entry point).

## Action Items

- [ ] Decide target phase (recommended: Phase 2, alongside the Telegram bot).
- [ ] On acceptance: `AllusionExtractor` `@AiService` + `POST /api/v1/explain-references` +
      `ReferenceExplanation` DTO; vision transcription step behind the same endpoint.
- [ ] Review V14 alias seed for modern-literature coverage (Roman names, common English variants).
- [ ] Add the five-case gold set above; coordinate schema with ADR-010.
- [ ] Verify LangChain4j image-content support against the pinned beta5 version before build.
- [ ] On acceptance: log **DEV-NNN**; add a pointer note to `CONCEPT.md §15` (future directions)
      naming this ADR.
