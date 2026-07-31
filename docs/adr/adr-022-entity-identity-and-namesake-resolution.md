# ADR-022: Entity Identity — Namesake Splitting, Resolution Provenance, and the Merge Gate

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-31 |
| **Status**   | Proposed (implemented by **Stage P6**, `docs/TODO-phase2-stage-p6.md`) |
| **Amends**   | ADR-004 (extends the review gate from *what a claim says* to *who its subject is*) |
| **Amended by** | —         |
| **Supersedes** | —         |

---

## Context

`docs/DATA-GAPS.md` **GAP-009** and **GAP-010** were both found on 2026-07-31, during Stage P5
Track C's per-row `variant_claims` review (DEV-136/137/138), and were filed separately because they
present differently to a reviewer. They have one root cause.

**Entity identity is decided by string matching, silently, with no evidence artifact and no review
gate.** `EntityResolver.resolve()` (`ingestion/extraction/entity_resolver.py`) dedupes a
newly-extracted name in three steps — exact match against the running name list,
`known_aliases.json` lookup, then `rapidfuzz.fuzz.ratio` at threshold 88 — and returns a canonical
string. It has no notion of *who* a name denotes. It does not know which passage the name came from,
and it has no access to the confirmed entity set.

Every downstream table inherits that decision without re-examining it:

- `relationships` mechanically, with **no human gate at all** (CLAUDE.md, Data Model).
- `variant_claims` through ADR-004's gate, which reviews *what the claim says* and takes *who the
  subject is* as given. A reviewer looking at `Lycaon | parentage | child of Priam` adjudicates the
  parentage; nothing in the workflow asks whether this `Lycaon` is the same person as the entity of
  that name already carrying 35 rows about an Arcadian king.

The two gaps are the two ways that fails.

**GAP-009 — near-miss merges.** The corpus spells the name differently from the entity it gets
attached to, and the fuzzy step bridges the gap: the text's own "Atas" (one of Priam's ~50 sons)
becomes the Titan `Atlas`; "Aesacus" becomes the underworld judge `Aeacus`; "Philaemon" becomes
Apollo's son `Philammon`. A variant of the same failure needs no fuzzy step at all — a globally
correct alias applied where it does not hold, as when Hesiod's Oceanid nymph "soft eyed Pluto"
(*Theogony* 346-403) resolves to `Hades` through the entirely legitimate `Pluto`/`Dis`→Hades row in
`entity_aliases` (V14).

**GAP-010 — exact-name namesake collisions.** Greek myth genuinely reuses names. The string is
byte-identical, so no threshold can separate the Arcadian king `Lycaon` from Priam's son, the Muse
`Urania` from the Oceanid, the Cretan king `Idomeneus` from another of Priam's sons. **≥82 confirmed
instances across the first 7 passages reviewed** — 20-30% of every Track C batch's rejections, and
by far the largest single cause of rejection in each one.

### The measurement that rules out the obvious fix

Construction: `rapidfuzz.fuzz.ratio(a, b)` (the scorer `entity_resolver.py` uses), evaluated over the
confirmed GAP-009 false-positive pairs and over the legitimate spelling-variant pairs DEV-043
identified and `duplicate_entities._translit_key` was built for.

| pair | ratio | what it is |
|---|---|---|
| `Atas` / `Atlas` | 88.9 | confirmed false positive (DEV-137) |
| `Philaemon` / `Philammon` | 88.9 | confirmed false positive |
| `Amphitryon` / `Amphictyon` | 90.0 | confirmed false positive, **already live** in `relationships` |
| `Rhodea` / `Rhode` | 90.9 | confirmed false positive |
| `Aesacus` / `Aeacus` | 92.3 | confirmed false positive |
| `Coronus` / `Cronus` | 92.3 | confirmed false positive, **already live** in `relationships` |
| `Perses` / `Perseus` | 92.3 | confirmed false positive, **already promoted** at `trust_tier=1` |
| `Cronos` / `Cronus` | 83.3 | legitimate spelling variant |
| `Athene` / `Athena` | 83.3 | legitimate spelling variant |
| `Ocean` / `Oceanus` | 83.3 | legitimate spelling variant |
| `Iphis` / `Iphitus` | 83.3 | legitimate spelling variant |

