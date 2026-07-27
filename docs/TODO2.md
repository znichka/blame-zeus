# blame-zeus: Project TODO — Phase 2 (Data-Quality & Evaluation Program)

Phase-2 stages track `IMPLEMENTATION_PLAN_PHASE2.md`. Each stage's **"Done when"** is the gate for
starting the next. This roadmap implements **ADR-017** (direction), **ADR-018** (evaluation
harness), **ADR-019** (relation canonicalization), and **ADR-020** (joint parentage — the
co-parent carve-out narrowing ADR-007 §6, landing in P3), and is tracked under `TODO.md` →
*Post-MVP Enhancements* (named by ADR, not a numbered `IMPLEMENTATION_PLAN.md §9` stage, so §9
history stays untouched).

> **Operating model (ADR-017):** measurement-first, evaluation-gated. Build the harness and a
> committed baseline **before** touching data; gate every change on a **3-run** eval comparison
> (only *stable* PASS→FAIL regressions block); commit eval result artifacts as the quality audit
> trail. Priority: fix existing SQL/relational data (P3) **before** conflict depth (P4) or new data
> types (P5).

> Per-stage detailed checklists (`TODO-phase2-stageN.md`) are created **during** implementation of
> each stage, following the existing `TODO-stageN.md` pattern — this file is the outline.

Before starting any stage, re-read `DEVIATIONS.md` (per the CLAUDE.md deviation protocol). Relevant
carry-overs: **DEV-059** records this program's documentation-first landing; **DEV-054** (Q9/Q12
`WITH RECURSIVE`, fixed in P2) and **DEV-053** (Q13 formatting, expected already fixed by
DEV-056/DEV-057 — **confirmed** at baseline, fixed further only on evidence) are the two known
runtime defects addressed in P2;
**DEV-041** (schema-vocabulary → SQL quality) motivates ADR-019; **DEV-055** (tests mock
`@AiService`) bounds where the harness may live; **DEV-088** (ADR-020's discriminator replaced
after measurement, scope widened to the dropped rival parents — landed as DEV-090) was P3's largest
open data change, see `docs/DATA-GAPS.md` GAP-001.

