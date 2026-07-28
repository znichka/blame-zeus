# Stage P4 — Iterative conflict-depth loop: Detailed Checklist

**Done when:** (1) the **second** prerequisite is discharged — DEV-049's zero-retrieval path returns
a parsed `{answer, citations: []}` refusal instead of `serviceError` (DEV-038, the first, landed
2026-07-28 as DEV-101); (2) the loop has run **≥3 batches end-to-end**, each one a complete
`review → seedgen --strict → reseed-local.sh → audit → runner --runs 3 → compare.py →
commit-or-revert` pass with its results dir, candidate JSON and migrations committed **together**;
(3) the **seeded `variant_claims` table** covers **≥4 canonical claim_types** (today: **2** —
`parentage` and `death`, counting `birth` as its V9_2 alias) and **all top-20-prominence subjects**
frozen from A8's first clean ranking (today: **3** — Aphrodite, Achilles, Io); both counted in the
table after a reseed, **not** in the candidate file, which currently overstates by 38% (*Contracts*);
(4) the gold set is **≈25 questions** (today **16**) with the ADR-010 backlog authored
— REFUSAL **Q16/Q17**, an enrichment-on-non-CONFLICT-route question, a claim-type-relevant REFUSAL,
and a schema-boundary question — every keyword **live-verified** and every old question kept as a
regression sentinel; (5) **per-category floors are enforced**, including a REFUSAL floor promoted off
`null` in `evaluation/eval-config.json` once Q16/Q17 exist, and a CONFLICT floor raised as the
category grows; (6) **overall ≥75% sustained across a 3-run eval** with zero stable regressions;
(7) GAP-001 Root cause 3's promotion half (a′) and GAP-002's unknown-name long tail are each either
worked or **explicitly deferred with a written waiver** — neither may close silently.
*(The loop continues past this gate.)*

> **Design source of truth:** `IMPLEMENTATION_PLAN_PHASE2.md §5` (the repeatable batch, its five
> steps, the two prerequisites, the P4 exit, the `ConflictProbe` risk) and `§4.3`/`§7`/`§8`/`§9`
> (the fix loop this stage reuses unchanged, the "new claim_types are data + `claim_type_aliases`
> rows, never schema" rule, the Flyway-checksum trap, critical files); **ADR-010** (the expansion
> half — which questions, why per-category floors, "curated not bulk"); **ADR-004** (the human
> promotion gate: no row reaches `trust_tier=1` without per-row developer review); **ADR-007 §5/§6**
> (router-independent enrichment, claim-type filtering — what the new gold questions test);
> **ADR-018 §Decision 3/4** (3-run stable/flaky contract; the optional LLM-judge column).
> This checklist is the *granular task breakdown* — it does not re-justify the design.

> **Operating principle (CLAUDE.md + ADR-017):** **fix data at the candidate-JSON layer, never with a
> runtime/query-time patch**, and **root cause first — code fix only if still needed**. Every
> promotion lands in `ingestion/extraction/output/variant_claims_candidates.json` (the editable
> source of truth), then flows through `seedgen` → `reseed-local.sh`. `python -m audit` is a
> **standing pre-seedgen gate**: no batch commits until it is clean or a finding is waived with a
> written reason. **"Clean" means exactly one thing in this checklist: `python -m audit` exits `0`.**
> Read the rule off the code, not off intuition — `AuditRun.exit_code` is
> `1 if any(not f.waived for f in self.all_findings) else 0`, so **any** unwaived `Finding` fails the
> gate and **`severity` does not enter into it**: a `"warning"` blocks exactly as hard as an
> `"error"`. There is no such thing as a finding that is emitted but tolerated. The only two ways to
> exit 0 are *emit no finding* or *waive it with a written reason*, and that is why F0c's
> standing-waiver decision is load-bearing rather than bookkeeping. Never act on a single-run eval delta — the **3-run stable/flaky** classification is
> the contract. A keyword edit made to pass a run is a logged **eval-bug** fix, never silent tuning
> (DEV-048/050). An eval run containing `transport error` in `raw_responses.json` is **invalid, not
> evidence** (DEV-100) — Track D makes that visible instead of leaving it to operator memory.

Before starting, re-read `DEVIATIONS.md` (deviation protocol). Relevant carry-overs:
- **DEV-101 / DEV-038 — DONE, and it changes how promotion must be keyed.**
  `_write_claims_preserving_review()` (`ingestion/extraction/run_extraction.py`) now merges on write,
  keyed on `_CLAIM_IDENTITY = (subject_name, claim_type, claim_value, source_id, passage_ref)` with
  `trust_tier` deliberately excluded as the mutable review verdict. The merge is **one-directional** —
  extraction owns which claims exist, review owns their tier — so a promoted row the extractor stops
  producing is **not** resurrected, only reported by name. Consequence this stage must act on: the
  file is rewritten in *extraction* order, so **positional indices are not stable across a
  re-extraction** (Track C).
- **DEV-049 — OPEN, and it is the gate on ADR-010's REFUSAL pair.** `DefaultContentInjector.inject()`
  short-circuits to the bare question when `contents.isEmpty()`, the model answers in prose, the
  structured-output parse fails, and the request surfaces as `serviceError=true`. DEV-049 recorded
  this as "secondary, not fixed" because Stage 6's scope was the FACT slice. DEV-101's Impact repeats
  the claim that Q16/Q17 "are by construction the zero-retrieval case", so authoring them first would
  score a `serviceError` fail rather than the refusal they test (Track A). **Treat that as a
  hypothesis, not a fact — A1f measures it.** It is credible for Q16 (physical appearance is simply
  absent from the corpus) and much weaker for Q17, which names Zeus, Troy and a council: all densely
  represented in the Iliad chunks, so it may well retrieve above `min-score` and refuse on *content*
  grounds instead. **The A→E1/E2 dependency holds only for whichever of the two actually retrieves
  nothing**; if Q17 retrieves, it is not blocked by Track A, it tests a different refusal path, and
  E2's `forbidden_patterns` must be written against that path (E2 already says so).
- **DEV-060 / TODO-phase2-stage-p1 B4 — the REFUSAL scorer already exists.** `score_refusal` in
  `evaluation/runner/scoring.py` implements all three `refusal_criteria` flags and
  `SOURCE_SILENCE_PHRASES`; P1 built it deliberately ahead of the questions so **P4 needs no scorer
  change**. If the live refusal wording doesn't match, extend `SOURCE_SILENCE_PHRASES` — that
  extension point is the sanctioned one, and it is not a scorer change.
- **DEV-090 / GAP-001 Root cause 3 — the promotion backlog A6 made visible.**
  `ingestion/audit/dropped_parents.py` (audit check **A6**) records every `parent_of` candidate the
  contested-collapse resolver discards: **697 dropped rows / 612 distinct child+parent pairs, 694
  without existing promoted coverage**. A6 "only makes the backlog visible, it promotes nothing
  itself." That backlog is P4's, and A6's box cannot close until it is worked or waived (Track F0).
- **DEV-098 / DEV-099 — the extraction-corruption class, and its detector.** `Arges` was **entirely**
  corrupted `Ares`; `Steropes` was a five-way `Sterope` split. Audit check **A7**
  (`ingestion/audit/name_coverage.py`) now detects the failure mode. Its six findings were triaged in
  P3b (DEV-100); the *generalization* — whether the same near-miss confusion recurs for other major
  names — is still open and belongs with Track H.
- **DEV-078…DEV-082 / GAP-002 — do not bulk-add names.** Track J spent five deviation entries
  removing name-conflation defects. Bucket 2 of GAP-002 (`Electra`, `Eurytus`, `Phineus`, `Thoas`)
  are multi-person names in this corpus; adding a bare name there *creates* the defect Track J
  removed. Per-name source verification, never a batch add (DEV-047: never fabricate).
- **DEV-100 — an eval run with transport timeouts is not evidence.** Q15 measured 9.1 s at normal
  latency and **>7.5 minutes** during an API slow episode; three requests hit the 60 s client timeout
  and converted passing CONFLICT questions into false failures worth 7 points, while the server sat
  idle and healthy. Check `raw_responses.json` for `_runnerNote: transport error` before reading any
  score as a regression (Track D automates this).