Every confirmed false positive sits at **88.9-92.3**. Every legitimate variant the threshold was
nominally tuned for sits at **83.3** — *below* the current cutoff of 88, meaning the fuzzy step is
not what catches them today; the curated alias layers are. Raising the threshold removes none of the
false positives and can only lose recall. **The fuzzy step's entire live band may be false
positives**, which is a hypothesis this ADR does not assume — Stage P6 G2 measures it against the
full corpus and decides under a pre-registered rule.

---

## Decision

Four rules. Each has an existing precedent in this repository, so none of the machinery is new.

### 1. Identity resolution emits provenance

Every `resolve()` decision is written to `ingestion/extraction/output/entity_resolutions.json`:

```json
{ "surface": "Atas", "canonical": "Atlas", "method": "fuzzy", "score": 88.9,
  "source_id": "apollodorus-bibliotheca", "passage_ref": "3.12.5" }
```

`method ∈ {exact, alias, registry, fuzzy, new}`. `resolve()` gains optional `source_id` /
`passage_ref` parameters; all **four** call sites in `run_extraction.build_candidates` already hold
`source.source_id` and `seg.passage_ref` — `run_extraction.py:118` (entities), `:124` and `:125`
(the two relationship endpoints), `:131` (variant-claim subjects).

Identity is currently **the only pipeline decision with no artifact at all** — entities,
relationships and variant_claims each have a candidates file, while resolution has nothing.
`EntityResolver.fuzzy_merges` exists but is printed by `write_output` and then discarded, and the
alias path that produced `Pluto`→Hades leaves no trace whatsoever.

The ledger is what makes a merge reviewable at all. It also gives GAP-009 the denominator its own
"what a fix needs to decide" item 3 asks for, and it lets a **future** source be reviewed by
**diffing the new merges only**, rather than re-reading the corpus.

### 2. A passage-scoped namesake registry overrides both exact and fuzzy matching

`ingestion/extraction/namesake_registry.json`, a list of reason-bearing entries:

```json
{ "name": "Pluto", "source_id": "hesiod-theogony", "passage_ref": "346-403",
  "identity": "Pluto (Oceanid)",
  "reason": "GAP-009 / DEV-136. Hesiod's Oceanid catalogue: \"soft eyed Pluto\" is one of the 3,000 daughters of Ocean, not Hades. The entity_aliases Pluto->Hades row is correct everywhere else and stays." }
```

Consulted in `resolve()` **first — ahead of the exact-match memo, the alias step and the fuzzy
step** — keyed `(lower(name), source_id, passage_ref)`, falling back to `(lower(name), source_id)`,
then to a global entry.

**"First" is load-bearing, and it drags the memo with it.** `EntityResolver._seen` is today a single
per-run cache keyed on `name.strip().lower()` and checked before everything else
(`entity_resolver.py:43-45`). Two consequences follow, and both must be implemented or the mechanism
does not work:

- A lookup inserted merely "before the alias and fuzzy steps" sits *behind* the memo's exact hit, so
  it never fires for GAP-010 — where the strings are byte-identical and the exact hit is the whole
  problem. The registry goes at position 1.
- Even at position 1, memoizing the registry's answer under the bare name re-breaks it one call
  later: `Pluto` @ *Theogony* 346-403 would write `Pluto (Oceanid)` into `_seen["pluto"]` and return
  it for every subsequent passage. A registry hit is therefore memoized under
  `(source_id, passage_ref, lower(name))`, never under the bare name. Surfaces with no registry
  entry keep today's global memo and today's behaviour unchanged.

Shape and review discipline mirror `extraction/parentage_deny_list.json` (ADR-020 rule 4) and
`extraction/known_aliases.json` — hand-maintained, reason-bearing, review-gated JSON, a form ADR-020
explicitly chose over encoding exceptions in code.

**This is the only mechanism that addresses both gaps.** It beats the fuzzy step (GAP-009) *and* it
beats exact match (GAP-010, where nothing else can, because the strings are identical), and it
survives re-extraction because it is keyed on a **corpus location**, not on a name-to-name pair. A
single entry per `(name, passage)` corrects every row extracted from that passage, now and on every
future run.

