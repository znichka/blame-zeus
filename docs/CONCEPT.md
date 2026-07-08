# Greek Mythology Lore Assistant — PoC Concept

## 1. Overview

An AI assistant that answers questions about Greek mythology and, for every
factual claim it makes, tracks and reports **which ancient source the claim came
from**. The defining feature is not that it answers myth questions — plenty of
tools do that — but that it treats the ancient corpus the way it actually is:
a collection of sources that frequently **disagree with each other**. When two
texts give conflicting accounts, the assistant surfaces the disagreement and
attributes each version to its source, rather than flattening everything into
one confident (and often wrong) answer.

## 2. Problem Statement

General-purpose LLMs answer Greek mythology questions fluently but with three
recurring failure modes:

- **Hallucination.** The model conflates versions of each myth from training
  data and invents details.
- **False certainty.** It presents one version of a myth as *the* version. The
  "Achilles' heel" story, for example, is late (Statius, 1st c. CE) — Homer
  never mentions it — but a generic model states it as plain fact.
- **No provenance.** There is no way to ask *"who said that?"* and get a source
  citation to an ancient text.

The PoC addresses all three by grounding every answer in a curated corpus with
source attribution on each claim.

## 3. Expected Value

- **Grounded answers with citations** instead of confident invention.
- **Conflict-aware retrieval**: reports *"Source A says X; Source B says Y"*
  rather than picking one silently.
- **Provenance / auditability**: every claim traces to a specific ancient text
  and translation.
- **Transferable pattern**: generalizes to any domain with conflicting or
  versioned documentation.

## 4. Target User Scenario

A user, student, or writer asks natural-language questions and gets answers that
are grounded, cited, and honest about uncertainty. Four question types are
supported:

| Question type | Example | How it is answered |
|---|---|---|
| **Fact-based** | "Why did Athena turn Arachne into a spider?" | Semantic retrieval over narrative text (RAG) |
| **Data** | "Which Olympians are children of Cronus?" | Text-to-SQL over the structured entity/relationship tables |
| **Mixed** | "Which heroes had a divine parent and died in the Trojan War, and what was the story?" | SQL to filter/join entities, then RAG to narrate, then synthesis |
| **Conflict** *(the differentiator)* | "Who were Aphrodite's parents?" | Query the variant-claims table; report each attributed version |

## 5. Core Concept: Source Tracking & Conflict Awareness

The central design decision is to model **claims** and **sources** as
first-class data, not just narrative text.

The ancient mythographers **already annotate their own disagreements inline**.
Apollodorus writes of Io: "the annalist Castor and many of the tragedians allege
that Io was a daughter of Inachus; and Hesiod and Acusilaus say that she was a
daughter of Piren." One entity, two conflicting parentage claims, each attributed
to multiple named sources — in a single paragraph. The variant-claims data is
therefore something to **extract**, not something to invent.

Each atomic claim (e.g. "Aphrodite's father is Zeus") is stored with:

- the entities involved,
- the relationship or assertion type,
- the **source** it came from (author + specific work + passage reference),
- optionally, the **source stance** (see §6), and
- the translation used (for copyright and citation correctness).

At query time the assistant checks whether multiple claims answer the same
question. If they conflict, it returns all of them with attribution instead of
choosing one.

## 6. Source Stance (optional depth)

Each source can carry an **epistemic stance** — how the material is meant to be
read:

- **poetic-myth** — narrative poetry (Homer, Ovid)
- **mythographic-handbook** — systematic compilation (Apollodorus, Hyginus)
- **cosmological** — genealogy of the divine order (Hesiod's *Theogony*)
- **hymnic** — praise poems to individual deities (Homeric Hymns)

This lets the assistant report not just *"sources disagree"* but *"the handbooks
record X while the poets dramatize Y"* — a more precise answer, since documents
written at different levels of authority carry different weight.

## 7. Scope of Content

Greek mythology only — no later Greek history, no rationalizing historians.
Three tiers:

1. **Primordials & cosmology** — Chaos, Gaia, Ouranos, etc.
2. **Gods** — Titans, then Olympians.
3. **Heroes, mortals & monsters** — Achilles, Heracles, Perseus, Theseus,
   Odysseus, Jason, and their attached figures (Medusa, the Minotaur, the Hydra).

The hero/mortal tier is **central** — it carries the bulk of the narratives,
generates the most source conflicts, and is what a demo audience instinctively
asks about. Divine parentage of heroes also lets genealogy queries cross the
god/mortal boundary.

## 8. Sources & Data-Source-Type Mapping

All sources use **public-domain translations** (early Loeb editions). Available
via the Theoi Classical Texts Library and ToposText. Modern translations are
excluded.

Handbook / genealogical material → primarily **SQL**, also indexed for RAG.
Narrative poetry → primarily **RAG**, key relationships pulled into SQL.

| Source | Translation (public domain) | → SQL | → RAG | Primary role |
|---|---|---|---|---|
| **Apollodorus, *Bibliotheca*** | Frazer, 1921 Loeb | ✅ primary | ✅ | **Spine.** Systematic genealogical handbook; organized by lineage, rich in attributed variants. Feeds entities, relationships, myth summaries, and most variant-claims. |
| **Hesiod, *Theogony*** | Evelyn-White, 1914 Loeb | ✅ primary | ✅ | Divine-generation backbone (Chaos → Titans → Olympians). Conflicts with Apollodorus at the cosmological level. |
| **Homer, *Iliad* & *Odyssey*** | Murray, 1919 / 1924 Loeb | ⚠️ selectively | ✅ primary | Heroic/Trojan narrative; earliest source and a valuable conflict anchor. |
| **Homeric Hymns** | Evelyn-White, 1914 Loeb | ⚠️ selectively | ✅ | Alternate deity parentage conflicting with Hesiod. |
| **Ovid, *Metamorphoses*** | public-domain verse translation | ⚠️ selectively | ✅ | Roman-era retellings; rich second wave of conflicts. |
| **Hyginus, *Fabulae*** *(stretch)* | Grant / older PD ed. | ✅ | ✅ | Additional handbook-style entity/variant coverage. |
| **Hesiod, *Catalogues of Women* (fragments)** *(stretch)* | Evelyn-White, 1914 Loeb | ✅ | ✅ | Dense attributed variant-claims material. |

### Data preparation

- **Narrative text → RAG:** load local .txt corpus files, clean, chunk, embed
  into a vector store. Corpus files are prepared from public-domain plaintext
  editions (Gutenberg, sacred-texts.com, Theoi) and stored in `ingestion/corpus/`
  before running ingestion — this is a manual developer step, not automated.
- **Structured tables & variant-claims → LLM-extracted from the ingested corpus,
  tiered by risk, with a human review gate on the highest-stakes data:**
  entities and basic relationships (parent_of, married_to, killed_by) are
  extracted from the cleaned corpus text by an offline LLM pass and merged into
  seed migrations after a developer spot-check — this data is largely
  unambiguous handbook material (mainly from Apollodorus, the "spine" source),
  so the risk of a wrong row is low and mechanical review is sufficient.
  `variant_claims`, by contrast, is the data the product's trustworthiness
  depends on — a misattributed or hallucinated conflict actively undermines the
  differentiator — so every extracted claim candidate is staged at
  `trust_tier=3` and requires explicit developer approval (promoting it to
  `trust_tier=1`) before it enters the real seed data. The ancient mythographers
  frequently flag their own disagreements inline (the Io example: "Castor... say
  Io was a daughter of Inachus; Hesiod and Acusilaus say... a daughter of
  Piren"), which makes this specific case well-suited to extraction — the
  source is doing the conflict-detection, the LLM is just structuring it.
  `sources`, `myths`/`myth_participants`, and `entity_aliases` remain
  hand-curated: bibliographic metadata, editorial myth groupings, and
  cross-cultural name mappings aren't things the corpus text yields via
  extraction. See `IMPLEMENTATION_PLAN.md §4` for the extraction pipeline
  design.

### Translator footnotes (Frazer, Evelyn-White, Murray) — out of pipeline scope

Loeb translators, especially Frazer, annotate the primary text with extensive
scholarly footnotes that often name additional ancient authors and their
divergent accounts. These footnotes are a genuinely rich source of variant
material — richer, in Frazer's case, than the main narrative itself — but for
this PoC they are **not** scraped, chunked, or embedded as RAG-retrievable
content, and they are **not** modeled as a distinct `sources` row. Footnotes
are consulted manually, off to the side, only as reference material when
hand-curating `variant_claims` rows (§9); the automated ingestion pipeline
sees and stores only the main translated narrative.

This means a question whose best-grounded answer lives solely in a footnote
will currently produce a grounded refusal rather than a cited answer — an
accepted, explicit limitation for this PoC rather than an oversight. Treating
footnotes as a first-class, independently citable source (their own `sources`
row, e.g. `frazer-notes-apollodorus`, with a new `stance` value such as
`editorial-commentary`) is deferred to a future iteration — see §15.

## 9. Proposed Data Model (SQL side)

- `entities(id, name, type, generation, domain)` — `type` ∈ {primordial, titan,
  olympian, other_god, hero, mortal, monster, nymph}
- `relationships(from_id, relation, to_id, source_id)` — e.g. parent_of,
  married_to, killed_by
- `myths(id, title, location, summary)`
- `myth_participants(myth_id, entity_id, role)`
- `sources(id, author, work, passage_ref, translation, stance)`
- `variant_claims(id, subject_entity_id, claim_type, claim_value, source_id)` —
  multiple rows per question when sources disagree

Vector store: narrative chunks with `source_id` metadata so RAG answers can
also cite.

## 10. AI Capabilities (real-time, in-application)

Requests are sent to an LLM at query time; AI is used *within* the app, not
only to write it:

1. **Query routing** — decides per question whether to run SQL, RAG, or both;
   decision exposed to the user.
2. **Text-to-SQL generation** — including **recursive CTEs** for lineage
   ("trace from Chaos to Zeus").
3. **RAG synthesis** — retrieve narrative chunks and compose a grounded, cited
   answer.
4. **Conflict-aware answering** — detect multiple attributed claims and present
   all of them.
5. **Grounded refusal** — when the corpus doesn't cover something, say so
   instead of inventing.

## 11. Tooling & Integrations

- LLM API for routing, text-to-SQL, and synthesis (real-time).
- SQL database (Postgres 16 + pgvector) for entity/relationship/claims tables.
- Vector store for narrative RAG.
- Ingestion script (Python) that loads local .txt corpus files, cleans, chunks, and embeds them into the vector store.
- Application layer (chat UI) showing routing decisions and citations.

## 12. Evaluation

15–20 gold questions across the four categories (fact, data, mixed, conflict)
with known answers, scored as an accuracy figure — signals the team validated
*whether it works*, not just *that it runs*.

## 13. Demo Highlights

- **Recursive genealogy** rendered as a family tree — proves the SQL backend
  is real.
- **A source conflict** — "Who were Aphrodite's parents?" — showing attributed,
  disagreeing sources.
- **A multi-hop mixed question** chaining SQL filtering into RAG narration.
- **A grounded refusal** — a correct "the texts don't say" is more impressive
  than a fluent wrong answer.

## 14. Copyright / Licensing Note

Only age-expired public-domain translations (Frazer 1921, Evelyn-White 1914,
Murray 1919–24) are ingested; modern translations are excluded. State this
explicitly to prevent accidental ingestion from a copyrighted edition. The
underlying myths are ancient and not under copyright; the risk is solely in the
choice of translation.

## 15. Future Directions (out of scope for this PoC)

- Expand into **local-tradition** sources (Pausanias) for place-anchored
  variants and a geography dimension.
- Add a **historicizing** source (e.g. Plutarch on Theseus) to demonstrate
  myth-vs-history disagreement via the `stance` field.
- **Persona layer** ("ask a character") on top of the grounded backend, still
  citing canon and refusing beyond it.
- **Ingest translator footnotes as a first-class source.** Scrape each
  translator's editorial notes (starting with Frazer's on Apollodorus, since
  they carry the most cross-referenced variant material), give them their own
  `sources` row and an `editorial-commentary` stance, and chunk/embed them
  into RAG so answers can cite "Frazer's note on Apollod. 1.1.1" distinctly
  from the primary text. Deferred from the PoC (see §8) because it adds a
  second scrape target and schema change per source, and raises an
  attribution question (crediting Frazer's paraphrase vs. the ancient author
  he cites) that needs its own decision.