**Deviation protocol:** Tracks **C** (review-workflow re-keying) and **D** (eval-report transport
signal) are **new relative to `IMPLEMENTATION_PLAN_PHASE2.md §5`** — §5 assumes the notebook and the
report are fit for purpose; measuring the live tree for this checklist showed neither is. Track **B**
builds emitters §5 *asserts already exist* ("the audit package emits the ranking") but which do not.
Each needs its own `DEV-NNN` entry and the `> ⚠️ Deviations occurred in this stage` banner treatment
per the CLAUDE.md protocol. **This checklist was authored when DEV-102 was the next free number —
check `DEVIATIONS.md` for the current one before claiming any.** Reserve, indicatively:
**DEV-102** Track A (the DEV-049 fix); **DEV-103** Track B (audit checks A8/A9/A10);
**DEV-104** Track C (keyed promotion); **DEV-105** Track D (transport/latency signal in `report.md`);
**DEV-106** Track E (ADR-010's expansion half — the gold-set growth); **DEV-107** Track G (V18
`claim_type_aliases`); **DEV-108+** one per Track F batch and per Track H triage pass.

---

## Contracts verified against the live tree (code against these exact shapes)

Every number below was measured on **2026-07-28** against the working tree at `2e4ce40`. The
reproducing command is given for each — re-run them before starting, and **record any delta in the
owning track's banner rather than silently coding against a stale figure** (the P3 lesson: that
checklist was authored against 131 relation labels and 29 fuzzy-dup pairs; the live values were 177
and 45, which cost two after-the-fact deviation banners).

- **`variant_claims_candidates.json`** — **7,429 rows**, **839** distinct `(subject, claim_type)`
  groups, **71** rows at `trust_tier=1`, 7,358 at tier 3. Every row carries exactly
  `{subject_name, claim_type, claim_value, source_id, passage_ref, trust_tier}` — there is **no**
  `review_status` field, and nothing but `trust_tier` records a review decision.
  ```
  python3 -c "import json,collections; d=json.load(open('ingestion/extraction/output/variant_claims_candidates.json')); print(len(d), len({(r['subject_name'].strip().lower(), r['claim_type']) for r in d}), collections.Counter(r['trust_tier'] for r in d))"
  ```
- **The review frontier is 835 groups, not "838".** All **71** promotions sit in just **4** groups
  across **3** subjects — `Aphrodite/parentage` (+`Aphrodite/birth`), `Achilles/death`,
  `Io/parentage`. So **835 of 839 groups have zero promoted rows**. The "838 unreviewed groups"
  figure in `ADR-017:61`, `IMPLEMENTATION_PLAN_PHASE2.md:324`, `TODO2.md:389` and `TODO.md:113` is a
  stale pre-P3 count and is superseded here; `TODO2.md:391-392` already flags it as stale (J4a's
  same-source detector condition added ~145 `parentage` candidates on top).
- **All 839 groups already clear the ≥2-distinct-source detector gate** — that gate is what the
  extractor emits on, so it is not a filter available for tranche selection. Selection must come from
  prominence and claim_type (Track B).
- **Promoted coverage against the exit gate:** canonical claim_types **2** of the required ≥4
  (`parentage` 43 rows + `birth` 1 which V9_2 aliases to `parentage`; `death` 27); prominence
  subjects **3** of the required top-20.
- **Candidate space and table space are not the same, and the gap is 38%.** Every figure above is
  measured on `variant_claims_candidates.json`; the exit gate is worded against the **`variant_claims`
  table**. **71** promoted candidates become **44** seeded rows — `V12__seed_variant_claims.sql` holds
  exactly 44 (`Achilles` 22, `Aphrodite` 13, `Io` 9). The cause is mechanical, not lossy review:
  `seedgen`'s dedup key (`variant_claims_gen.py:32`) is the **4-tuple** `(subject, claim_type,
  claim_value, source_id)`, while DEV-101's review identity `_CLAIM_IDENTITY` is the **5-tuple** that
  also includes `passage_ref`. The promoted rows collapse to exactly 44 distinct 4-tuples — verified,
  the numbers match to the row. **Two consequences P4 must plan around:** (1) **27 of 71 promotions
  (38%) produced no table row at all** — they were the same claim attested at a second passage. In a
  stage whose entire cost is per-row human review, promoting a row that differs from an
  already-promoted one *only* in `passage_ref` is free review effort spent for zero coverage, so the
  tranche rule (F0a) should prefer breadth across `(subject, claim_type)` groups over depth within
  one. (2) **Coverage must be reported in both spaces** (F1i) — a group can be fully promoted in
  candidate space and still contribute nothing new to the table.
  ```
  grep -c "^ *((SELECT" core-api/src/main/resources/db/migration/V12__seed_variant_claims.sql
  ```
  *Not in scope here, but worth a J-item:* the surviving row keeps one arbitrary `passage_ref`, which
  sits oddly with DEV-021's stated reason for the column ("so surfaced conflicts cite like RAG answers
  do"). Record it; do not redesign the dedup key inside a promotion batch.
- **18 distinct candidate `claim_type` surface forms**, of which **7 are one `notable*` family**:
  ```
  parentage 5038 · death 943 · marriage 676 · notable_claim 268 · notable 218 · notable_deed 75
  epithet 72 · notable_act 56 · transformation 19 · "notable claim" 14 · "notable act" 9
  abduction 9 · other 9 · notable_event 8 · birth 8 · role 3 · punishment 2 · burial 2
  ```
  `claim_type_aliases` (V8_2 + V9_2) currently maps only `parent_of`, `parents`, `married_to`,
  `killed_by`, `killed by`, `slain by`, `slaying`, `death_manner`, `manner_of_death`, `how he died`,
  `birth`. **No `notable*` variant is aliased** — that is Track G's V18.
- **`evaluation/gold-questions.json`** — a flat array of **16** objects, ids **1–15 and 18**. Ids
  **16 and 17 are deliberately absent**, reserved by ADR-010 for the REFUSAL pair, whose text is
  already fixed at `IMPLEMENTATION_PLAN.md:1041-1042`: Q16 *"What did Achilles look like
  physically?"*, Q17 *"What were Zeus's exact words at the Trojan council?"*, both
  `expected_route: RAG`. **Next free id for new questions is 19.** No object in the file carries a
  `refusal_criteria` key yet; the schema is at `IMPLEMENTATION_PLAN.md:981-1002`.
- **`evaluation/runner/scoring.py`** — `SOURCE_SILENCE_PHRASES` is a module-level tuple;
  `score_refusal(q, resp)` implements `must_not_assert_answer`, `must_mention_source_limit`,
  `must_not_fabricate_citation` and requires *all enabled* criteria to pass **and** no
  `forbidden_patterns` hit. **Do not modify its logic** — P1 built it for exactly these questions.
- **`evaluation/eval-config.json`** — `overall_target: 0.75`; `category_floors: {CONFLICT: 0.5,
  DATA: 0.5, REFUSAL: null}`; `timeout_seconds: 60`. The REFUSAL `null` is what Track **E6** flips
  (E5 is the Q21 schema-boundary question — a different item entirely). Note also that **FACT and
  MIXED have no floor at all** (`null`, so `floor_met: null` in `scores.json`): "per-category floors
  are enforced" in the exit gate means CONFLICT + DATA + the new REFUSAL, not all five categories.
  Adding FACT/MIXED floors is **not** in P4's scope — if E6 wants them, that is a deliberate addition
  to justify in its DEV entry, not a gap to close silently.
- **`evaluation/runner/__main__.py`** writes `_runnerNote` into the raw response on transport failure
  (`{"serviceError": true, "answer": "", "routeDecision": null, "_runnerNote": note}`).
  **`report.py` never reads it** — verified by grep; it emits only `score.notes`. That is Track D.
- **Audit check contract** (`ingestion/audit/contract.py`): a module conforms by exposing a
  module-level `NAME: str` and `run(candidates_dir, db_conn) -> CheckResult`; `__main__.py`'s
  `discover_checks()` walks the package and picks up anything with both — **there is no `register()`
  call**. `Finding` is a frozen dataclass `{check, severity, subject, detail, suggested_fix, waived,
  waiver_reason}` with a `waive(reason)` that **raises on an empty reason**. Existing checks:
  **A1** `duplicate_entities`, **A2** `drop_accounting`, **A3** `cycle_check`, **A4**
  `relation_taxonomy`, **A5** `integrity`, **A6** `dropped_parents`, **A7** `name_coverage`.
  **P4's new checks take A8, A9, A10.**
- **`ingestion/notebooks/02_verify_conflicts.ipynb`** — promotion is **positional**: cells 10–13
  accumulate `approved_indices: list[int]`, cell 14 does `for i in approved_indices:
  candidates[i]["trust_tier"] = 1` then rewrites the file. Three historical `approved_indices += [...]`
  cells are committed in the notebook. Track C replaces this keying.
- **Latest migration is `V17`** (`V17__create_relation_aliases.sql`). New `claim_type_aliases` rows
  take the next fresh number **`V18`**. `afterMigrate__grant_app_user.sql` grants schema-wide —
  verify, don't assume.
- **`scripts/reseed-local.sh`** is the only sanctioned reseed. **Never `docker compose down -v`.**
  The Flyway-checksum trap (`§8`): regenerating an already-applied V10–V12 file is legal **only**
  while local-only — still true today, so free regeneration holds for this stage.
- **`compare.py` baseline — the P3b close is NOT usable as-is; F0d re-runs it clean.** The obvious
  candidate, `evaluation/results/2026-07-27T21-21-29Z__3a3f894__p3b-a7-findings-triage/` (P3b close:
  13/16 = 81%, DATA 4/5 = 80%, all floors met, zero stable regressions), **is DEV-100's own transport
  episode** — its `raw_responses.json` carries three `"_runnerNote": "transport error: timed out"`
  entries (lines 553, 1084, 1393; Q13/Q15, both CONFLICT). Under this checklist's own operating
  principle that is *invalid, not evidence*, and Track **D4** will make `compare.py` refuse it
  outright. Comparing against it would also manufacture spurious FAIL→PASS deltas on exactly the two
  questions DEV-100 proved never changed. **F0d produces a clean re-run, and that run is the accepted
  baseline for F1.** It does **not** need a checkout of `3a3f894`: the only commit since is `2e4ce40`
  (DEV-101), whose Impact records "no schema, no migration, no seeded-data change, no gold-question
  change, and nothing reseeded" — verified, it touches `run_extraction.py`, its tests and docs only —
  so the current tree is **eval-identical** to the P3b close.
  ```
  grep -c '_runnerNote' evaluation/results/2026-07-27T21-21-29Z__3a3f894__p3b-a7-findings-triage/raw_responses.json
  ```
  Thereafter each batch compares against **the last accepted run**, not against F0d's forever.

### An unresolved conflict between two source documents — Track F0 decides it

`IMPLEMENTATION_PLAN_PHASE2.md §5` step 1 says to *"prioritize **new claim_types beyond
parentage/death**"*. `TODO2.md:396-398` **retracts that**: GAP-001 Root cause 3 leaves ~**467**
parentage rivals that clear the ≥2-source gate and stall at the ADR-004 review gate, so *"parentage
is the largest unworked dimension"* and the beyond-parentage guidance *"no longer holds
unqualified"*. §5 was never updated, so the two documents disagree. **This checklist does not pick a
winner** — F0 does, in writing, before the first batch, and the decision is logged as a DEV entry.

---

## Parallelization Guide

```
Track A  DEV-049 zero-retrieval refusal fix (Kotlin)   ─┐  Start all four now. They touch
Track B  audit emitters A8/A9/A10 (Python)              │  disjoint files and nothing in
Track C  keyed promotion (notebook) — C1–C5 only        │  this stage blocks them.
Track D  transport/latency signal in report.md (Python) ┘  ONE internal edge: C6 needs B7.