### 3. Splitting convention: `Name (descriptor)`, bare name to the dominant identity

Already in use at **67 distinct names** in `V10__seed_entities.sql` — construction
`grep -oE "\('[A-Za-z][^']*\([^']*\)'," V10__seed_entities.sql | sort -u | wc -l` — and
`entities_gen._duplicate_names` (`ingestion/seedgen/entities_gen.py:36`) already rejects
case-insensitive duplicate names, so a descriptor is the **only legal way** to hold two figures of
one name. This ADR codifies the existing convention rather than inventing one.

The shape in use covers both `(son|daughter of X)` and looser descriptors — `Cleopatra (daughter of
Tros)`, `Acamas (son of Antenor)` / `Acamas (son of Eusorus)`, `Amphithea (wife of Lycurgus)`,
`Agraulus (mother)` / `Agraulus (daughter)`. Note that each split identity is its **own row**: the
pipe shorthand used elsewhere in these docs (`Astyoche (daughter of Actor | Laomedon | Niobe |
Phylas)`) abbreviates four sibling rows, and is **not** a legal `entities.name` value.

- The bare name stays with the higher-prominence identity (A8, `audit/prominence.py`); the minor
  identity takes the descriptor.
- **A descriptor form is never aliased back to the bare name** in `entity_aliases` or
  `known_aliases.json`. Doing so re-collapses the split on the next run — which is precisely the
  `Pluto`→Hades mechanism, one layer up.
- Rows are reassigned to the split identities **by registry entry** (rule 2), not by hand-editing
  each row. That is the economy of the design: per-passage judgement, not per-row.

GAP-006's `Ajax` merge is the inverse problem — one person fragmented across 16 entities — and
DEV-121 is the precedent for the per-row re-derivation cost either direction incurs.

### 4. The merge gate

A fuzzy or alias merge onto an entity already established from **other** passages is a reviewable
event: it is surfaced to the reviewer with its evidence, never silently applied. Implemented as
`assess_collision_risk` in `ingestion/extraction/claim_evidence.py`, printed by `review_passage`
beside the existing bucket label.

Consistent with **ADR-004 Amendment 1**: *the pre-verification signal may order and annotate; it may
never promote.* No code path writes `trust_tier=1`, and no code path splits an entity. The gate
produces a signal for a human; the human takes the decision.

---

## Consequences

**Positive**

- The single largest cause of Track C rejection becomes visible **before** a reviewer opens the DB.
  Today a reviewer discovers `Atas`→`Atlas` by manually cross-referencing live `entities` and
  `relationships` for every suspicious row; the ledger states it outright.
- Identity fixes become **durable**. A correction made in the registry re-applies on every
  subsequent run and to every future source, instead of being a candidate-file edit that the next
  extraction overwrites.
- Re-resolution is **free**. `build_candidates` applies `resolve()` to segment facts whether or not
  they came from the checkpoint cache, so a resolver or registry change takes effect on a plain
  re-run with **zero Anthropic API calls**.
- **Zero detector budget spent** (`docs/TODO2.md`, *Cross-cutting rules*). Every piece of new tooling
  lives in `ingestion/extraction/`, which is **outside the `audit` package** — `discover_checks()`
  (`audit/__main__.py:47`) walks `pkgutil.iter_modules(audit_pkg.__path__)` and never sees it, so the
  `NAME`/`run` attribute check is not even reached. (The invariant is *location*, not the absent
  attribute: the same module moved into `audit/` and given a `NAME` would register.) Same structural
  argument P5 Track B1 made for `claim_evidence.py`. No `audit/` check is added or modified, and E1's
  "A16 is the last one" holds.
