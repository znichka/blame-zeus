# Stage 4 — Seed Data (Extraction-Assisted): Detailed Checklist

**Done when:** `GET /api/v1/entities` returns ≥60 entities; `GET /api/v1/sources` returns 6 rows; `VariantClaimRepositoryTest` finds ≥2 conflict rows for Aphrodite.

> This stage was formerly numbered Stage 2 and was pure hand-curation. Redesigned per
> `docs/adr/adr-004-seed-data-extraction-strategy.md`: `entities`/`relationships` are now
> LLM-extracted from the ingested corpus with a developer spot-check; `variant_claims`
> candidates require explicit per-row review before promotion to `trust_tier=1`. `sources`,
> `myths`/`myth_participants`, and `entity_aliases` remain hand-curated, unaffected by this
> change. **Prerequisite: Stage 2 (Ingestion Setup) and Stage 3 (Full Corpus) must be complete**
> — extraction reads real cleaned corpus text, so `narrative_chunks` must already be populated
> for all 6 sources before this stage's extraction tracks can run.

Before starting, re-read `DEVIATIONS.md`. Relevant carry-overs:
- **DEV-003** — Flyway 10.10.0; `V9`–`V14` SQL syntax unaffected.
- **DEV-008** — Testcontainers pinned to `1.21.4`; reuse `AbstractContainerTest` for every test in this stage.
- No `@AiService` interfaces are touched — the extraction pipeline is Python/offline, not core-api/LangChain4j, so **DEV-004** does not apply here.

## Parallelization Guide

```
Track A (extraction pipeline code) ─┐
Track D (JPA entities+repos)        ├─→ Track B (run extraction, review) ─→ Track C (Flyway V9–V14) ─→ Track G (repo tests) ─→ Track H (verify)
Track E (DTOs)                      ┘                                                    ↑
Track F (REST endpoints) ── needs D ┘                                                    │
                                     Track C's V9/V13/V14 items have no dependency on B ───┘
```

- **A, D, E have no dependency on each other or on anything else in this stage** — start all three in parallel immediately. `[DEVIATED - see DEVIATIONS.md #DEV-037]` Exception: Track D's D7 (`EntityAlias`) specifically depends on Track C6/`V14` — an `@Entity` mapped to a nonexistent table breaks `ddl-auto: validate` for the whole module, not just tests touching that table. D1–D6 remain fully independent.
- **B depends on A** (the pipeline must exist) **and on Stages 2–3 being done** (real corpus text to run against). B cannot start until both are true.
- **Within Track C**: V9 (sources), V13 (myths), V14 (aliases) are hand-curated and have no dependency on B — draft them in parallel with A/B. V10/V11/V12 need B's reviewed output before they can be finalized (though V10/V11 need only the lighter spot-check, not the full review gate V12 requires).
- **F depends on D** (needs `SourceRepository` + `EntityRecordRepository`).
- **G depends on C + D** — each repository test only needs its own repository and the corresponding seed data, so the three tests can be parallelized across sessions once both land.
- **H is sequential and last.**

---

## Track A — Extraction pipeline build

_Directory:_ `ingestion/extraction/`. No dependency on ingested data yet — this is pure code, testable against inline fixtures.

- [x] **A1** `schema.py` — Pydantic models scoped to this project's actual schema (not the broader entity/claim/conflict/place/event shape considered and rejected in ADR-004):
  ```python
  class ExtractedEntity(BaseModel):
      name: str
      type: str            # must match entities.type CHECK values
      generation: int | None = None
      domain: str | None = None

  class ExtractedRelationship(BaseModel):
      from_name: str
      relation: str         # parent_of, married_to, killed_by
      to_name: str
      is_contested: bool = False
      passage_ref: str | None = None   # set mechanically from the A4 segment, never by the LLM (DEV-021)

  class ExtractedVariantClaim(BaseModel):
      subject_name: str
      claim_type: str
      claim_value: str
      passage_ref: str | None = None   # set mechanically from the A4 segment, never by the LLM (DEV-021)

  class ExtractedFacts(BaseModel):
      entities: list[ExtractedEntity] = []
      relationships: list[ExtractedRelationship] = []
      variant_claims: list[ExtractedVariantClaim] = []
  ```
