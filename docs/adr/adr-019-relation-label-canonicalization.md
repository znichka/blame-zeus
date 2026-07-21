# ADR-019: Relation-Label Canonicalization (`relation_aliases`)

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-21  |
| **Status**   | Accepted    |
| **Amends**   | — (parallels ADR-007/DEV-022 `claim_type_aliases` for the `relationships.relation` column) |
| **Amended by** | —         |
| **Supersedes** | —         |

---

## Context

`relationships` (Flyway V11) holds 2,496 seeded rows across **131 distinct free-text `relation`
strings**. The distribution is a steep head plus a long tail: `parent_of` (1,273), `killed_by`
(475), `married_to` (329), `child_of` (104), `sibling_of` (45), `son_of` (21), `killed` (20), then
~124 one-off labels. The tail mixes three genuinely different cases:

- **Synonyms of a canonical relation** — `son_of` / `child_of` / `daughter_of` all mean `parent_of`
  (inverted); `married_to` / `wife_of` / `wedded` mean `marriage`.
- **Inverses of a canonical relation** — `killed` vs `killed_by`, `child_of` vs `parent_of`: the
  same edge with `from`/`to` swapped.
- **Legitimate long-tail free text** — `gave_scepter_to`, `abductor_of`, `companion_of`: real,
  low-frequency semantics that should be preserved as-is.

`SchemaIntrospector` advertises the live `relation` value vocabulary in the `TextToSqlAgent` system
prompt. DEV-041 already demonstrated that vocabulary quality directly drives text-to-SQL quality —
an alphabetical `LIMIT 50` silently dropped `parent_of` from the prompt and broke lineage queries
until it was reordered by frequency. A 131-value vocabulary dominated by near-duplicate synonyms
dilutes the signal: the model must guess which of `son_of` / `child_of` / `parent_of` the data
actually uses, and queries fragment across all three.

The project already solved the identical problem for `variant_claims.claim_type`: ADR-007 + DEV-022
introduced the **`claim_type_aliases`** DB table — a shared `normalize()` map read by *both* the
Python extraction/seedgen side and the Kotlin runtime (`ConflictLookup`), with new surface variants
appended via follow-up migrations (e.g. V9_2's `birth`→`parentage`), never hardcoded in code or JSON.

## Decision

Introduce **`relation_aliases`**, the relationship-column analogue of `claim_type_aliases`:

1. **New table (new Phase-2 Flyway migration):**
   ```sql
   relation_aliases(
     alias      TEXT PRIMARY KEY,   -- lower(trim()) surface form, e.g. 'son_of'
     canonical  TEXT NOT NULL,      -- e.g. 'parent_of'
     inverse    BOOLEAN NOT NULL DEFAULT FALSE  -- true when the alias is the reversed edge
   )
   ```
   `normalize_relation(x)` = `canonical` where `alias = lower(trim(x))`, identity otherwise —
   mirroring `claim_type_aliases`' `normalize()`.

2. **`seedgen/relationships_gen.py` applies the map at generation time**, exactly as
   `variant_claims_gen.py` already applies the claim-type map (`load_alias_map`). When a label is
   flagged `inverse = true`, the generator **swaps `from_id`/`to_id`** so every row lands on the
   canonical relation with the canonical direction (DEV-047's `parent_of`: `from_id` = parent).

3. **New surface variants are appended via follow-up migrations**, never hardcoded elsewhere — the
   DEV-022 rule. The initial alias map is produced by the Stage P3 audit's relation-label taxonomy
   check (`ingestion/audit/`, check A4), which classifies all 131 labels into canonical / synonym /
   inverse / legit-long-tail.

4. **Legitimate long-tail free-text labels are left untouched** — they have no alias row, so
   `normalize_relation` returns them unchanged. Canonicalization collapses only the synonym/inverse
   noise, not real semantics.

The net effect: `SchemaIntrospector`'s advertised relation vocabulary shrinks to a high-signal set of
canonical relations plus genuine long-tail, improving text-to-SQL directly.

## Alternatives considered

- **Hardcode the synonym map in Python and/or a JSON file.** Rejected: DEV-022 already made this
  decision for the identical claim_type problem and chose a shared DB table so Python (seedgen) and
  any future Kotlin consumer read one source of truth. Duplicating a second convention for relations
  would be inconsistent and drift-prone.
- **Collapse everything to a tiny fixed relation enum.** Rejected: destroys the legitimate long-tail
  semantics (`gave_scepter_to`, `abductor_of`) that carry real mythological meaning and are
  occasionally queried.
- **Do nothing / rely on the model to normalize at query time.** Rejected: leaves the fragmented
  vocabulary in the prompt (the DEV-041 failure mode) and splits data across synonym rows, so counts
  and joins silently under-report.
- **Add a runtime normalization layer instead of normalizing at seed time.** Rejected: the data is
  regenerated from candidates anyway (ADR-017's local-only regeneration), so normalizing once at
  generation is simpler and keeps the stored data itself clean, matching how `variant_claims` stores
  the already-normalized canonical `claim_type` (V12).

## Consequences

**Positive**
- Cleaner, higher-signal relation vocabulary for text-to-SQL (the DEV-041 lesson, applied to
  relations); queries stop fragmenting across synonym labels.
- One consistent normalization mechanism across `claim_type` and `relation`.

**Negative / costs**
- A new table, a new migration, and a generation-time step to maintain; inverse handling in
  `relationships_gen.py` must be correct or edges point the wrong way (guarded by the audit's
  direction checks, A3).
- The canonical-edge collapse (`canonical_edge.py`) interacts with normalization — normalization
  runs first so contested edges are compared on canonical relation+direction.

**Follow-ups**
- Record `DEV-059`; author the `relation_aliases` migration (new Phase-2 V-number) at Stage P3;
  wire it into `seedgen/relationships_gen.py` and confirm `SchemaIntrospector` reflects the shrunk
  vocabulary. Initial alias rows come from the audit A4 taxonomy output.
- Implementation detail: `IMPLEMENTATION_PLAN_PHASE2.md §4`; checklist: `TODO2.md` Stage P3.