- The recall safety net for any change to the fuzzy step already exists: **A1**
  (`audit/duplicate_entities.py`) scans the confirmed set at the same threshold 88 **and runs a
  second, transliteration-normalized pass** (`_translit_key`, DEV-043's Cronos/Cronus lesson). The
  second pass is the one that matters here: the 83.3-scoring legitimate variants are *below* 88, so a
  threshold-only guard would be blind to exactly the recall this ADR needs protected.

**Negative / costs**

- **Re-resolution re-keys review decisions.** `subject_name` is part of `_CLAIM_IDENTITY`, so a
  changed canonical name means `_write_claims_preserving_review` cannot match the row and reports it
  under `WARNING: N reviewed row(s) are no longer produced by extraction`. Exposure at the time of
  writing, construction `Counter(r.get('trust_tier', 3) for r in variant_claims_candidates.json)`:
  **569 tier-1 + 523 tier-2 = 1,092 decisions** against 7,429 rows. Stage P6 G0 migrates these keys
  rather than losing them, and it is the reason the stage runs **before** the remaining Track C
  sprints rather than after — the exposure grows with every batch.
- The registry is hand-maintained and grows with the corpus. It is bounded by the same discipline as
  `parentage_deny_list.json`: an entry requires a stated reason, and entries are added from
  adjudicated evidence, never speculatively.
- Splitting an entity requires re-deriving which already-seeded rows belong to which identity —
  genuine per-passage work, at whatever scale the confirmed collision list reaches. Stage P6 G5
  bounds this by prominence rather than opening it ended.

**Known limit, accepted**

A registry key of `(name, source_id, passage_ref)` cannot separate two figures who share a name
**inside a single passage**. `Lynceus` in `apollodorus-bibliotheca 2.1.5` is exactly that: Aphareus's
son and Egyptus's son both appear there. Such instances are fixed individually at the entity level.
Sub-passage granularity is not adopted now; if the P6 G5 sweep shows the shape is common it is
recorded in `docs/DATA-GAPS.md` as a known-and-accepted limit, on evidence.

---

## Alternatives considered

**Raise the rapidfuzz threshold.** Rejected on measurement — every confirmed false positive scores
88.9-92.3 while the variants the threshold protects score 83.3, so any reachable threshold either
keeps all the false positives or destroys recall. This was GAP-009's own first suggestion, and the
measurement above is why it is not the answer.

**A pairwise `never_merge` blocklist alone.** Addresses GAP-009's confirmed pairs but is blind to
GAP-010 by construction — there is no pair to block when both names are the same string. Retained
only as the fallback branch of P6 G2's decision rule, not as the primary mechanism.

**Scope-restrict `entity_aliases` rows in the schema.** GAP-009's "what a fix needs to decide" item 2
raised adding a scope column to `entity_aliases`. Rejected: `entity_aliases` is a *runtime* lookup
serving `ConflictLookup` and query-time entity resolution, where the global `Pluto`→Hades mapping is
correct and wanted. The defect is at *extraction* time, so the fix belongs in the extraction layer —
and a JSON registry there needs no migration, no schema change, and no `core-api` change at all.

**An LLM disambiguation pass over every extracted name.** Rejected on cost and on ADR-004's own
posture: the extraction model already produced these names, so asking it to re-adjudicate its own
merges adds a second unreviewed judgement rather than a gate. The reviewer signal (rule 4) is
deterministic, free, and feeds the human gate that already exists.

**Leave the pipeline frozen and fix identities only in the curated candidate files.** This is what
happens today by default. Rejected because it protects nothing: the curated files are not what
`resolve()` reads, so the next source or re-extraction reintroduces the same merges, and the fix has
to be re-done by hand each time.

---

## References

- `docs/DATA-GAPS.md` — GAP-009, GAP-010 (the two gaps this ADR closes); GAP-006 (the inverse
  over-fragmentation problem and the `Name (descriptor)` precedent)
- `docs/TODO-phase2-stage-p6.md` — the implementing checklist, tracks G0-G7
- `docs/DEVIATIONS.md` — DEV-136, DEV-137, DEV-138 (where every confirmed instance was adjudicated);
  DEV-043 (the spelling-variant lesson the threshold serves); DEV-121 (the Ajax merge, the per-row
  re-derivation precedent)
- ADR-004 + Amendment 1 — the review gate this ADR extends from claim content to subject identity
- ADR-020 rule 4 — `parentage_deny_list.json`, the curated-JSON-exception-list precedent
- `ingestion/extraction/entity_resolver.py`, `run_extraction.py`, `claim_evidence.py`;
  `ingestion/audit/duplicate_entities.py` (A1), `prominence.py` (A8)