> ⚠️ Amended by ADR-007 (`[DEVIATED - see DEVIATIONS.md DEV-014]`). A1's `ExtractedVariantClaim.claim_type` stays free-text `str` — the extractor is **hinted** with known canonical types, not restricted to them. `ExtractedRelationship.is_contested` may remain as a soft signal but **no longer gates storage**: A5 stores every attributed claim regardless. See A5/A6 and the new alias-map item below.
>
> ⚠️ Amended by DEV-021: both models carry `passage_ref`, filled in by the A7 runner from the A4 segment each claim was extracted from — **mechanical provenance, not an LLM output field** (exclude it from the extraction prompt/schema shown to the model, stamp it after parsing). It flows through the candidate JSONs into V11/V12 (`variant_claims.passage_ref`, `relationships.passage_ref` — columns exist since `V8_1`), and B5's per-row review reads it directly off each candidate.
>
> ⚠️ Amended by DEV-033 `[DEVIATED - see DEVIATIONS.md #DEV-033]`: a candidate's `passage_ref` may be a **containment range** (e.g. `"9.114-9.140"`, full prefix on both ends), not only a point — whenever its A4 segment groups multiple marker intervals. Same notation as `narrative_chunks.passage_ref`; see the ADR-014 amendments. Note this is a genuinely *wider* range than a single `narrative_chunks` row now produces (DEV-034 made the chunker paragraph-aligned — one row per marker interval) — A4's grouping is a deliberate, different choice (keep a whole genealogical statement together), not a precedent for chunk-level range width.

- [x] **A2** `known_aliases.json` — Roman/cross-cultural equivalents (Zeus/Jupiter, Heracles/Hercules, Odysseus/Ulysses, etc.); this doubles as a reference list for hand-curated `V14`
- [x] **A2b** `normalize(claim_type)` helper reading the **`claim_type_aliases` DB table** (created + seeded by `V8_2` — replaces the originally planned `claim_type_aliases.json`, which `core-api` could never have read; DEV-022). Canonical → surface-variant rows (e.g. `death` ← `death_manner`, `manner_of_death`, `how he died`, `slaying`, `slain by`, `killed by` — already seeded). Its canonicals are the **same namespace** the relation→claim_type map (A6) targets — `parentage`, `marriage`, `death` — so a disagreement split between a typed relationship and free-text prose still groups under one key. Used by `conflict_detector.py` (A6) offline **and**, at query time, by `ConflictLookup` (Stage 7), both reading the same table — the single shared source of truth. New surface variants discovered during extraction are appended via a follow-up migration, never hardcoded `[DEVIATED - see DEVIATIONS.md DEV-014, DEV-020, DEV-022]`
- [x] **A3** `entity_resolver.py` — in-memory dedup: exact name match → `known_aliases.json` lookup → `rapidfuzz` fuzzy match (threshold ~88) against the running candidate name list; log fuzzy merges for a second look during spot-check
- [x] **A4** Passage segmentation helper — reuse the existing `passage_ref_extractor` scan from `ingestion/loader/` (built in Stage 2), but group whole sections between consecutive ref boundaries (not the 1500-char RAG window) so a full genealogical statement isn't split mid-claim. This can live in `extraction/` as a thin wrapper over the Stage 2 extractor functions — do not duplicate the regex patterns. `[DEVIATED - see DEVIATIONS.md #DEV-033]` The wrapper must also **carry each segment's end boundary** and reuse `ingestion/loader/ref_ranges.py` (never re-derive range logic): stamp `format_range(segment_start_ref, range_end(refs, segment_end_offset))` as the segment's `passage_ref`, so a segment grouping multiple marker intervals gets an honest range and single-interval segments stay points. `[DEVIATED - see DEVIATIONS.md #DEV-036]` "Whole sections" turned out to mean marker-interval accumulation up to a size cap, not blank-line paragraphs — `text_cleaner.clean()` collapses blank-line runs before A4 ever sees the text, so no blank-line signal survives to group on.
- [x] **A5** `claim_extractor.py` — `instructor`-wrapped **Anthropic** client (`instructor.from_anthropic(Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]))`, model `EXTRACTION_MODEL=claude-opus-4-8` per ADR-008), `tenacity` retry matching the `embed_batch` pattern from Stage 2's `embedding_pipeline.py`, per-source `SOURCE_HINTS` dict (e.g. Apollodorus: *"flag 'others say'/'some say' as is_contested=true"*). Extract **all** attributed claims of the observed types, **not only inline-contested ones** — `is_contested` is a soft hint, not a storage gate (ADR-007 §1) `[DEVIATED - see DEVIATIONS.md DEV-014, DEV-015]`
- [x] **A6** `conflict_detector.py` — **single GROUP-BY pass over ALL candidate claims** (not relationships only): key on `(subject, normalize(claim_type))` with `HAVING count(DISTINCT source_id) >= 2` → emit a `variant_claims` candidate. Map relationship candidates into the same space (`parent_of → parentage`, `married_to → marriage`, `killed_by → death`) — each mapping is a row in the `claim_type_aliases` table (A2b/V8_2), so free-text death prose and `killed_by` edges group under one `death` key rather than splitting `slaying` vs `death_manner` — so structured relationships and free-form claims flow through one detector, even when no source's text used explicit disagreement phrasing (ADR-007 §1) `[DEVIATED - see DEVIATIONS.md DEV-014, DEV-020, DEV-022]`
- [x] **A7** `run_extraction.py` — entry point: iterate ingested sources → segment (A4) → extract (A5), stamping each relationship/variant-claim candidate's `passage_ref` from its segment (DEV-021) → resolve (A3) → run conflict detector (A6) → write `extraction/output/entities_candidates.json`, `relationships_candidates.json`, `variant_claims_candidates.json` (latter always `trust_tier=3`)
- [x] **A8** Add `instructor>=1.3.0`, `rapidfuzz>=3.0.0`, and `anthropic` (ADR-008 — extraction is Claude Opus 4.8 via `instructor.from_anthropic`) to `ingestion/requirements.txt` `[DEVIATED - see DEVIATIONS.md DEV-015]`