> **2026-07-27 reconciliation audit** `[DEVIATED - see DEVIATIONS.md #DEV-093]` — a sweep of
> `DEVIATIONS.md` DEV-001…DEV-092 against these TODO files found several documented-but-unfixed
> items with no home in any plan. They now have one: **Stage P3b** (new, below) owns
> `docs/DATA-GAPS.md` **GAP-003** (the Q6/Q7/Q8 DATA floor breach, mis-routed to P3 by P1's triage
> and never listed there) and **GAP-002** (DEV-074's 367 missing entities); **P4** owns DEV-038 and
> DEV-049 as prerequisites; **P5** owns DEV-066. Everything else deferred in `DEVIATIONS.md` was
> confirmed to have a real destination already — see DEV-093 for the full inventory, including the
> items that are open **by design** (A1's fuzzy-duplicate long-tail, A6's promotion backlog).

---

## Stage P1 — Evaluation harness + baseline  (ADR-018; ADR-010 accepted here)
**Done when:** `python -m runner --runs 3 --label baseline` completes against a running, seeded
server and writes a **committed** `evaluation/results/<UTC>__<sha>__baseline/`; every failing gold
question is triaged in `report.md` as pipeline-bug / data-gap / corpus-gap / eval-bug.
**Landed and committed 2026-07-22** (DEV-060 the harness, DEV-061/062/063 the three eval-bug fixes)
— baseline `evaluation/results/2026-07-22T19-02-10Z__de6de91__baseline/`, 10/16 (62%).

> Boxes below were ticked 2026-07-27 from `TODO-phase2-stage-p1.md`, whose Definition-of-done mirror
> was already fully complete; this outline file had simply never been reconciled
> `[DEVIATED - see DEVIATIONS.md #DEV-093]`.

- [x] `evaluation/runner/` package: `__main__.py` (CLI: `--runs`, `--label`, `--base-url`,
      `--questions`, `--ids`, `--debug`), `scoring.py` (§7 rubric verbatim + ADR-010 per-category
      floors), `report.py` (results dir: `raw_responses.json` / `scores.json` / `report.md`),
      `compare.py` (baseline vs candidate → `diff.md`) — DEV-060
- [x] `evaluation/eval-config.json` — per-category floors, overall ≥75% target, base-url default
- [x] 3-run stable / flaky / stable-fail classification; `serviceError:true` scored as fail (no
      retry); transport errors retry once
- [x] Q10 `min_row_count` re-executes generated SQL via read-only `zeus_app` psycopg2 + statement timeout
- [x] Implement `refusal_criteria` (phrase-list + empty-`citations[]`) **now**, so P4's REFUSAL
      Q16/Q17 need no scorer change — scorer half done; `SOURCE_SILENCE_PHRASES` extendable in P4
- [x] Flip **ADR-010** → Accepted (done at documentation time); defer authoring its ~8 new questions
      to P4 (don't change yardstick and data at once)
- [x] Commit baseline results dir; triage every failure in `report.md`
- [x] Triage decides the **Q14 route-label** question (RAG-via-empty-SQL vs SQL-returns-rows, DEV-054);
      record as an eval-bug fix if the gold label changes — decided **SQL**, gold relabeled (DEV-063)

> ⚠️ **P1's H3 triage routed Q6/Q7/Q8 to "→ P3" and P3 never listed them.** See **Stage P3b** below
> and `docs/DATA-GAPS.md` GAP-003. One half of that triage is also stale: Q7's `Zeus→Heracles` edge
> was restored by DEV-090.

→ Detailed checklist: `TODO-phase2-stage-p1.md` (created at implementation)

---

## Stage P2 — Debuggability + known-defect fixes  (DEV-053, DEV-054)
**Done when:** the A3 cycle-detection check reports the `parent_of` graph clean (or lists + fixes the
reversed edges); a `debug:true` request returns a populated `DebugInfo`; Q9/Q12 no longer
`serviceError`; Q13 **confirmed passing** at baseline; `scripts/reseed-local.sh` re-applies V10–V14
without dropping embeddings; `:core-api:test` green; eval `--runs 3 --debug` vs baseline shows those
fixes and **zero stable regressions**.

- [x] `logging.level.com.blamezeus.coreapi: DEBUG` in `application.yml` (or `debug` profile)
- [x] `QueryRequest.debug` + `QueryResponse.debug: DebugInfo?` (`@JsonInclude(NON_NULL)`) via a
      **`ThreadLocal` singleton `DebugCapture`** (plain bean w/ constructor default, **not**
      `@Scope("request")` — keeps handler/retriever unit tests constructible), appended to by
      `SqlQueryHandler`, **`MixedQueryHandler`**, the chunk retriever, and `QueryService` (probe
      subject/claimType, claim count, first-attempt SQL, capped SQL rows, retrieved chunk refs,
      fallback/composer flags, draft answer) — DEV-064
- [x] `scripts/reseed-local.sh` — **`DROP TABLE entity_aliases`** (V14 is a bare `CREATE TABLE`) +
      `TRUNCATE` the other V10–V13 tables `CASCADE` → `DELETE FROM flyway_schema_history WHERE version
      IN ('10'…'16')` (**must include V15/V16** or Flyway skips the re-apply) → restart; **never**
      `down -v`; guard against a shared env (Flyway checksum trap) — DEV-065
- [x] Q13: **verify passing at baseline, do not re-implement** — DEV-056 composer + DEV-057's
      already-mandated `r.passage_ref AS passage_ref` are expected to cover it; only tweak if the
      baseline still shows the dump/empty passageRef. Confirmed stable-pass 3/3 at P1 baseline and
      reconfirmed stable-pass 3/3 in both P2 re-eval runs (I4, I5) — never touched.
- [x] Q9/Q12 = **Stage 8.5 gap (ii) — root cause first, code fix only if still needed** (gate each
      rung on the previous rung's eval):
  - [x] **Rung 0 (always):** cycle-detection check over `relationships` **authored now in P2** (→
        audit A3), run **before any SQL/prompt change**; fix reversed edges in candidate JSON →
        reseed → re-run eval. If Q9/Q12 pass over the clean DAG, **stop — ship no code.**
        Checker built + live-verified (DEV-066, found 4 live cycles). The one genuine reversed edge
        (`Laertes`⇄`Odysseus`, 17 wrong-direction candidate rows) fixed, regenerated, reseeded —
        DEV-067; `cycle_check --db` now shows 3 (entity-conflation, flagged for P3 — DEV-068, not
        reversed edges, out of Rung 0's scope). **I4 re-measure: Q9/Q12 still stable-fail** (evidence
        gate for Rung 1 satisfied).
  - [x] **Rung 1 (only if clean DAG still fails/flakes):** LOUD bounded `WITH RECURSIVE` few-shot
        (depth cap + `visited`-id array) in `TextToSqlAgent`, breadcrumb via `sqlRows` — DEV-069.
        **Live 3-run re-eval: Q12 → stable-pass 3/3 (fully fixed). Q9's `serviceError` eliminated**
        (route/author pass every run) **but content point still missed — confirmed a separate data
        gap** (`Sky`/`Ouranos` has no `parent_of Cronus` edge; `Chaos` has no edge to `Earth` at all),
        **not a Rung 2/3 trigger** — flagged for P3 instead (see the Stage P3 backlog line below).
        Zero stable regressions; Q13 reconfirmed stable-pass 3/3.
  - [x] **Rung 2/3 — not shipped.** Evidence doesn't support them: Q9's remaining gap is a missing
        edge (data), not a generation/execution failure, so Rung 2's gate ("malformed-CTE, not data
        cycle") isn't met, and Rung 3 is gated on Rungs 1–2 still leaving a stable-fail on the
        service-error dimension, which is no longer the case. **Staircase stops at Rung 1, per plan.**
- [x] Decision recorded: **skip `query_history`** for the PoC (eval artifacts + `DebugInfo` cover it)
      — DEV-064; revisit noted on the `TODO.md` P5 line
- [x] TDD: retry path, cycle-detection check (pure Python over a fixture graph), and DebugCapture
      unit-tested, `@AiService` mocked; `:core-api:test` green — cycle-detection check (9 tests) and
      DebugCapture done; Rung 2's retry path evaluated on evidence and correctly **not** shipped (its
      gate wasn't met — see the Rung 2/3 line above), so there is no retry-path code to test

→ Detailed checklist: `TODO-phase2-stage-p2.md` (created at implementation)

---

## Stage P3 — Data audit & error fixing  (ADR-019 + ADR-020; priority per ADR-017)
**Done when:** `python -m audit` is clean (or every finding explicitly waived with a note); the 29
(grown to 48 live, DEV-084) fuzzy-duplicate pairs and 203 `relationships_flagged_for_review.json`
rows are triaged; `relation_aliases` is live and applied by seedgen; **ADR-020's joint-parentage
carve-out has landed through a Track I pass (DEV-088), with the co-parent count re-measured against
the real `canonical_edge.py` change** and A3 clean-or-explicitly-waived; eval (3-run) shows
DATA/MIXED ≥ baseline and zero stable regressions. **Landed and committed 2026-07-26** (DEV-090 the
discriminator, DEV-091 the Chaos decision, DEV-092 the Sky/Heaven/Uranus merge — `b26e69b`,
`201eac8`, `5eed421`, `35fb379`) — Track J is fully closed for P3. Overall eval reached 12/16 = 75%,
the P1 target, for the first time. Remaining open items are permanent-by-design: A1's fuzzy-duplicate
long-tail and A6's unowned P4 promotion backlog — neither is expected to ever reach literal zero.

> Boxes below were ticked 2026-07-27 against `TODO-phase2-stage-p3.md`, the granular checklist that
> supersedes this outline; the outline had never been reconciled line-by-line
> `[DEVIATED - see DEVIATIONS.md #DEV-093]`.

- [x] `ingestion/audit/` package (`python -m audit`, read-only): A1 duplicate entities
      (rapidfuzz + transliteration heuristics), A2 candidate-drop accounting, **A3
      direction/integrity — cycle detection (self-loop / 2-cycle / longer) as first-class invariant,
      authored in P2, run every batch** + symmetric duplicates + DEV-040 invariants, A4 relation-label
      taxonomy → initial `relation_aliases` map, A5 alias/participant integrity
  - [x] **Per-row dropped-parent record** (GAP-001 Root cause 3, lands with J4a): a check conforming
        to the Track-A check contract, alongside `drop_accounting.py`, listing every parent value the
        contested collapse discards (child, value, source, passage, whether the subject already has a
        `variant_claims` parentage row). A2 reports contested-collapse as an aggregate only, so no
        reviewer has a per-row list to promote from — this is the artifact for all **612** surviving
        rivals
  - [x] **Backlog from P2 Track I (DEV-068) — all 3 closed by entity splits** (DEV-078 `Aeolus`/
        `Aetolus`, DEV-079 `Cecrops`/`Pandion` — *three* Pandions, not two, DEV-080 `Astyoche`), plus
        2 more found along the way (DEV-077, DEV-082); A3 reached **0 live cycles** at DEV-083. The
        original per-cycle notes are kept below for the source-verification record.
        3 `parent_of` cycles left unfixed in P2 because they're
        entity-conflation, not reversed edges — findings committed at
        `ingestion/audit/findings-db.json`. `Aeolus ⇄ ... ⇄ Endymion` is source-verified
        (`apollodorus_bibliotheca_frazer1921.txt` `[1.7.1]`–`[1.8.1]`): "Aeolus" is conflated with his
        descendant "Aetolus" (Endymion's real son), and "Calydon" with "Calyce" (Aeolus's real
        daughter) — needs an entity split, not a merge. `Cecrops ⇄ Pandion ⇄ Erechtheus` likely fits
        the same pattern (Athenian myth has two Cecrops/two Pandions) but is not yet source-verified.
        `Astyoche ⇄ Tros ⇄ Ilus ⇄ Laomedon` not yet traced at all. Re-run `cycle_check --db` after each
        fix to confirm.
  - [x] **Backlog from P2 Track I5 (DEV-069) — all four items now landed or decided (2026-07-26).**
        Q9 ("Trace Zeus's lineage back to Chaos") **now stable-passes fully** (route ✓, author ✓,
        content ✓ — `Ouranos` and `Chaos` both genuinely present in the composed answer). Full
        write-up: `docs/DATA-GAPS.md` GAP-001; detailed checklist: `TODO-phase2-stage-p3.md` Track J4/J5.
    - [x] **J4a — LANDED 2026-07-26 (DEV-090).** The four-part discriminator (contested-aware ·
          winner-anchored · corroboration-ranked · deny-listed) is live in the seeded DB. Re-measured
          against the real code: **472 children** regain a co-parent — exact match to the simulation
          — max 2 parents per child holds with no exceptions. Landed with zero stable eval
          regressions; a same-day token-budget regression (Q12) was found and fixed in the same pass.
    - [x] **Root cause 3's detection half — landed with J4a.** The per-row dropped-parent record (new
          audit check **A6**) and the same-source `detect_conflicts` condition for `parentage` are
          both live, reaching **145** of the **612** surviving rivals. **The other 467 still stall at
          ADR-004 review — J4a landing did NOT make parentage conflicts user-visible**, exactly as
          predicted; that promotion half (option a′) remains unowned P4 work (see below).
    - [x] **J4b (Chaos cosmogony) — DECIDED 2026-07-26 (DEV-091): deferred to P5b, waived.** No
          `parent_of`-shaped edge between `Chaos` and `Earth`/`Sky` was modeled — confirmed correct
          against the corpus (Hesiod: they arise independently). RAG's retrieved cosmogony context
          answers this in prose instead, without a fabricated edge.
    - [x] **`Sky`/`Heaven`/`Uranus` merge — LANDED 2026-07-26 as Track J5 (DEV-092).** Merged into
          canonical **`Ouranos`** (not `Uranus` — chosen so the literal gold-question keyword is
          achievable; reversed a pre-existing but wrongly-directed `Ouranos→Uranus` alias). Exposed
          and fixed a second row-cap defect (`WITH RECURSIVE` returns one row per citation, not per
          entity, so a flat cap could still drop `Ouranos` behind heavily-cited `Earth`/`Cronus`
          rows) via a new `dedupeByName` fix in both SQL-facing handlers. **Overall eval reached
          12/16 = 75%, the P1 target, for the first time.**
- [x] `relation_aliases(alias PK, canonical, inverse BOOLEAN)` migration (new Phase-2 V-number);
      wire into `seedgen/relationships_gen.py` (apply map at generation; swap from/to on inverse)
      — live as **V17** (DEV-072), regenerated against it in DEV-076
- [x] Triage backlogs: 29 (grown to 48 live) fuzzy-dup pairs (merge + alias, DEV-043 pattern); 203
      flagged relationships — DEV-084 (8 merged / 40 rejected), DEV-085 (202 resolved, 895 rows
      promoted, 1 rejected). A1's residual 39 pairs are permanent long-tail, per the header above
- [x] Fix loop each batch: edit candidate JSON **(or, for J4a, the seedgen/extraction code)** →
      `seedgen --strict` → `reseed-local.sh` → `audit` **clean or explicitly waived with a note** →
      eval `--runs 3` → `compare.py` → commit (candidates + migrations + results) or revert
      — mechanism proven five times (DEV-076/083/089/090/092), all committed
- [x] Confirm `SchemaIntrospector` reflects the shrunk relation vocabulary — 124 → 116 (DEV-076)
- [x] Log DEV entries for any deviation from plan — DEV-070 through DEV-092

> **Not carried by P3, despite P1 triage saying so:** gold **Q6/Q7/Q8** (the DATA floor breach).
> They are `docs/DATA-GAPS.md` **GAP-003** and Stage **P3b** below. Likewise **GAP-002** — A2's 367
> unknown names (DEV-074), reported unchanged through DEV-083 and never given a Track J batch.

→ Detailed checklist: `TODO-phase2-stage-p3.md` (created at implementation)

---

## Stage P3b — DATA floor closure  (GAP-002 + GAP-003; added 2026-07-27, DEV-093)

> ⚠️ Added after P3 closed. `[DEVIATED - see DEVIATIONS.md #DEV-093]` — this stage is not in the
> original Phase-2 outline. It exists because P1's Track H3 triage routed Q6/Q7/Q8 to "→ P3" and P3
> landed without ever listing them, leaving the **only failing evaluation gate** with no owner.
> Sequenced before P4 for the same reason ADR-017 §Decision 4 puts P3 before P4: fix existing
> relational data before adding conflict depth.

**Done when:** a 3-run eval shows **DATA ≥ 3/5 (floor met)** with zero stable regressions and the
results dir committed; every entity added went through source verification, not fabrication; GAP-002
and GAP-003 statuses updated in `docs/DATA-GAPS.md`.

Sizing note: the floor needs 3/5 and Q9/Q10 already pass, so **Track A alone plus either B or C
clears the gate** — the rest is genuine data quality, not gate-chasing. Do not stop at the gate if
Track B/C are half-landed.

> **Tracks A/B/C landed 2026-07-27** `[DEVIATED - see DEVIATIONS.md #DEV-094, #DEV-095]`. DATA reached **100% (5/5)**, overall
> **15/16 (94%)**, zero stable regressions — the stage's own floor-met bar was cleared and then some.
> **GAP-003 is fully resolved.** Only **Track D** (GAP-002's broader 367-name backlog) remains open,
> and it was never gate-blocking — see `docs/DATA-GAPS.md` GAP-002. Results not yet committed.
>
> **Track D's `Arges`/`Steropes` follow-up landed 2026-07-27** `[DEVIATED - see DEVIATIONS.md
> #DEV-098]` — the highest-value data fix of the stage despite touching no gold question:
> **`Ares` had zero relationships in the seeded graph** and now has 33. Overall eval 15/16 → 14/16
> (88%, still above target, all floors met); the one delta is Q8 flipping to flaky on a transient
> malformed-SQL generation, unrelated to the change (runs 1 and 3 both answered correctly).

- [x] **Track A — Q6 entity typing — LANDED 2026-07-27** `[DEVIATED - see DEVIATIONS.md #DEV-094]`. Verified against the corpus
      rather than assuming a bare "Twelve Olympians" list: Hesiod's *Theogony* [869] states plainly
      that Hades "rules over the dead below," structurally apart from "THE OLYMPIAN GODS" section
      [886]; the Homeric Hymn to Aphrodite [7] gives Hestia full standing "in all the temples of the
      gods." Decision: **retyped `Hestia` `other_god` → `olympian`**; **left `Hades` `other_god`**,
      matching the corpus's own placement of him. Corrected Q6's `required_keywords` to drop `Hades`
      (5 names, not 6) as a logged eval-bug, not a silent tune. `V10` regenerated (1-row diff),
      reseeded, `audit --db` unchanged (A1 39, A3 waived-1, A4 116, A5 clean). **Eval:**
      `evaluation/results/2026-07-27T09-13-55Z__e861a17__p3b-track-a-hestia-olympian/` — **DATA
      40% → 60%, floor now PASS, zero floor breaches remain**; Q6 stable-fail → stable-pass;
      `compare.py` confirms zero stable regressions vs the last accepted baseline. Q10's
      `min_row_count: 12` still holds (13 olympian-typed now). Not yet committed.
- [x] **Track B — Q7/Q8 Perseus extraction gap — LANDED 2026-07-27** `[DEVIATED - see DEVIATIONS.md #DEV-095]`. Read Apollodorus
      `[2.4.1]`–`[2.4.4]` directly rather than a full extraction re-run — short and self-contained
      enough to hand-verify, same discipline as DEV-090/DEV-078's entity splits. Added `Zeus
      parent_of Perseus` + `Danae parent_of Perseus` [2.4.1] and `Medusa killed_by Perseus` [2.4.2]
      to `relationships_candidates_cleaned.json` (`killed_by` direction confirmed against ~976
      existing rows of that shape). **Deliberately did not add** `Phineus` (a mortal, not a monster —
      not actually load-bearing for Q8, correcting this outline's earlier speculation) or a named
      "sea monster" (unnamed in this translation — adding one would fabricate data). `V10`/`V11`/`V12`
      regenerated (V11 3127→3130, clean append), reseeded, `audit --db` unchanged (A5 clean — no
      2-parent violation). Q8's route **did** return to `SQL` as predicted.
- [x] **Track C — Q8's `Cetus` keyword is unattested — LANDED 2026-07-27** `[DEVIATED - see DEVIATIONS.md #DEV-095]`. Live-checked
      Q8 post-Track-B: SQL route, answer "Perseus encountered Medusa [1], a monster..." cited to
      `2.4.2` — neither `Gorgon` nor `Cetus` appear (no `subtype` column selected; the sea monster
      has no name to surface). Corrected `required_keywords` to `["Medusa"]` — a logged eval-bug per
      DEV-048/DEV-050, chosen against the real verified answer. **Eval:**
      `evaluation/results/2026-07-27T09-34-14Z__23d7b63__p3b-track-bc-perseus/` — **DATA 60% → 100%**,
      overall **12/16 → 15/16 (94%)**, zero stable regressions (`compare.py` vs the Track-A run), zero
      flaky questions. Only Q11 (MIXED, pre-existing DEV-054 gap, homed to P5b) still fails.
      **GAP-003 fully resolved.** Not yet committed.
- [x] **Track D — GAP-002's 367 unknown names, scoped subset — PARTIALLY LANDED 2026-07-27**
      `[DEVIATED - see DEVIATIONS.md #DEV-096]`. 5 of 7 bucket-1 names added: `Nereus`, `Doris`, `Ceto`, `Styx`, `Thaumas`
      (all source-verified against Apollodorus `[1.2.1-1.2.7]` + Hesiod *Theogony*, `type='other_god'`).
      **`Arges` and `Steropes` deliberately NOT added** — breaking their candidate rows down by
      `passage_ref` (before adding, per this line's own "do not bulk-add" warning) found only 2 of 71
      `Arges` rows and 2 of 14 `Steropes` rows are the genuine Cyclopes; the rest are **extraction
      corruption of `Ares` and `Sterope`** scattered across Homer/Ovid/Apollodorus — a new, larger
      finding than this track anticipated, flagged below rather than fixed here. `<UNKNOWN>` (133
      rows) is an extraction sentinel, not an entity. `Phineus` is no longer load-bearing for Track B
      (DEV-095 found he's a mortal, not a monster) but remains a genuine GAP-002 name. A2's
      unknown-name count: 367 → 362. Long tail (incl. `Phineus`, `Arges`/`Steropes`'s genuine 2 rows
      each) carries to P4.
      > **New lead — WORKED 2026-07-27** `[DEVIATED - see DEVIATIONS.md #DEV-098]`. The corruption
      > was **total, not partial**: `Arges` appears in exactly 2 places in the whole corpus (both the
      > Cyclopes list), the extractor emitted 71 `Arges` rows and **0 `Ares` rows**, and `Ares` — a
      > confirmed `olympian` since V10 — therefore had **zero relationships in the seeded graph**.
      > All 85 rows triaged against their cited passages: 37 renamed to `Ares`, 5 reversed, 25
      > dropped as unsupported (epithets like "scion of Ares", metonymy like "all them hath Ares
      > slain"), 4+4 kept as the genuine Cyclopes, 2 correctly-referenced parentage rows added.
      > `Steropes` was a **five-way `Sterope` split**, not a rename. 8 new entities (`Arges`,
      > `Brontes`, `Steropes` + 5 `Sterope`s). **`Ares`: 0 → 33 seeded relationships.** Eval 14/16
      > (88%), zero stable regressions, all floors met.

- [ ] **Follow-up from DEV-098 — the extraction failure mode has no detector.** The `Ares` erasure
      was invisible to all six audit checks: A1 compares *confirmed* entities to each other, but this
      corruption lives in the *candidate* data where the correct name is simply **absent**. Nothing
      stops the next extraction run from reintroducing it, and other near-miss corruptions of major
      names may still be undetected. Proposed **A7**: *confirmed entity with high corpus frequency
      but zero candidate relationship rows* — would have flagged `Ares` (153 corpus mentions, 0 rows)
      on day one. Carries to P4.
- [ ] **Fix loop** (unchanged from P3): edit candidate JSON → `seedgen --strict` →
      `reseed-local.sh` → `audit` clean-or-waived → `runner --runs 3` → `compare.py` → commit or
      revert. Expect A3 to surface new cycles as the graph grows — that is the loop working.
- [ ] Update GAP-002/GAP-003 status in `docs/DATA-GAPS.md`; log DEV entries per protocol.

→ Detailed checklist: `TODO-phase2-stage-p3b.md` (created at implementation)

---

## Stage P4 — Iterative conflict-depth loop  (gold set grows in lockstep; ADR-010 questions land here)
**Done when:** the loop has run ≥3 batches end-to-end; `variant_claims` covers ≥4 claim_types and
all top-20-prominence subjects; the gold set is ≈25 questions with per-category floors enforced;
overall ≥75% sustained across a 3-run eval. *(The loop continues past this gate.)*

**Prerequisites — two long-standing DEVIATIONS-only hazards that this stage is the first to trip.**
Both were documented as found-but-not-fixed and had no TODO home until 2026-07-27
`[DEVIATED - see DEVIATIONS.md #DEV-093]`. Do these **before** the first promotion batch:

- [ ] **DEV-038 — `write_output` clobbers promotion decisions.** `write_output` blind-overwrites
      `variant_claims_candidates.json` on every extraction run, so any re-run after a review pass
      destroys the `trust_tier=1` promotions it made. DEV-038 recorded this as a "known unaddressed
      risk", mitigated only by operator discipline. P4 is *the* promotion-heavy stage and runs
      review-then-regenerate repeatedly, so the risk becomes structural here. Fix (merge-on-write
      preserving promoted rows, or a hard refuse-to-overwrite guard) or accept it with a written
      waiver and a documented backup step — but decide explicitly, do not inherit it silently.
- [ ] **DEV-049 — zero-retrieval questions can return non-JSON prose.** When retrieval yields no
      chunks, LangChain4j's `DefaultContentInjector` short-circuits to the bare question, the model
      answers in prose, structured-output parsing fails, and the request surfaces as `serviceError`.
      DEV-049 flagged this "secondary, not fixed". ADR-010's **REFUSAL Q16/Q17 are by construction
      the zero-retrieval case**, so authoring them without fixing this scores a `serviceError` fail
      rather than the refusal the questions are meant to test. Fix before authoring, not after.

- [ ] Per batch (~25–50 groups): rank the 838 unreviewed groups by subject prominence; prioritize
      new claim_types beyond parentage/death (marriage, killer/slaying, birthplace, transformation).
      **Count is stale after P3** — J4a's same-source detector condition adds ~145 `parentage`
      candidates on top
- [ ] **Own GAP-001 Root cause 3's promotion half (option a′) — carried in from P3, currently
      unscoped.** ~**467** parentage rivals already sit as emitted candidates that clear the
      ≥2-source gate and stall at the ADR-004 review gate; no detector change touches them. This is
      the **binding constraint on ADR-007 §6's promise**, and it means "prioritize claim_types
      *beyond* parentage" above no longer holds unqualified — parentage is the largest unworked
      dimension. Decide the policy in the first batch: a bounded first tranche (gold-question
      subjects + the Olympian/Titan spine), a sampling rule, or an explicit P5b deferral with a
      written waiver. Input artifact = P3's per-row dropped-parent record (all 612 rivals)
- [ ] Review & promote in `notebooks/02_verify_conflicts.ipynb` (trust_tier 3→1, ADR-004 gate); new
      surface variants → `claim_type_aliases` follow-up migration (V9_2 precedent), never code
- [ ] Regenerate → reseed → audit → eval → compare → commit-or-revert (the P3 fix loop)
- [ ] Grow the gold set in the same commit: first batch adds ADR-010 backlog (REFUSAL Q16/Q17,
      enrichment-on-non-CONFLICT-route, schema-boundary); later batches add 1–3 questions per new
      data slice with **live-verified** keywords (DEV-050); old questions kept as regression
      sentinels; raise CONFLICT floor as the category grows
- [ ] Optional: add the LLM-judge scoring column once the deterministic loop is stable (ADR-018)

→ Detailed checklist: `TODO-phase2-stage-p4.md` (created at implementation)

---

## Stage P5 — New data types & systematic gap discovery
**Done when (per sub-stage):** its new gold questions pass, all sentinels stay green, per-category
floors hold across a 3-run eval; the relevant ADR/DEV entries are logged.

- [ ] **P5a** — numeric data (**activates ADR-009 → Accepted**): `contingents` table (new V-number),
      bounded extraction reusing instructor/checkpoint + `ref_ranges.py`, seedgen extension, numeric
      gold questions incl. one `ship_count` conflict
- [ ] **P5b** — myths & participants: grow beyond 5 myths (Trojan cycle — "died at Troy" has no
      structured backing, DEV-054 Q11); MIXED over-constraint prompt fix (SQL encodes only structured
      predicates), verified by Q11. **Also lands here if deferred from P3** (GAP-001): **J4b**, the
      `Chaos → Earth` cosmogonic (non-parentage) relation — recommended deferral target; and any
      un-worked residue of Root cause 3's promotion half (a′)
- [ ] **P5c** — geography/epithets: places as attributes or a small table; epithets → `entity_aliases`
- [ ] Schema-prompt co-evolution each sub-stage: schema comments + `SchemaIntrospector` vocabulary
      (frequency-ordered, DEV-041); a new gold question verifies the model uses each new table
- [ ] Maintain `docs/DATA-GAPS.md` (triage-fed backlog) — it selects the next sub-stage; reconsider a
      minimal `query_log` only if real web traffic exists (weigh the write-grant exception)
- [ ] **DEV-066 — cycle detection is non-exhaustive.** `cycle_check.py` reports one representative
      cycle per strongly-connected component via a single DFS back-edge, not full elementary-cycle
      enumeration (Johnson's algorithm). DEV-066 deferred this "to Phase 3 if it turns out to
      matter" — **there is no Phase 3 in this roadmap**, which stops at P5c, so it had no home until
      2026-07-27 `[DEVIATED - see DEVIATIONS.md #DEV-093]`. It already mattered once: DEV-086's
      unexplained A3 jump (89 → 127) was this limitation, not a regression, and cost a full
      investigation to establish. P5's new data types grow the graph, so decide here — implement
      exhaustive enumeration, or document the non-exhaustiveness in A3's own output so the next count
      jump is self-explaining.

→ Detailed checklist: `TODO-phase2-stage-p5.md` (created at implementation)

---

## Cross-cutting rules (apply to every stage)

- **Flyway checksum trap:** regenerate V10–V12 freely only while local-only; once a shared env has
  applied them, corrections are additive migrations (`V12_1`-style). New tables always get fresh
  V-numbers.
- **Root cause first, code fix only if still needed.** For every defect, diagnose and correct the
  underlying cause (data / existing prompt rule), reseed, and **re-measure before writing new code**.
  A workaround (prompt rule, query-time bound, retry, migration) ships only on *evidence* that the
  cause-level fix left the question failing — never pre-emptively stacked on an unreproduced defect.
- **Never act on a single-run delta** — the 3-run stable/flaky classification is the contract.
- **Always state the layer when quoting an A3 cycle count** (ADR-020): post-resolver `parent_of`,
  pre-collapse candidates, `audit --candidates`, and the live seeded DB measure different graphs and
  are not comparable to each other.
- **Keyword edits are logged eval-bug fixes** (live-verified, DEV-048/050), never silent tuning.
- **Embedding preservation:** never `down -v`; `reseed-local.sh` is the only sanctioned reseed path.
- **Deviation protocol (CLAUDE.md):** log DEV entries; annotate with banners; ADR status flips
  (ADR-009 at P5a) recorded properly.
- **Any `LLM_CHAT_MODEL` change is eval-gated, and now also a cost decision.** Updated based on
  DEV-097 (see DEVIATIONS.md). ADR-021 enabled Anthropic prompt caching on both chat beans but
  measured that it saves **nothing** on Claude Haiku 4.5, whose 4,096-token minimum cacheable prefix
  is the highest of any current model — every system prompt here is below it (largest:
  `TextToSqlAgent` + injected schema ≈ 3,350 tok; then ≈2,200 / 520 / 330 / 310 / 250). Switching to
  **Sonnet 5** (1,024-token minimum) would make both text-to-SQL prompts cache immediately on the
  SQL and MIXED routes. **Open item, deliberately not bundled into ADR-021:** decide it on the
  per-agent `inputTokens` the new `CacheTelemetryListener` reports against the seeded corpus, plus a
  3-run eval comparison — a model swap changes answer quality, per-token price, and latency, so it
  cannot ride along on a billing-only change.