Track E  gold-set authoring (ADR-010 expansion half)
  ├─ E1/E2  REFUSAL Q16/Q17 ─────────── NEEDS A *only if* zero-retrieval; A1f measures
  │                                     which of the two actually is (Q16 likely, Q17 doubtful)
  ├─ E3/E5  enrichment-route · schema-boundary ── need nothing; author anytime
  ├─ E4     claim-type-relevant REFUSAL ──────── NEEDS F1's promotions (the stored
  │                                              death conflict it asserts must exist)
  └─ E6/E7/E8  floors · per-batch questions · flaky-CONFLICT watch ── ride with F

Track G  V18 claim_type_aliases (notable* family) ── SEED ROWS need B's normalized distribution
Track H  GAP-002 unknown-name long tail (~362) ─── independent triage; findings feed F's batches

Track F  THE BATCH LOOP — SERIAL INTEGRATION GATE.  Needs B (ranking) + C (safe promotion) + G,
         and F1g needs D4's rule + F0d's clean baseline.
  └─ F0  tranche rule + GAP-001 a' policy + clean-baseline re-run (F0d) ── gates F1
  └─ F1  batch 1 — CONCRETE (also lands E's four questions)
  └─ F2  batch 2 — template, tranche per F0's rule
  └─ F3  batch 3 — template, tranche per F0's rule
Track J  docs: DEV entries, ADR-010 action items, banners, stale-count fixes ── prose, anytime
```

**Rule of thumb:** **A, B, C1–C5, D fan out from minute one** — nothing in this stage blocks them.
A gates E1/E2 *only for whichever question A1f shows is genuinely zero-retrieval*. B gates F (no
ranking, no tranche) and G's seed rows, and **B7 gates C6** — the one dependency inside the
"concurrent four", since C6 renders A8's ranking and A10's inventory in the notebook's group-listing
cell and B7 emits that JSON explicitly for it. Keep the edge pointing that way: B must never read
C5's promotion log, or the two tracks deadlock. C gates F (promoting by stale index is a silent data
corruption, not an inconvenience). **D gates F1g**, both ways: D4 refuses a transport-dirty run
outright, and the definition-of-done requires D's banner clean on the final eval — so "land it before
F1's eval" is a hard ordering, not a nicety. E3 and E5 are pure authoring and can land in any batch's
commit; **E4 is the one gold question
that must wait**, since it asserts an empty `conflicts[]` for a subject whose *death* conflict has to
already be promoted. **F is the serial integration gate**, exactly as P3's Track I was: never batch
two tranches into one unaudited reseed, and never commit a batch whose `compare.py` shows a stable
regression. H's candidate-JSON edits fan out in parallel but every merge serializes through F. J is
prose, anytime.

**Out of scope, deliberately:** ADR-018 §Decision 3's **optional LLM-judge scoring column**. §5
permits it "once the deterministic loop is stable"; the loop does not exist yet, so adding a
non-deterministic scorer now would make the first three batches' gates unreadable. Revisit after F3,
or in P5.

---

## Track A — DEV-049: zero-retrieval returns a parsed refusal, not `serviceError` (Kotlin; blocks E1/E2)

> ⚠️ **Deviations occurred in this track.** A1f's live reproduction did **not** reproduce the
> `serviceError` bug — see `DEVIATIONS.md` **#DEV-102**. Re-scoped from a code fix (A2f–A4f) to a
> verification note + a `SOURCE_SILENCE_PHRASES` extension (A5f). **Carry-over for Track E:** neither
> draft Q16 nor Q17 retrieves zero chunks against the live corpus at `min-score=0.5` — both returned
> substantive, correctly-cited answers, not refusals. E1/E2 must re-verify this before authoring.

*IDs carry an `f` suffix (= fix) so they never read as the audit check names `A1`–`A7`, which are
taken — the same collision-avoidance P3's Track A used with its `r` suffix.*

The one prerequisite still open. `RagAgent`'s `@SystemMessage` **already** specifies the refusal
shape ("If the retrieved context does not support an answer, set `citations` to an empty array and
make `answer` an explanatory sentence saying the provided texts don't address the question"), so this
is not a prompt-authoring task — the model never gets the chance to obey, because
`DefaultContentInjector.inject()` discards the whole augmentation, system message included, when
`contents.isEmpty()`. **Root cause first: reproduce before fixing.**

- [x] **A1f** — **Reproduce and record, before writing any code.** Start the stack
      (`scripts/run-local.sh`), `POST /api/v1/query` with a question guaranteed to retrieve nothing at
      `app.rag.min-score=0.5` — DEV-049's own negative control, *"What is the chemical formula for the
      caffeine molecule?"*, returned zero chunks at 0.3 and 0.5 — plus draft Q16 and Q17. Capture the
      full response bodies and the DEBUG retrieval lines. **Confirm `serviceError: true` and prose,
      not JSON.** If it does *not* reproduce, stop: re-scope this track to a verification note and say
      so in the DEV entry rather than fixing an unreproduced defect.
      **Record the retrieved-chunk count for Q16 and Q17 separately, and treat it as this track's
      second output** — it is what settles E1/E2's dependency on Track A (see the DEV-049 carry-over
      above). Q17 names Zeus, Troy and a council, all dense in the Iliad chunks, so it may retrieve
      above `min-score` and never touch this code path at all. Whichever of the two retrieves nothing
      is blocked on this fix; whichever retrieves is unblocked immediately and tests a different
      refusal path. Say which is which in the DEV entry so E1/E2 can start without re-measuring.
      **Result: does not reproduce.** 6/6 runs of the negative control returned `serviceError: false`
      with a parsed JSON refusal (`debug.retrievedChunks: []` confirmed genuine zero-retrieval).
      Neither draft Q16 nor Q17 retrieves zero chunks at the live corpus/`min-score=0.5` — both
      answered substantively with real citations, so neither is currently a zero-retrieval case at
      all. Full detail in `DEVIATIONS.md` **#DEV-102**. Re-scoped per this box's own instruction:
      A2f–A4f skipped (nothing to fix), A5f–A7f still run as live verification.
- [~] **A2f** *(skipped — no defect to fix, see A1f's result)* — **The fix, in `core-api/src/main/kotlin/com/blamezeus/coreapi/config/RagConfig.kt`:**
      a `ContentInjector` that delegates to the existing metadata-configured `DefaultContentInjector`
      when `contents` is non-empty, and on an **empty** `contents` injects an explicit
      "no passages were retrieved for this question" block into the user message instead of
      short-circuiting to the bare question. Keep the current `metadataKeysToInclude(listOf("author",
      "work", "passage_ref", "stance"))` behaviour byte-identical on the non-empty path — the DEV-049
      citation fix must not regress. Wire it via `DefaultRetrievalAugmentor.builder().contentInjector(...)`;
      `RagAgent`'s `retrievalAugmentor = "retrievalAugmentor"` binding is unchanged (`AiServices`
      throws if both `contentRetriever` and `retrievalAugmentor` are set).
- [~] **A3f** *(skipped — no defect to fix)* — **`RagAgent.kt` `@SystemMessage`**, only if A1f's evidence shows the existing wording
      insufficient once the sentinel actually reaches the model: name the sentinel explicitly so the
      empty-citations branch is unambiguous. Prefer changing nothing — the existing paragraph already
      covers it, and an unnecessary prompt edit is a change to every RAG answer, not just refusals.
- [~] **A4f** *(skipped — no injector built, see A2f)* — **TDD**: a unit test on the injector alone — it is a plain class, so this needs no
      chat model and does not touch the no-live-LLM guardrail. Empty `contents` → the returned
      `UserMessage` contains the sentinel and the original question; non-empty `contents` → output is
      identical to what the bare `DefaultContentInjector` produces for the same input (assert against
      the delegate, not against a hardcoded string, so the metadata format can evolve). A third case:
      a single content with all four metadata keys still renders them.
- [x] **A5f** — **Live-verify the refusal wording against the scorer.** Re-run A1f's three questions
      against the fixed build and check the answer text against
      `evaluation/runner/scoring.py::SOURCE_SILENCE_PHRASES`. If no phrase matches, **extend the
      tuple** with the phrasing the model actually produces — `TODO2.md:60` and
      `TODO-phase2-stage-p1.md:160-166` both sanction this explicitly, and it is *not* a scorer change
      (`score_refusal`'s logic stays untouched). Record the before/after phrasing in the DEV entry;
      this is the DEV-050 live-verification rule applied to refusals.
      **Result:** none of the 6 live answers matched any existing phrase. Added `"do not contain"`
      (6/6 runs) and `"outside the scope"` (2/6) to `SOURCE_SILENCE_PHRASES`, plus a regression test
      pinned to the exact live wording (`evaluation/runner/tests/test_scoring.py`).
- [x] **A6f** — Confirm the end state on all three: `serviceError: false`, `citations: []`,
      `routeDecision: RAG`, and an answer that acknowledges the texts are silent. Capture the raw
      responses into the DEV entry as evidence — the same standard DEV-049 itself set.
      **Confirmed** for the negative control (the one genuine zero-retrieval case among the three),
      stable across 6 runs. Q16/Q17 are not zero-retrieval cases at the live corpus, so this end
      state doesn't apply to them as drafted — see A1f's result and Track E's carry-over note above.
- [x] **A7f** — `./gradlew :core-api:test` green (180+ tests as of P3's close). Log **DEV-102**;
      tick the `TODO2.md:382-387` DEV-049 box and the matching line in
      `IMPLEMENTATION_PLAN_PHASE2.md §5`'s banner, which currently reads "**DEV-049 remains open**,
      so ADR-010's REFUSAL Q16/Q17 still cannot be authored".

---

## Track B — audit emitters: prominence, normalized claim-type distribution, group inventory (Python; gates F and G)

> ⚠️ **Deviations occurred in this track.** See `DEVIATIONS.md` **#DEV-103**. B7's group total
> comes in at **835**, not the raw-839 figure — grouping by *canonical* claim_type (as B7
> instructs) is a different key than the Contracts section's raw-claim_type measurement; the
> 4-group reduction is entirely the `Aphrodite`/`Athena`/`Dionysus`/`Adonis` birth+parentage
> merges, verified directly. `group_inventory.py`'s own baseline self-initializes from whatever
> the live figure actually is rather than asserting 839, so this is not a bug, just a different
> (and more correct, per B7's own literal instruction) grouping key than the headline number.

§5 step 1 says "the audit package emits the ranking" and `TODO2.md:389` repeats it. **It does not** —
`grep -rn "prominence\|degree\|rank" ingestion/audit/*.py` returns nothing. Three new sibling modules,
each conforming to `audit/contract.py` (module-level `NAME` + `run(candidates_dir, db_conn)`) so
`discover_checks()` picks them up with no registration call. All three are **reporting** checks in the
`relation_taxonomy` mould — they emit data for human selection and must **not** fail the runner's exit
code, or the standing pre-seedgen gate breaks on every batch.

- [x] **B1** — `ingestion/audit/prominence.py`, check **A8**: pure core
      `rank_subjects(relationship_rows, candidate_rows) -> list[SubjectRank]` scoring each subject by
      **relationship degree** (in + out, over the live V11 `relationships` when `db_conn` is given,
      falling back to the generated set from candidates) **plus candidate mention count**. Report both
      components separately as well as the composite — a subject with high degree and no claim
      candidates is a different signal from the reverse. No I/O in the core.
- [x] **B2** — A8's report output: the **top 50** subjects with degree, mention count, composite rank,
      the number of `(subject, claim_type)` groups they own, and how many of those already have a
      promoted row. This table **is** the tranche-selection instrument for every batch, and the
      "all top-20-prominence subjects" half of the exit gate is read directly off it.
- [x] **B3** — Resolve subject names through the same path the rest of the pipeline uses before
      ranking, so `Sky`/`Ouranos` (DEV-092) and the `entity_aliases` set do not split one figure's
      degree across two rows. Reuse the existing resolution rather than re-deriving it; if no reusable
      helper exists, say so in the module docstring and use `entity_aliases` from the live DB.
- [x] **B4** — **TDD** `ingestion/audit/tests/test_prominence.py`: a fixture graph where subject X has
      degree 5 / 2 mentions and subject Y degree 1 / 40 mentions → both appear with their components
      intact and the documented composite ordering; an aliased pair merges into one row; an empty
      graph returns an empty ranking without raising. Pure, no live DB.
- [x] **B5** — `ingestion/audit/claim_type_distribution.py`, check **A9**: the candidate `claim_type`
      distribution **after** `extraction/claim_type_normalizer.normalize`, using
      `load_alias_map(conn)` — never a hardcoded map (the DEV-022 rule). Report **raw surface form →
      canonical → count**, so the 7-member `notable*` family is visibly one canonical type and the
      "≥4 canonical claim_types" exit gate counts canonical values, not spellings.
- [x] **B6** — A9 additionally lists surface forms with **no alias row and no canonical match** —
      those are exactly Track G's V18 input, and the mechanism by which each later batch's new
      claim_types get their alias rows without anyone maintaining a list by hand.
      **Implemented narrowly**: only mechanical whitespace/underscore/case-fold duplicates with no
      existing alias row (`'notable claim'`→`'notable_claim'`, `'notable act'`→`'notable_act'`) —
      the full 7-member semantic collapse stays a Track G human call (G1), never guessed here.
- [x] **B7** — `ingestion/audit/group_inventory.py`, check **A10**: one row per
      `(subject, canonical claim_type)` group — candidate row count, distinct `source_id` count,
      distinct `claim_value` count, promoted-row count, and the subject's A8 rank. Emit as
      machine-readable JSON alongside the report table so Track C's notebook can read it directly.
      **Assert only what is actually invariant.** The group total — **839** — is an extraction-level
      fact and does not move when rows are promoted, so a change there is a genuine finding. The
      zero-promoted count (**835** today) is **the thing this stage exists to reduce**: F1–F3 promote
      25–50 groups each, so asserting it as a constant would fire a false finding on every batch after
      the first and force a standing waiver — the exact residue problem F0c is trying to end. So:
      **(a)** finding if `groups_total != 839` (record the new figure and the reason in the owning
      batch's banner); **(b)** finding if the arithmetic identity `groups_with_promotions +
      zero_promoted == groups_total` breaks, which catches a counting bug rather than expected
      progress; **(c)** finding if `zero_promoted` **increases** — promotion is monotone, so growth
      means a promotion was lost, the DEV-101/Track C corruption signature; **(d)** a normal decrease
      is **reported as a trend, not a finding** — print `zero_promoted` against the 835 starting
      figure and the delta since the previous run, which is the coverage number F1i has to report
      anyway. Derive all four from the candidate file alone; **do not read C5's promotion log** — B7
      must not acquire a dependency on Track C, which already depends on B7 via C6.
- [x] **B8** — **TDD** `tests/test_claim_type_distribution.py` and `tests/test_group_inventory.py`:
      a fixture where `notable_act` and `notable act` both alias to one canonical → the distribution
      shows one canonical row with the summed count and both surface forms; an unaliased novel type →
      appears in B6's unmapped list. For A10: a group with 2 sources and 1 promoted row → correct
      counts; a fixture whose group **total** drifts → a finding, not a crash (B7a); a fixture whose
      promoted + zero-promoted ≠ total → a finding (B7b); a fixture where `zero_promoted` has **gone
      up** → a finding (B7c); and — the case that matters most, since it is what every batch produces
      — a fixture where `zero_promoted` has **gone down** with the total unchanged → **no finding**,
      just the trend line (B7d). Assert the no-finding case explicitly; a check that fires on normal
      progress is worse than no check.
- [x] **B9** — Update `ingestion/audit/README.md`: A8/A9/A10 added to the check list and their
      artifacts named. **Be precise about what "reporting-only" has to mean here**, because the
      obvious reading is wrong: `exit_code` is `1 if any(not f.waived ...)` and **ignores
      `severity`**, so a check cannot emit `Finding(severity="warning")` and still exit 0. "Reporting"
      therefore means these checks return `CheckResult(findings=(), summary=…)` on the normal path and
      put their tables in the `summary` and the JSON artifact — **the ranking, the distribution and
      the inventory are never `Finding`s**. The *only* things A8/A9/A10 raise as findings are the
      genuine anomalies: B6's unmapped surface forms and B7's (a)/(b)/(c). Those are meant to block —
      that is the point of them. State this inversion in the README so the next check author does not
      reach for a "warning" severity that silently gates the whole loop. Log **DEV-103**.

---

## Track C — keyed promotion: `02_verify_conflicts.ipynb` (Python; gates F)

> ⚠️ **Deviations occurred in this track.** See `DEVIATIONS.md` **#DEV-104**. C1's hazard was
> proven live (73/73 historical indices resolved to unrelated claims after a reorder), and C3's
> migration found the drift was **already real, not hypothetical**: only 71 of the 3 historical
> cells' 73 indices currently resolve to a promoted row. The 3 stale cells were replaced with one
> keyed cell listing the live file's actual 71 promoted keys, not the (partly stale) index-derived
> content — see the migration markdown cell in the notebook itself for the full accounting.

**A silent-corruption fix, not a convenience.** The notebook promotes by position
(`candidates[i]["trust_tier"] = 1`); DEV-101's merge rewrites the file in extraction order. P4 is the
first stage that runs review → regenerate → review repeatedly, so an `approved_indices` list carried
across a re-extraction promotes **whichever rows now occupy those positions**. There is no error, no
warning, and the result is hand-reviewed provenance attached to unreviewed claims — the exact thing
ADR-004's gate exists to prevent.

- [x] **C1** — **Prove the hazard before changing anything.** Take the committed
      `approved_indices` cells, re-run the extraction merge path against a *copy* of the live file
      (never the real one), and show that at least one index now points at a different claim than it
      did. If positions turn out to be stable in practice, record that finding and downgrade this
      track to the C2 guard alone — evidence first, same as Track A.
      **Result: reproduces decisively** — 73/73 historical indices pointed at a different,
      unrelated claim after a reorder (e.g. Aphrodite/parentage → Agamemnon/death). Full detail
      in `DEVIATIONS.md` #DEV-104.
- [x] **C2** — Re-key promotion to the **same 5-tuple** DEV-101 uses:
      `(subject_name, claim_type, claim_value, source_id, passage_ref)`. Import
      `_CLAIM_IDENTITY`/`_claim_key` from `extraction.run_extraction` rather than redefining them —
      one definition, the DEV-022 discipline applied to code. `review_group(...)` prints the key
      alongside the `[i]` it already prints, and the paste-ready line it emits becomes a list of keys.
- [x] **C3** — **Migrate the existing 71 promotions**: before switching, assert that the 4 promoted
      groups (`Aphrodite/parentage`, `Aphrodite/birth`, `Achilles/death`, `Io/parentage`) resolve to
      the *same* 71 rows under both the positional and keyed schemes. A mismatch means the file
      already drifted — stop and triage, do not proceed.
      **Mismatch found**: only 71/73 historical indices currently resolve to a promoted row, and
      one promoted row (`Aphrodite/birth`) is covered by none of them. Per this box's own
      instruction, the stale indices were **not** used as the migration source — the notebook now
      lists the live file's actual 71 promoted keys directly.
- [x] **C4** — **A key that matches no row is an error, not a no-op.** Print the unmatched keys and
      refuse to write. Silent skipping is how a review pass ends up believing it promoted rows it
      did not.
- [x] **C5** — **Per-batch promotion log**: each promotion pass appends
      `{batch_label, date, keys[], group_count}` to a committed JSON file, so a batch's promotions can
      be identified and reverted as a unit when `compare.py` comes back red — F's commit-or-revert
      step needs this to be able to revert *the batch* rather than the whole file.
- [x] **C6** — Surface Track B's A8 ranking and A10 inventory in the group-listing cell (replacing the
      flat `for (subject, claim_type), idxs in sorted(groups.items())` dump), so a tranche is picked
      in-tool from prominence + claim_type + source count rather than alphabetically. **This is the
      one item in Track C that is not concurrent with Track B — it consumes B7's JSON artifact, which
      B7 emits for exactly this purpose.** Do C1–C5 first; C6 lands after B7. Read the artifact from
      disk rather than importing the audit modules, so the notebook does not grow a dependency on the
      audit package's internals. Log **DEV-104**.

---

## Track D — transport/latency signal in `report.md` (Python; makes F's gate trustworthy)

> ⚠️ **Deviations occurred in this track.** See `DEVIATIONS.md` **#DEV-105**. D4's refusal logic
> was retroactively verified against the *real* DEV-100 incident (not only synthetic fixtures): the
> P3b close's own `raw_responses.json` `_runnerNote` entries, paired onto its `scores.json` shape
> in memory, correctly produce all 3 real transport-error notes (`Q13 run 2`, `Q15 run 0/1`) — the
> committed results directory on disk was **not** mutated, only used as a read-only fixture.

`TODO2.md:455-464`'s open item, and P4 is the loop that leans on these numbers. Today
`runner/__main__.py` writes `_runnerNote: "transport error: …"` into the raw response and
`report.py` never reads it, so a DEV-100-style API slow episode is indistinguishable from a quality
regression — it cost 7 points of false failure and a full investigation once already.

- [x] **D1** — Record **per-request elapsed seconds** for every question × repetition in
      `raw_responses.json` (the runner already owns the request; this is a timer, not a redesign).
- [x] **D2** — Propagate `_runnerNote` into `scores.json` per question/run, so the machine-readable
      artifact carries it and `compare.py` can act on it too.
- [x] **D3** — `report.md` gains: a **top-line banner** when any repetition carried a transport error
      — *"⚠️ N request(s) failed on transport; this run is invalid as evidence (DEV-100)"* — a
      per-question latency column, and the slowest-request figure. The banner goes **above** the score
      table; the point is that nobody reads the aggregate first.
- [x] **D4** — `compare.py` refuses to treat a run containing transport errors as an accepted
      baseline or candidate without an explicit override flag, and says why. A false PASS→FAIL is
      exactly what this stage's gate must not produce. **The P3b close
      (`2026-07-27T21-21-29Z__3a3f894__p3b-a7-findings-triage`, 3 transport errors) is the live
      example this must refuse** — use it as D5's realistic fixture, and note that F0d exists because
      of it.
- [x] **D5** — **TDD** in `evaluation/runner/tests/`: a fixture run with one `_runnerNote` transport
      error → banner present, run flagged invalid, `compare.py` refuses without the override and
      proceeds with it; a clean fixture → no banner, latency column populated, byte-identical
      behaviour otherwise. Log **DEV-105**.

---

## Track E — gold-set authoring, ADR-010's expansion half (E1/E2 need A; E4 needs F1; E3/E5 need nothing)

ADR-010 Decision 3: **curated, not bulk** — every question keeps hand-authored
`required_keywords` / `required_authors` / `forbidden_patterns` / `refusal_criteria`. **Old questions
are never removed**; they are the regression sentinels. **Next free id is 19** (1–15 and 18 are
taken; 16/17 are reserved for the REFUSAL pair and must use those numbers).

- [ ] **E1** — **Q16 REFUSAL** *"What did Achilles look like physically?"*, `expected_route: RAG`,
      `refusal_criteria: {must_not_assert_answer, must_mention_source_limit,
      must_not_fabricate_citation}` all `true`, `forbidden_patterns` targeting this question's
      hallucination signature (`IMPLEMENTATION_PLAN.md:981-1002` gives `"his hair was"`, `"he had"`,
      `"described as"` — **verify each against a live answer** before committing them, DEV-050).
      **Needs A5f's live-verified refusal wording.**
- [ ] **E2** — **Q17 REFUSAL** *"What were Zeus's exact words at the Trojan council?"*, same shape,
      its own `forbidden_patterns` (quotation signatures rather than description signatures). Verify
      it is genuinely a zero-retrieval question at the live `min-score` — if it retrieves chunks it
      tests something else and the `forbidden_patterns` must change accordingly.
- [ ] **E3** — **Q19 — conflict surfacing via enrichment on a non-CONFLICT route** (ADR-010
      Decision 1; ADR-007 §5 router-independence). A conflict-shaped question the router sends to SQL
      or RAG that must still populate `conflicts[]`. Category `CONFLICT`, `conflicts_min_count >= 2`,
      `expected_route` set to whatever the router **actually** produces — confirm live, and if the
      route proves unstable across 3 runs say so rather than pinning a coin-flip.
- [ ] **E4** — **Q20 — claim-type-relevant REFUSAL** (ADR-010 Decision 1): an *appearance* question
      about a subject that holds a stored **death** conflict, asserting `conflicts[]` comes back
      **empty**. This tests `ConflictLookup`'s claim-type filter, which nothing currently covers. Pick
      the subject from Track B's A10 inventory *after* F1's promotions, so the stored death conflict
      genuinely exists.
- [ ] **E5** — **Q21 — schema-boundary routing** (ADR-010 Decision 1; ADR-005's open action item):
      *"Where is Achilles from?"* → `expected_route: RAG`, with `forbidden_patterns` catching a
      fabricated citation. Location is not in the schema, so this asserts the router does not force it
      into SQL.
- [ ] **E6** — **Floors** in `evaluation/eval-config.json`: flip `REFUSAL` off `null` once E1/E2 land
      (2 questions — pick the floor deliberately and justify it in the DEV entry; ADR-010 mandates
      that floors exist, not specific numbers), and raise `CONFLICT` as the category grows past 4.
      Never lower a floor to make a run pass — that is the keyword-tuning anti-pattern in another
      costume.
- [ ] **E7** — Per later batch: **1–3 questions targeting the newly promoted data**, keywords
      **live-verified against a real answer** before commit (DEV-048/050 — a static corpus grep was
      wrong three times in Stage 6). Each lands in **the same commit** as the batch it measures.
- [ ] **E8** — **Watch the ADR-007 risk** (§5:348-350): more claim_types stress `ConflictProbe`'s
      phrasing sensitivity. Track flaky CONFLICT questions **separately** across batches and do not
      touch the probe prompt on a single batch's evidence — ADR-007 warns against over-enumerating
      surface forms, and the RAG backstop is the designed complement. Log **DEV-106**.
      **Do not add numeric/aggregation questions here** — ADR-010 makes them contingent on ADR-009,
      which flips to Accepted at **P5a**.

---

## Track G — V18 `claim_type_aliases`: collapse the `notable*` family (seed rows ← B6)

> ⚠️ **Deviations occurred in this track.** See `DEVIATIONS.md` **#DEV-107**. G1's review found
> **no claim/deed split in the actual data** — every one of the 7 surface forms mixes active
> deeds, passive events, and asserted claims within itself. One canonical, `notable_claim` (the
> plurality surface form, 268/648 rows), chosen by the same majority-frequency rule A9 already
> uses for its own duplicate proposals.

`§7`: new `claim_type` values are **data + alias rows, never schema changes**, and new migrations
always take a fresh V-number. The V9_2 `birth`→`parentage` migration is the precedent to copy.

- [x] **G1** — From B5/B6's normalized distribution, decide the canonical form for the **7-member
      `notable*` family** (`notable_claim` 268, `notable` 218, `notable_deed` 75, `notable_act` 56,
      `notable claim` 14, `notable act` 9, `notable_event` 8 — **648 rows**). Decide whether they are
      one canonical type or genuinely two (a *claim about* a figure vs a *deed done by* one) —
      **review-gated**, the ADR-019 Track D discipline: a human confirms before rows are written.
      Whichever way it goes, the singular/plural and space/underscore spellings collapse.
      **Result: one canonical (`notable_claim`)** — read real subject/claim_value samples from
      all 7 labels; the claim/deed split does not exist in the data, so inventing it would be
      exactly the guessing this box warns against.
- [x] **G2** — `core-api/src/main/resources/db/migration/V18__add_claim_type_aliases_notable.sql`:
      `INSERT INTO claim_type_aliases (alias, canonical) VALUES …` in the V8_2/V9_2 style, keys
      **lower-cased and trimmed** (`normalize(x) = alias_map.get(x.strip().lower(), x)`), plus a
      schema comment naming this checklist and the DEV number. Confirm
      `afterMigrate__grant_app_user.sql` covers it (it grants schema-wide — verify, don't assume).
      Syntax/semantics-verified via a rolled-back transaction (V17 precedent — not yet applied
      anywhere) and independently via `./gradlew :core-api:test`'s fresh Testcontainers apply of
      V1–V18 (189 tests green).
- [x] **G3** — Confirm the effect where it matters: `variant_claims_gen.py` already calls
      `normalize(alias_map, x)`, and V12 writes the **normalized canonical** `claim_type`, so runtime
      `ConflictLookup` matches by exact equality. **No Kotlin change, no code change at all** — if
      one seems necessary, the alias mechanism is being bypassed somewhere and that is the bug.
      **Confirmed by grep**: `seedgen/variant_claims_gen.py:39` already calls `normalize(...)` at
      promotion time. No code touched.
- [ ] **G4** — Verify through F1's reseed: the regenerated `V12__seed_variant_claims.sql` contains
      **zero** occurrences of any collapsed surface form, and a spot sample of former-`notable act`
      rows lands canonical. This is F's loop, not a standalone reseed (the P3 F6 precedent).
      Log **DEV-107**. **G4 itself stays open until Track F1 actually reseeds** — by design, not
      an oversight (this box says so explicitly).

---

## Track H — GAP-002 unknown-name long tail (independent triage; merges serialize through F)

> ⚠️ **Deviations occurred in this track.** See `DEVIATIONS.md` **#DEV-108**. Landed 12 bucket-1
> entities + 3 translation-spelling aliases (one, `Helios`→`Helius`, caught only *after* adding —
> by running the full audit suite, not by the pre-add review — a useful reminder that the fix-loop
> verification step isn't optional even when the manual check felt thorough). Confirmed 3 more
> bucket-2 collisions (`Oenomaus`, `Hippolytus`, `Ascalaphus`). `scripts/reseed-local.sh` needed a
> fix (`CLEAR_HISTORY_SQL` +`'18'`/`'19'`) hit live while landing this.

`DATA-GAPS.md` routes GAP-002's remainder here: **362** distinct names referenced by candidate
relationships but absent from the confirmed entity set (367 before DEV-096 added `Nereus`, `Doris`,
`Ceto`, `Styx`, `Thaumas`), across ~1,253 dropped rows. **These are leads, not a work list.**

- [x] **H1** — Re-run `python -m audit --only A2` and `--only A7` and record the **current** unknown-name
      count and A7 finding set; the 362 figure predates P3b's later passes.
      **Result: 359** (before this batch), **347** (after) — see DATA-GAPS.md for the full drilldown.
- [x] **H2** — **Bucket every name** per `DATA-GAPS.md`'s four buckets: (1) genuine unambiguous
      figures; (2) namesake collisions and conflations — `Electra`, `Eurytus`, `Phineus`, `Thoas` are
      all multi-person names in this corpus; (3) extraction noise and the `<UNKNOWN>` sentinel
      (~133 rows) — a signal about the extraction pass, no entity to add; (4) **extraction corruption
      of an existing name**, the `Arges`→`Ares` class DEV-098 proved was *total*, not partial.
      **Done at a full-list scale** (359 names, heuristic noise classifier + manual review); found a
      **place-name sub-class** with no home in the `entities.type` enum at all, and a
      **collective/group-noun sub-class** distinct from bucket 3's descriptive-phrase noise.
- [x] **H3** — **Bucket 1 only, in small source-verified batches.** Every added entity cites the
      passage that attests it (DEV-047: never fabricated). **Bulk-adding is rejected** — option (b) in
      `DATA-GAPS.md`'s decision list — because it recreates the name-conflation class DEV-078…DEV-082
      spent all of Track J removing. Bucket 2 needs a per-name **split or merge** decision, not an add.
      **12 entities added, 3 resolved as aliases instead of adds** (`Aesculapius`→`Asclepius`,
      `Phorcus`→`Phorcys`, `Helios`→`Helius`), each verified against its actual candidate rows (and,
      for the 3 newly-confirmed bucket-2 cases, against raw corpus text) before deciding.
- [x] **H4** — **Work DEV-098's open generalization**: whether the same near-miss extraction confusion
      corrupts other major names. A7 detects the shape; run it against the *current* candidate set and
      triage anything it names, since a confirmed entity with anomalously few relationships is the
      `Ares` signature (`Ares`: 0 → 33).
      **A7 unchanged at 2 waived findings** — no new corruption found this pass.
- [x] **H5** — Adding entities grows the graph and **can surface new A3 cycles** — always state the
      layer when quoting a cycle count (ADR-020: post-resolver `parent_of`, pre-collapse candidates,
      `audit --candidates`, live DB are four incomparable graphs). Each batch goes through F's loop
      like any other data change.
      **A3 unchanged at 92 (candidates) / 1 waived (db)** — no new cycle from this batch's additions.
      Full `seedgen → reseed-local.sh → audit` loop run (three passes, see DEV-108).
- [x] **H6** — Whatever is not worked by F3 gets an **explicit written deferral** to P5 with its
      bucket and reason — GAP-002 does not close silently, and option (c) (permanent waiver) was
      already rejected on the grounds that these are real absent pieces of the graph, not duplicates.
      **Written deferral in `DATA-GAPS.md`**: ~330 residual names split into bucket 3 noise (+ the
      new place-name/collective-noun sub-classes), 2 flagged future-batch leads (Hesiod's
      personified abstractions, the Hecatoncheires cluster), and named high-value individual
      candidates (`Tiresias`, `Narcissus`, `Calchas`, `Alecto`, `Enceladus`, `Talos`) for whoever
      picks up the next batch.

---

## Track F — THE BATCH LOOP (SERIAL integration gate — needs B + C + G; F0 gates F1)

The fix loop is `§4.3`'s, unchanged: **edit candidate JSON → `python -m seedgen --strict` →
`scripts/reseed-local.sh` → `python -m audit` (clean or waived with a written reason) →
`python -m runner --runs 3` → `compare.py` vs the last accepted run → commit candidates + migrations
+ gold set + results dir **together**, or revert.** Never batch two tranches into one unaudited
reseed.

### F0 — Decisions and the clean baseline, before the first batch (write each one down)

- [ ] **F0a** — **Resolve the tranche-priority conflict** between `IMPLEMENTATION_PLAN_PHASE2.md §5`
      step 1 ("beyond parentage/death") and `TODO2.md:396-398` ("parentage is the largest unworked
      dimension"). Write the rule as an explicit, repeatable selection procedure over Track B's A8
      ranking and A9 distribution — it is applied unchanged by F1, F2 and F3, so it must be
      mechanical, not a per-batch judgement call. **Build in the breadth-over-depth correction**
      the *Contracts* section measured: `seedgen` dedupes on a `passage_ref`-free 4-tuple, so extra
      promotions within a `(subject, claim_type)` group that repeat an existing claim_value+source
      cost review time and yield no table row (27 of today's 71 promotions). A rule that spreads a
      tranche across groups converts review effort into coverage; one that deepens a single group
      may not. Also freeze the **top-20 subject list** from A8's first clean run here, so the exit
      gate has a fixed target rather than one that moves as Track H grows the graph.
- [ ] **F0b** — **Decide GAP-001 Root cause 3's promotion half (option a′)**, `TODO2.md:393-400`'s
      unscoped carry-in and the **binding constraint on ADR-007 §6's promise**. Input artifact is
      A6's per-row dropped-parent record: **697 dropped rows / 612 distinct child+parent pairs, 694
      without promoted coverage**, of which ~**467** clear the ≥2-source gate. Three admissible
      outcomes, all requiring a written record: a **bounded first tranche** (gold-question subjects +
      the Olympian/Titan spine), a **sampling rule**, or an **explicit P5b deferral with a waiver**.
      Do not leave it implicit — it went unowned through all of P3 precisely that way.
- [ ] **F0c** — Decide whether A6's and A1's permanent-by-design residue gets a **standing
      category-level waiver**. P3's final box could not be ticked because clean means **exit `0`**
      (operating principle) and these two never reach zero findings on their own, so without waivers
      the gate is red every single time. P4 runs it ≥3 more times; settle the policy once, with a
      written reason (`Finding.waive` **raises** on an empty one), rather than re-arguing it each
      batch. Note this is the *only* mechanism available — there is no "tolerated finding" severity to
      fall back on.
- [ ] **F0d** — **Re-run the P3b close cleanly and make *that* the F1 baseline.** The only work in F0
      that is not a decision, and the one that unblocks F1g. `python -m runner --runs 3 --label
      p3b-baseline-rerun` **on the current tree** (eval-identical to `3a3f894` — see *Contracts*),
      with **no data change of any kind first**: this measures the same corpus, the same 44 seeded
      `variant_claims` and the same 16 gold questions, only without the transport episode. Then:
      **(1)** confirm zero `_runnerNote` entries in the new `raw_responses.json` — if any appear, the
      API is slow again; **re-run, do not triage** (DEV-100's whole lesson); **(2)** check it
      reproduces the P3b close within flake — 13/16 or better, DATA ≥ 4/5, all floors met, and Q13/Q15
      returning their 13 and 22 conflicts, which DEV-100 established is what they return whenever the
      request completes; **(3)** if it lands materially *below* the P3b close on a clean run, that is
      a real finding about `2e4ce40` or about baseline flake — triage it **before** F1 rather than
      baking it into the baseline. Commit the results dir and name it in F1g. Land this **after Track
      D** if D is ready (the banner is what proves criterion (1) mechanically); if D is still in
      flight, the `grep -c '_runnerNote'` above is the manual equivalent and does not block.

### F1 — Batch 1 (concrete; also lands E1–E3, E5, E6 and G — E4 only if its conflict exists)

- [ ] **F1a** — **Pick the tranche** (~25–50 groups) by applying F0a's rule to A8/A9/A10. Record the
      exact group list in the batch's promotion log (C5) *before* review starts, so the batch's scope
      is fixed and its revert is well-defined.
- [ ] **F1b** — **Review & promote** in `02_verify_conflicts.ipynb` using Track C's keyed workflow:
      each row checked against its source segment text, `trust_tier` 3→1 — the ADR-004 human gate,
      per row, no exceptions and no bulk promotion.
- [ ] **F1c** — New claim-type surface variants discovered during review → **Track G's V18 alias
      rows**, never a code change (`§7`; the V9_2 precedent).
- [ ] **F1d** — `python -m seedgen --strict` → inspect the regenerated `V12__seed_variant_claims.sql`
      diff before applying anything. Entity-merge fallout (`§8`) is caught here: V13's name-based
      subqueries and the candidate JSON reference names that a merge can move.
- [ ] **F1e** — `scripts/reseed-local.sh` → `python -m audit`. **Clean = exit `0`**, which per the
      operating principle means every finding is either absent or waived with a written reason.
      A8/A9/A10 should contribute their tables via `summary`/artifacts and **no** findings on the
      normal path (B9) — so if the exit code flips because of them, either a real anomaly fired
      (B6/B7a–c: triage it, do not waive reflexively) or B9's zero-finding rule was implemented as a
      `"warning"` severity, which does not do what it looks like it does.
- [ ] **F1f** — **Author the ADR-010 backlog into the same commit**: E1 (Q16), E2 (Q17), E3 (Q19),
      E5 (Q21), plus E6's floor flip. E4 (Q20) lands here only if F1's promotions created the death
      conflict it needs; otherwise it moves to F2.
- [ ] **F1g** — `python -m runner --runs 3 --label p4-batch1` → `compare.py` vs **F0d's clean
      re-run** (*not* `2026-07-27T21-21-29Z__3a3f894__p3b-a7-findings-triage`, which is DEV-100's own
      transport episode and which D4 refuses — see *Contracts*). **Read Track D's transport banner
      first** — a run with transport errors is invalid and must be re-run, not triaged.
- [ ] **F1h** — **Decide.** Green (no stable regression, floors held, new questions pass) → commit
      candidates + V18 + gold set + results dir **together**. Red → triage into the taxonomy
      (**data-gap / pipeline-bug / corpus-gap / eval-bug**) and either fix or revert the batch via
      C5's log. A single-run delta is never grounds for either.
- [ ] **F1i** — Record in the DEV entry: groups promoted, rows promoted, canonical claim_types now
      covered (target ≥4), top-20 subjects now covered, gold-set size, and the per-category rates.
      These five numbers are the exit gate, so every batch reports them. **Report the coverage numbers
      in both spaces** — promoted candidates *and* rows actually present in `variant_claims` after the
      reseed — because `seedgen` dedupes on a 4-tuple that drops `passage_ref` and today collapses 71
      promotions into 44 rows (see *Contracts*). The gate is worded against the table, so the table
      figure is the one that counts; a batch where the two diverge sharply means the tranche was deep
      rather than broad, which is F0a's signal to correct.
- [ ] **F1j** — Note any **flaky** CONFLICT question separately (E8) — do not react to it yet.

### F2 / F3 — Batches 2 and 3 (template; tranche per F0a's rule)

Each repeats **F1a–F1j** unchanged, with these substitutions. Their content is deliberately not
pre-assigned: it depends on what F1's eval shows and on which claim_types F1's promotions opened.

- [ ] **F2** — tranche per F0a over the *updated* A8/A9/A10 output (re-run the audit first — the
      ranking moves as the graph grows); gold set grows by **1–3** live-verified questions (E7);
      `compare.py` baseline is **F1's accepted run**, not the P3b one; label `p4-batch2`.
- [ ] **F3** — same again; label `p4-batch3`. At its close, check the exit gate explicitly:
      **≥3 batches**, **≥4 canonical claim_types**, **all top-20-prominence subjects**, **gold set
      ≈25**, **floors enforced**, **overall ≥75% across 3 runs**. Anything unmet is either worked in
      an F4 or written down as a deferral — not quietly dropped.
- [ ] **F4+** — The loop continues past the gate (`§5`: "the loop continues after"). Additional
      batches follow the same template; the gate is a milestone, not a stopping condition.

---

## Track J — Docs / DEV entries / banners (pure prose — do anytime)

- [ ] **J1** — Log **one DEV entry per landed track** in `DEVIATIONS.md`, in the
      Stage/Original Plan/What Changed/Reason/Impact/Date format, **claiming whatever number is free
      when it lands** — the `DEV-102`…`DEV-108+` assignments above are indicative, reserved before any
      of this was built, and P3b's own numbering moved twice under exactly this assumption. The
      requirement is one entry per track, not these specific integers. Tracks **C** and **D** are new
      relative to `§5` and Track **B** builds what `§5` asserted already existed — each entry says so
      plainly rather than presenting them as planned work.
- [ ] **J2** — **Fix the stale group count where it appears.** "838 unreviewed groups" in
      `ADR-017:61`, `IMPLEMENTATION_PLAN_PHASE2.md:324`, `TODO2.md:389` and `TODO.md:113` — the
      measured figures are **839 total groups / 835 with zero promotions / 71 promoted rows in 4
      groups**. Per the deviation protocol, **do not overwrite the plan body** — add the correction as
      a banner and let this checklist's *Contracts* section be the live reference.
- [ ] **J3** — **Record the §5-vs-TODO2 tranche-priority conflict and F0a's resolution** in both
      documents, so the next reader does not re-derive it. `§5` step 1 is currently unamended.
- [ ] **J4** — **ADR-010 action items**: tick "Author the ~8 new gold questions" **at F3, not at E5**
      — E1–E5 is **five** questions (16 → 21), and reaching ADR-010's ~8 (and this stage's "≈25")
      needs E7's 1–3 per batch from F2 and F3 on top, landing somewhere in 23–27. Ticking it when the
      named backlog lands would close the item with a third of it unwritten. Also
      leave "numeric questions only if ADR-009 is accepted" open — ADR-009 flips at **P5a**, not here.
- [ ] **J5** — `TODO2.md` Stage P4: tick DEV-049 when Track A lands, tick each bullet as its track
      closes, and add the stage-closure banner in the P3b style (`> ✅ **STAGE CLOSED <date>.**` +
      the numbers + `> **Next: Stage P5**`) only when the definition-of-done below is genuinely met.
- [ ] **J6** — Add the `> ⚠️ Deviations occurred in this stage` banner extension to
      `IMPLEMENTATION_PLAN_PHASE2.md §5` naming this checklist, per the CLAUDE.md protocol step 4.
      Correct DEV-101's Impact field, which says "nothing committed" — it was committed as `2e4ce40`.

---

## Definition-of-done checklist (mirror of TODO2.md Stage P4)

- [x] **DEV-038** — `write_output` no longer clobbers promotion decisions. Landed 2026-07-28
      [DEVIATED - see DEVIATIONS.md #DEV-101], merge-on-write keyed on the claim 5-tuple; verified
      against the live file (71 promotions survive where 0 did before); 13 tests, ingestion suite
      green at 294; committed as `2e4ce40`.
- [x] **DEV-049** — zero-retrieval returns a parsed refusal, not `serviceError`; live-verified against
      `SOURCE_SILENCE_PHRASES`; `:core-api:test` green (Track A). **Closed 2026-07-28 as DEV-102**:
      does not reproduce on the live tree (root cause understood, not fixed — nothing to fix); see
      `DEVIATIONS.md` #DEV-102. Track E carries forward the open question of whether Q16/Q17's fixed
      text is still a valid zero-retrieval REFUSAL case.
- [ ] **≥3 batches end-to-end**, each a complete `seedgen → reseed → audit → runner --runs 3 →
      compare.py → commit-or-revert` pass, results dirs committed with their candidates, migrations
      and gold-set changes (Track F).
- [ ] **`variant_claims` covers ≥4 canonical claim_types** — from **2** today (`parentage`, `death`).
      **Counted in the seeded table after a reseed, not in the candidate file** (they differ: 71
      promoted candidates → 44 rows; see *Contracts*).
- [ ] **`variant_claims` covers all top-20-prominence subjects** — from **3** today (Aphrodite,
      Achilles, Io), measured against Track B's A8 ranking, and again counted **in the seeded table**.
      Because the A8 ranking shifts as Track H adds entities, **freeze the top-20 list from A8's first
      clean run into F0's record** and gate against that snapshot; re-ranking every batch makes the
      gate unfalsifiable. Note any subject that enters or leaves the live top 20 afterwards rather
      than silently re-scoping the target.
- [ ] **Gold set ≈25 questions** — from **16** today; ADR-010's backlog (Q16, Q17, Q19, Q20, Q21)
      authored with live-verified keywords; every pre-existing question retained as a sentinel.
- [ ] **Per-category floors enforced**, REFUSAL promoted off `null`, CONFLICT raised as the category
      grows; no floor ever lowered to make a run pass.
- [ ] **Overall ≥75% sustained across a 3-run eval** with **zero stable regressions**, on a run with
      no transport errors (Track D's banner clean).
- [ ] **GAP-001 a′** worked or explicitly deferred with a written waiver (F0b); **GAP-002** long tail
      worked or explicitly deferred with its bucket and reason (H6); **F0c**'s standing-waiver policy
      for A1/A6 residue decided in writing.
- [ ] **One DEV entry per landed track** logged in `DEVIATIONS.md` (indicatively DEV-102…DEV-108+;
      claim the numbers actually free at the time — J1); `TODO2.md`, `IMPLEMENTATION_PLAN_PHASE2.md §5`
      and ADR-010's action items annotated per the deviation protocol; the stale 838-group count
      corrected by banner, never by overwriting the plan body.