---

## Track B — Run extraction + human review

_Depends on:_ Track A + Stages 2–3 (ingested `narrative_chunks` for all 6 sources).

- [ ] **B1** `ingestion/notebooks/01_test_extraction.ipynb` — tune the prompt against Apollodorus (the spine source, most systematic) on 5–10 segments before running the full corpus; this is the highest-value 30 minutes in this stage — if extraction quality is good on Apollodorus, the rest follows
- [ ] **B2** Run `run_extraction.py` against all 6 ingested sources
- [ ] **B3** Spot-check `entities_candidates.json` — skim for wrong `type` values or obvious duplicate names the resolver missed; no per-row sign-off needed
- [ ] **B4** Spot-check `relationships_candidates.json` — same lighter pass; sanity-check a handful of `parent_of`/`married_to`/`killed_by` rows against known mythology
- [ ] **B5** `ingestion/notebooks/02_verify_conflicts.ipynb` — review every row in `variant_claims_candidates.json` against its source `passage_ref`; promote approved rows by setting `trust_tier=1`
- [ ] **B6** Floor conflicts — the runtime seed **must** contain all three: Aphrodite parentage (Hesiod vs Homer), Io parentage (Inachus vs Piren per Apollodorus), Achilles death variants. **Source is extraction-preferred:** where `variant_claims_candidates.json` already covers one (post-review), promote it as-is; **hand-add only the ones extraction missed.** The *presence* of all three in the seed is non-negotiable regardless of pipeline output — but this is a guarantee about the seeded data, **not** a claim that extraction found them; record per floor conflict whether it was extracted or hand-added (feeds B7). Hand-adding does not excuse the `claim_type` unification rule: insert each floor conflict's two versions under **one** normalized canonical `claim_type` (per DEV-018) so they group and the exact-match `ConflictLookup` returns both. For Achilles death, that canonical is **`death`** — both the `killed_by`-derived edge and any free-text manner-of-death claim normalize to `death` via `claim_type_aliases.json` (the `slaying` vs `death_manner` split is resolved in DEV-020); do not seed one version under `slaying` `[DEVIATED - see DEVIATIONS.md DEV-019, DEV-020]`
- [ ] **B7** Extraction-quality metric (**diagnostic, non-blocking**): after B2 and **before** any B6 hand-add, measure against the raw `variant_claims_candidates.json` how many of the **cross-source** floor conflicts the pipeline detected *unaided* — each as a group of ≥2 distinct `source_id` under one normalized `claim_type`. **Only Aphrodite and Achilles are measurable this way, so the metric is `N/2`, not `N/3`.** Io is **structurally excluded**: its two variants (Inachus vs Piren) are both attributed to Apollodorus — a single `source_id` (`IMPLEMENTATION_PLAN.md §7` Q14; ADR-004: one Apollodorus passage names both), so the `count(DISTINCT source_id) >= 2` detector can never emit it. Io is therefore **always hand-added (B6) and never counted as a pipeline miss** — its absence from the candidates is expected, not a quality signal. Log `floor conflicts detected: N/2` (Aphrodite, Achilles) with any miss named. This measures **extraction quality**, kept separate from the runtime **surfacing** guarantee (B6): a miss here is a pipeline signal to investigate, never a build failure. (Runtime surfacing of Io is unaffected — `ConflictLookup` fetches by subject + `claim_type` regardless of source count, and Q14 scoring already special-cases its single author per `IMPLEMENTATION_PLAN.md §7`.) Lives as a cell in `02_verify_conflicts.ipynb` (or a small `ingestion/extraction/` pytest over a fixture) — it is Python/offline, **not** a core-api Testcontainers test. The death-key fragmentation that would have made Achilles a false miss is resolved by DEV-020 (`killed_by` and free-text death claims both normalize to `death`), so a genuine `N/2` here reflects extraction coverage, not a key-mapping artifact `[DEVIATED - see DEVIATIONS.md DEV-019, DEV-020]`

---

## Track C — Flyway seed migrations (V9–V14)

_Directory:_ `core-api/src/main/resources/db/migration/`. V9/V13/V14 are hand-curated and independent of Track B; V10–V12 need Track B's (reviewed) output.

> Note: ADR-006's deferred `V15__add_embedding_model_tracking.sql` (see Stage 3 in `TODO.md`) may need to land before or alongside this track — if it was applied ahead of V9–V14 (out-of-order or renumbered), verify Flyway validation still passes; if it wasn't, it lands after V14 with a backfill of already-ingested rows.
> **Resolved by DEV-028 (see DEVIATIONS.md):** it landed early, renumbered as `V8_4__switch_embedding_to_3large_3072.sql` (bundled with the ADR-013 embedding upgrade), which sorts before V9 — no ordering issue and no backfill remain; this track's V9–V14 apply normally after it.

- [ ] **C1** `V9__seed_sources.sql` — hand-curated, unaffected by ADR-004. 6 rows, `ON CONFLICT DO NOTHING`.
  `[DEVIATED - see DEVIATIONS.md #DEV-030]` — these exact 6 rows are already hand-inserted in the
  running dev DB (Stage 3 Gotcha #1 / Track E, ahead of this migration being written), so `V9`'s
  `ON CONFLICT DO NOTHING` must reproduce them **verbatim**, stance column included, or it silently
  no-ops against different values:
  - `apollodorus-bibliotheca` / Apollodorus / Bibliotheca / Frazer / mythographic-handbook / 1921 / spine
  - `hesiod-theogony` / Hesiod / Theogony / Evelyn-White / cosmological / 1914 / spine
  - `hesiod-homeric-hymns` / **Anonymous ("Homeric")** / Homeric Hymns / Evelyn-White / hymnic / 1914 / primary
    `[DEVIATED - see DEVIATIONS.md DEV-018]` — the plan's V9 row (`IMPLEMENTATION_PLAN.md §3`) sets
    `author='Hesiod'`; the Hymns are conventionally anonymous (Evelyn-White's *volume* bundles them with
    Hesiod, but `author` is the work's author, not the translator's volume). Slug kept as the plan specifies
    so it still matches `SourceConfig.source_id`; only `author` is corrected.
  - `homer-iliad` / Homer / Iliad / Murray / poetic-myth / 1924 / spine
    `[DEVIATED - see DEVIATIONS.md #DEV-029]` — the plan's V9 row has Murray's Iliad/Odyssey years
    swapped; the real corpus file is `homer_iliad_murray1924.txt` (Loeb Iliad is 1924).
  - `homer-odyssey` / Homer / Odyssey / Murray / poetic-myth / 1919 / primary
    `[DEVIATED - see DEVIATIONS.md #DEV-029]` — real corpus file is `homer_odyssey_murray1919.txt`
    (Loeb Odyssey is 1919).
  - `ovid-metamorphoses` / Ovid / Metamorphoses / Brookes More / poetic-myth / 1922 / selective
    `[DEVIATED - see DEVIATIONS.md #DEV-029]` — the plan's placeholder `translation='PD'`/
    `year_published=null` is replaced by the real translator: `ovid_metamorphoses_more1922.txt`.
  - Verify each `id` slug matches `SourceConfig.source_id` in `source_registry.py` (already fixed in Stage 2)
- [ ] **C2** `V10__seed_entities.sql` — depends on B3. Merge spot-checked `entities_candidates.json` rows (~60–100: primordials, titans, olympians, heroes, monsters); set `type`/`generation`/`domain` per the `entities.type` CHECK values
- [ ] **C3** `V11__seed_relationships.sql` — depends on B4 + C2 (needs C2's final entity name list for the `SELECT id FROM entities WHERE name='...'` subqueries). Merge spot-checked `relationships_candidates.json` rows; every row sets `source_id` and carries the candidate's `passage_ref` (DEV-021). For a **contested** relationship, keep exactly **one canonical edge** (default: the spine source, `sources.role='spine'`) — do **not** store competing edges, which would branch every `WITH RECURSIVE` traversal. The disagreement is recorded in V12 instead (ADR-007 §6). Stored `passage_ref` provenance may be **range-shaped** (e.g. `"9.114-9.140"`) per DEV-033 — the column is TEXT, no change needed, but don't assume point form when reviewing/rendering `[DEVIATED - see DEVIATIONS.md DEV-014, #DEV-033]`
- [ ] **C4** `V12__seed_variant_claims.sql` — **most critical file in this stage** — depends on B5+B6 + C2. Insert only rows promoted to `trust_tier=1` during review; use the `INSERT ... SELECT id FROM entities WHERE name='...' / SELECT id FROM sources WHERE id='...' ... ON CONFLICT DO NOTHING` pattern from `IMPLEMENTATION_PLAN.md §3`. Record here the contradiction for each contested relationship whose canonical edge C3 fixed (so all versions still surface via enrichment). **Write each row's `claim_type` as the normalized canonical value** (apply the `claim_type_aliases` table's `normalize()` (A2b/V8_2, DEV-022) to the candidate's surface label before insert) so the two rows of a conflict share one `claim_type` and Stage 7's exact-match `ConflictLookup` (`claim_type = normalize(probeClaimType)`) returns both — leaving surface variants in place would make the lookup return one row and silently drop the conflict (ADR-007 §5). Every row also carries its candidate's `passage_ref` (column exists since `V8_1`; DEV-021) so surfaced conflicts cite at passage level like RAG answers do — and that provenance may be **range-shaped** (e.g. `"9.114-9.140"`) per DEV-033, matching `narrative_chunks` notation. Note: `V7__create_variant_claims.sql` already declares `claim_type TEXT` with **no CHECK** — the open-`claim_type` requirement needs no migration change `[DEVIATED - see DEVIATIONS.md DEV-014, DEV-018, DEV-021, DEV-022, #DEV-033]`
- [ ] **C5** `V13__seed_myths.sql` — hand-curated, unaffected. Depends on C2 (entity names). At least: Judgment of Paris / wedding of Peleus and Thetis, Abduction of Persephone, Perseus and Medusa, Polyphemus episode, Arachne's transformation; `myth_participants` rows with a `role` per participant. Remember: no `source_id` FK on `myths` — don't attribute it directly
- [ ] **C6** `V14__create_entity_aliases.sql` — hand-curated, unaffected. Depends on C2 (entity names). Schema: `CREATE TABLE entity_aliases (id SERIAL PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id), alias TEXT NOT NULL, UNIQUE(alias))`. Seed ~20 aliases — may reuse `A2`'s `known_aliases.json` as a source list (Venus→Aphrodite, Hercules→Heracles, Odysseus→Ulysses, Cupid→Eros, Neptune→Poseidon, Jupiter/Jove→Zeus, Juno→Hera, Minerva→Athena, Mars→Ares, Vulcan→Hephaestus, Mercury→Hermes, Diana→Artemis, Ceres→Demeter, Pluto/Dis→Hades, Vesta→Hestia, Bacchus→Dionysus, plus a couple Greek-spelling variants for the trigram fallback)
- [ ] **C-verify** Update `FlywayMigrationTest.kt`: replace `` `entity_aliases table does not exist yet` `` (now false) with a positive assertion — table exists and `columns("entity_aliases")` contains `entity_id`, `alias`

---

## Track D — JPA entities + repositories

_Directory:_ `core-api/src/main/kotlin/com/blamezeus/coreapi/domain/entity/` and `.../repository/`. Independent of A/B/C.

> **Naming note:** name the JPA class `EntityRecord` (table `"entities"`), not `Entity` — avoids colliding with `jakarta.persistence.Entity`. Use this name consistently through Stage 7 (`ConflictLookup`, `EntityExtractor`/`ConflictProbe`).

- [x] **D1** `Source.kt` `@Entity` (table `sources`) + `SourceRepository : JpaRepository<Source, String>` (String PK)
- [x] **D2** `EntityRecord.kt` `@Entity` (table `entities`) + `EntityRecordRepository : JpaRepository<EntityRecord, Int>` with `findByNameIgnoreCase(name: String): EntityRecord?`
- [x] **D3** `Relationship.kt` `@Entity` (table `relationships`) + `RelationshipRepository : JpaRepository<Relationship, Int>` — prefer plain FK columns over `@ManyToOne` to avoid N+1 surprises in simple read paths
- [x] **D4** `Myth.kt` + `MythParticipant.kt` `@Entity` classes (`MythParticipant` needs `@EmbeddedId`/`@IdClass` for its composite PK) + `MythRepository`, `MythParticipantRepository`
- [x] **D5** `VariantClaim.kt` `@Entity` (table `variant_claims`) + `VariantClaimRepository` with `findBySubjectEntityIdAndClaimType(...)` and a `findByEntityNameIgnoreCase` join-query. These now serve Stage 7's shared **`ConflictLookup`** (which the enrichment step calls), not a `ConflictQueryHandler` — that handler is deleted by ADR-007 `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [x] **D6** `NarrativeChunk.kt` `@Entity` (table `narrative_chunks`) + `NarrativeChunkRepository` — `embedding` unmapped/`@Transient`-adjacent; LangChain4j's `PgVectorEmbeddingStore` owns writes here from Stage 6 onward (superseded by DEV-025: a custom `ContentRetriever` reads, the Python pipeline writes). The `embedding_model` column added by V8_4 (DEV-028) may be mapped read-only or left unmapped — the Python pipeline is its only writer; with `ddl-auto: validate`, don't omit columns Hibernate would flag
- [ ] **D7** `EntityAlias.kt` `@Entity` (table `entity_aliases`) + `EntityAliasRepository` with `findByAliasIgnoreCase(alias: String): EntityAlias?` `[DEVIATED - see DEVIATIONS.md #DEV-037]` **Blocked on Track C6/`V14`, not independent as the parallelization guide states below** — `entity_aliases` doesn't exist until `V14` lands, and `ddl-auto: validate` fails the *entire* Spring context (every test in the module, not just ones touching this table) the moment an `@Entity` is mapped to a missing table. Confirmed empirically. Do not add this file until `V14` exists.

---

## Track E — DTOs

_Directory:_ `core-api/src/main/kotlin/com/blamezeus/coreapi/domain/dto/`. Fully independent — shapes fixed by `IMPLEMENTATION_PLAN.md §5`/`§7`.

- [x] **E1** `QueryRequest.kt` — `data class QueryRequest(val question: String)`
- [x] **E2** `Citation.kt` — `data class Citation(val author: String, val work: String, val passageRef: String, val stance: String? = null)`
- [x] **E3** `ConflictEntry.kt` — `data class ConflictEntry(val claimValue: String, val sourceAuthor: String, val sourceWork: String)`
- [x] **E4** `RagResponse.kt` — `data class RagResponse(val answer: String, val citations: List<Citation>)`
- [x] **E5** `QueryResponse.kt` — `data class QueryResponse(val answer: String, val routeDecision: RouteDecision?, val citations: List<Citation>, val conflicts: List<ConflictEntry>, val sqlGenerated: String?, val serviceError: Boolean = false)` — either stub a minimal `RouteDecision` enum now so this compiles (`SQL`/`RAG`/`MIXED`, **no `CONFLICT`** per ADR-007), or type `routeDecision` as `String?` and tighten in Stage 5 (log the choice in `DEVIATIONS.md` if the latter). Stage 7 enrichment writes only the `conflicts` field, never `answer` `[DEVIATED - see DEVIATIONS.md DEV-014]`. Took the first option: stubbed `routing/RouteDecision.kt` (`SQL`/`RAG`/`MIXED`, no `CONFLICT`) now — the enum values are already settled by ADR-007, so there was nothing provisional to defer to Stage 5.

---

## Track F — REST read endpoints

_Depends on:_ D1, D2. _Directory:_ `core-api/src/main/kotlin/com/blamezeus/coreapi/controller/`

- [ ] **F1** `QueryController.kt` skeleton (`@RestController`, `@RequestMapping("/api/v1")`) — `POST /api/v1/query` and `GET /api/v1/conflicts/{entityName}` are added in later stages; stub only
- [ ] **F2** `GET /api/v1/entities` — `entityRecordRepository.findAll()`
- [ ] **F3** `GET /api/v1/sources` — `sourceRepository.findAll()`

---

## Track G — Repository tests (Testcontainers)

_Depends on:_ Track C (seed data) + matching Track D repository. Reuse `AbstractContainerTest`.

- [ ] **G1** `SourceRepositoryTest.kt` — `findAll()` returns exactly 6 rows; spot-check one row's `year_published`/`role`
- [ ] **G2** `EntityRecordRepositoryTest.kt` — `findAll()` returns ≥60 rows; `findByNameIgnoreCase("aphrodite")` returns a non-null row named `"Aphrodite"`
- [ ] **G3** `VariantClaimRepositoryTest.kt` — `findByEntityNameIgnoreCase("Aphrodite")` returns ≥2 rows with distinct `claimValue`; assert both known `sourceId`s (`hesiod-theogony`, `homer-iliad`) appear
- [ ] **G4** (optional) `EntityAliasRepositoryTest.kt` — `findByAliasIgnoreCase("Venus")` resolves to the `EntityRecord` named `"Aphrodite"`
- [ ] **G5** (optional) `MythParticipantRepositoryTest.kt` — at least one seeded myth has ≥2 participants

---

## Track H — Verification (sequential, run last)

- [ ] **H1** `./gradlew :core-api:test --tests "*.FlywayMigrationTest"` — updated `entity_aliases` assertion passes
- [ ] **H2** `./gradlew :core-api:test --tests "*RepositoryTest"` — all Track G tests pass
- [ ] **H3** Start `core-api` locally (DB running): Flyway log shows V9–V14 applied with no `ON CONFLICT` errors
- [ ] **H4** `psql -U zeus -d blamezeus -c "SELECT count(*) FROM entities"` — ≥60
- [ ] **H5** `curl localhost:8080/api/v1/entities | jq length` — ≥60
- [ ] **H6** `curl localhost:8080/api/v1/sources | jq length` — exactly 6
- [ ] **H7** Spot-check `variant_claims` in the DB: `SELECT * FROM variant_claims vc JOIN entities e ON vc.subject_entity_id = e.id WHERE e.name = 'Aphrodite'` returns ≥2 rows with distinct `claim_value` and `trust_tier=1`
