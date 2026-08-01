# Stage P5 — Corpus-Complete Seeding

> ⚠️ Deviations occurred in this stage. See DEVIATIONS.md for details.
> This stage was re-scoped on 2026-07-30 `[DEVIATED - see DEVIATIONS.md #DEV-128]`. P5's original
> three sub-stages were *new data types* (P5a numeric, P5b myths, P5c geography/epithets). P5-0
> below — corpus-complete seeding of the tables that **already exist** — is inserted ahead of them
> and owns the stage. P5b is frozen. See `TODO2.md` Stage P5 for the roadmap-level view.
>
> **Corrected 2026-07-30, same day, before any track started** `[DEVIATED - see DEVIATIONS.md
> #DEV-129]`. A review against the live tree found seven defects in this checklist's own numbers and
> arithmetic. The four that changed the plan rather than a figure: the `variant_claims` denominator
> was unreachable by 36% (a **4,743-row ceiling**, so 6.3% not 4%); the group figures were
> **alias-blind** (838/749 → **795/723**); **Track D's exits were unreachable within Track D's own
> bound**; and **`A7` as written crashed every `python -m audit` invocation**, including Track A's
> own exit criterion. Corrections are inline and marked; nothing was silently overwritten. See
> **Track order** at the foot of this file — three items run out of sequence.
>
> **Corrected again 2026-07-30, same day, still before any track started** `[DEVIATED - see
> DEVIATIONS.md #DEV-130]`. A contradiction pass over this file against the live tree found five
> conflicts that blocked execution rather than misstating a figure: **A6 + E5 together un-waive 949
> findings**, pinning `python -m audit` at exit 1 for the whole stage against three separate
> green-suite gates (fixed — both sets are *relocated* to a backlog artifact with its own `DEFERRED`
> disposition, E5); **B7's evidence clause forbade C5 outright** (fixed — an explicit bucket-E
> carve-out, B7); **Track C's exit claimed an adjudication rate bucket Z excludes ~246 rows from**
> (fixed — the bucket-Z blocked register, C exit / F1); **A6's split table summed to 642, not 649,
> and named only 40 of the 47 keepers** (fixed — measured nine-way split, A6); and **A7a's prefix
> filter would have revoked 2 of the 47 verdicts it exists to protect** (fixed — the filter now keys
> off the revoke side, A7a). All five are corrected inline and marked.

---

## Context — why this stage exists

End goal: correctly seed everything the corpus makes available into the tables that already exist.

Measured at HEAD `65a9bb7` (2026-07-30):

| table | seeded | candidate pool | reachable ceiling | gate |
|---|---|---|---|---|
| `entities` | 1,990 | 2,594 raw / 1,990 confirmed | 2,337 name-space | curated list |
| `relationships` | 3,367 | 6,882 cleaned | 6,882 | **mechanical, no human gate** |
| `variant_claims` | 300 | 7,429 (tier1 328 / tier2 406 / tier3 **6,695 unreviewed**) | **4,743 rows** — see below | **per-row human gate (ADR-004)** |
| `myths` / `myth_participants` | 5 / 22 | none — nothing extracts them | n/a | hand-curated |

**The `variant_claims` candidate pool is not its reachable ceiling, and every coverage claim below is
stated against the ceiling.** `seedgen/variant_claims_gen.py::_reviewed_rows` applies two silent
filters (bare `continue`, no warning) after the trust-tier check: it drops rows whose
`subject_name` is absent from `entities`, and it collapses the 4-tuple `(subject, claim_type,
claim_value, source_id)` — which **omits `passage_ref`**, so the same claim attested in two passages
of one source seeds once. Simulating promotion of all 7,429 candidates through that exact filter:

```
7,429 candidates
  −  359  subject absent from entities
  −2,327  collapsed by the 4-tuple dedup (multi-attestation within one source)
= 4,743  rows -- the hard ceiling. Max "seeded ÷ candidates" is 63.8%, never 100%.
```

So the differentiator table sits at **300/4,743 = 6.3% row coverage** (not 4% — that figure divides
by an unreachable denominator) and **8.1% conflict-group coverage**: 62 of 764 candidate groups that
are surfaceable conflicts (≥2 distinct `source_id` **and** ≥2 distinct `claim_value`) have a
promoted surfaceable conflict. Of all 795 alias-resolved `(subject, canonical claim_type)` groups,
**723 have zero promoted rows**.

> ⚠️ Earlier drafts of this file, `TODO2.md` and DEV-128 quoted **838 groups / 749 zero-promoted**.
> Those are the **alias-blind** figures — `build_group_inventory(cands, {}, None)`, i.e. no
> `claim_type` normalization and no entity-alias resolution. A10 as it actually runs reports
> **795 / 723**. Corrected 2026-07-30. Under that one consistent grouping: **795** total groups,
> **764** of them surfaceable conflicts, **62** promoted, **715 reachable** after the entity filter —
> i.e. **93.6% of surfaceable groups are reachable where only 63.8% of rows are**, which is why
> Track A's headline is group-based, not row-based.

Seeded counts are `grep -cE "^\s*\("` over V10/V11/V12 and agree with the live DB exactly.
**A16 replaces this whole table on first run** (Track A), because hand-quoted counts are exactly
what goes stale — as the alias-blind figures above demonstrate. **All figures above are
pre-P6 (2026-07-30 baseline)** `[DEVIATED - see DEVIATIONS.md #DEV-149]` — candidate pool
7,429 → 9,096; `entities` 1,990 → 1,995; edge coverage 48.9% → 49.1%; group space 795/715 →
see C1's figure note. A16 re-derives everything on first run of batch 4.

### The drift is real and measurable

From `ingestion/audit/promotion_log.json` (13 batches):

- **2026-07-28** (P4 tracks F0–F3): **253 rows promoted**, 120 rejected — real coverage gain.
- **2026-07-29 → 07-30** (7 commits; checks A12–A15 plus two rounds of fixes *to those checks*):
  **4 rows promoted, 286 rejected.** The user-visible DB gained 4 rows in two days.
  (Rejection writes `trust_tier=2` — 1 = promoted, 2 = checked-and-rejected, 3 = never reviewed, and
  120 + 286 = 406 = exactly today's tier-2 count. An earlier draft said "every rejected row at
  `trust_tier=3`", which is both the wrong tier and a tautology: a rejected row can never seed, by
  definition. The load-bearing point is not that the rejections didn't seed — it is that **only 4
  promotions did**, which is what the seeding rule's "rejection is not coverage" clause encodes.)
- A13 was built, measured at 82% false positives, and recorded as a dead end (DEV-123).
- DEV-126 / DEV-127 fixed bugs *in the checks* (alias-blindness, failed-open drift guard, dedup
  keying). The detector suite has become its own maintenance surface.

### Root cause: the scoping axis, not discipline

P4's tranche rule (F0a, DEV-109) scopes review by **subject prominence**. Major figures are named
everywhere in the corpus, so subject-scoping pays nearly the full corpus-reading cost for a fraction
of the rows:

| scoping axis | passage reads | tier-3 rows reached | rows per read |
|---|---|---|---|
| top-20 subjects (**the current rule**) | 750 | 2,544 | 3.4 |
| top-100 passages | 100 | 2,229 | 22.3 |
| top-250 passages | 250 | 3,673 | 14.7 |
| **all passages** | **1,059** | **6,695 (100%)** | **6.3** |

*Method for the subject row, recorded per Track E3 so it can be re-derived rather than re-quoted:*
top 20 by `composite` from `audit/prominence_ranking.json`, matched against tier-3
`subject_name` through `claim_direction.load_name_aliases`. Alias resolution changes nothing here
(2,544/750 either way). Earlier drafts quoted **2,621 / 753**, which no construction reproduces —
closest are top-21-by-composite (2,601/758) and top-20-by-`mentionCount` (2,590/**753**). The
conclusion is unaffected under every construction: **the passage axis reaches 2.6× the rows for 1.4×
the reads.**

**The backlog was never 6,695 units of work. It is 1,059 passage reads** — but state the absolute
cost honestly, because Track C's exit demands all of it: those 1,059 segments are **2,544,525
characters ≈ 424,000 words**, median segment 2,504 chars, out of 1,204 total corpus segments. Track C
is a close read of ~88% of the corpus. Subject-scoping made a finishable job look infinite; review
ran out of cheap subjects and detector-building filled the vacuum. The same rule *forced* DEV-119 to
waive 602 of 649 A6 dropped-parent rows as "outside the frozen tranche" — a backlog mislabelled as a
waiver. (The other 47 were judged on their merits; see Track A6.)

### Decisions taken (2026-07-30, recorded in DEV-128)

1. **Review gate** — passage-batched review **plus** evidence assist. Requires an ADR-004 amendment.
2. **Coverage target** — the **full pool** (all 1,059 passages), worked highest-yield first.
3. **`myths` / `myth_participants`** — **frozen** with a written coverage statement, superseding
   P5b's "grow beyond 5 myths". No extraction pass.

---

## Standing rules for this stage

*These govern every track below. Both are also mirrored into `TODO2.md`'s cross-cutting rules,
because they apply beyond P5.*

### The seeding rule

> **The seeding rule.** Every **seeding batch** names, before it starts, the table it will add rows
> to and the row count it expects. A batch closes only on a re-run of `python -m audit --only A16`
> showing that table's coverage moved; the before/after figures go into the batch's own entry in
> `ingestion/audit/promotion_log.json` alongside `batchLabel`/`keys`/`rejectedKeys`.
>
> **Scope — the two clauses below have *different* reach, and conflating them was a defect**
> `[DEVIATED - see DEVIATIONS.md #DEV-132]`. **The batch-closing requirement** (name the table and
> row count up front; close on a coverage move) applies **only to seeding batches** — items that
> write rows to a user-visible table, i.e. Track C and Track D. Instrument, engine, retire and close
> items (Tracks A, B, E, F) add no rows; they name the seeding work they unblock instead. Without
> that limit the rule reads as violated by 33 of this stage's 43 items on day one — **39 of 50 since
> DEV-150**, which added five B items and one F item, all row-free, plus one seeding item (C0).
> **The detector budget below applies to every track, including A, B, E and F** — its whole purpose
> is to bound work that adds no rows, so exempting the row-free tracks would empty it.
>
> **Detector budget:** at most one new `audit/` check module per 250 net rows added to a
> user-visible table since the last one. Fixing a bug *in* an existing check spends the same budget
> — that maintenance surface is what this rule bounds.
>
> **Two standing exemptions, both narrow, because the budget genuinely does reach Track A.**
> **(a) A check that cannot emit a finding is an instrument, not a detector, and does not spend the
> budget.** A16 is the only such module today (Track A1 fixes its `findings=()` return as a design
> constraint). Without this the budget forbids A16 — 0 net rows have been added since A15 — and A16
> is the stage's serial gate, so the stage could not start without breaking its own rule.
> **(b) A9 is this stage's one budgeted bugfix, granted here and not renewable**
> `[DEVIATED - see DEVIATIONS.md #DEV-132]`. A9 corrects a placeholder leak in checks A2 and A8, and
> "fixing a bug *in* an existing check spends the same budget" would forbid it at 0 net rows —
> deadlocking the stage a second way, since D1's bound and E2's tiebreak both rank on that output.
> The grant is explicit rather than implied by scope, so the budget still bites on check number 17.
>
> **Rejection is not coverage.** Writing `trust_tier=2` shrinks the backlog and is worth doing,
> but it reports against the *decided* fraction, never the *seeded* one, and can never satisfy a
> batch's exit criterion alone.
>
> **A correction is coverage** `[DEVIATED - see DEVIATIONS.md #DEV-150]`. A row authored into
> `claim_corrections.json` from an open segment (ADR-023, B11) is a seeded row and counts exactly
> like a promotion. Every batch reports **corrections authored ÷ `reversed_direction` rejections**,
> and a batch whose reversed-direction rejections exceed its corrections names why in its rationale.
> Without this clause the one above makes a reversal-heavy batch read as pure loss — and a batch
> would rationally respond by adjudicating *around* reversals rather than correcting them, which is
> the drift the clause above exists to prevent, arriving by the other door.
>
> **A batch's audit gate is exit 0 with a non-growing deferral count**, not exit 0 alone
> `[DEVIATED - see DEVIATIONS.md #DEV-130]`. Scope-shaped waivers relocate to E5's backlog artifact,
> whose findings report `DEFERRED`: excluded from `AuditRun.exit_code`, counted per check on every
> run. So a batch that adjudicates nothing still exits 0 — read the deferral counts, which must be
> strictly lower for the checks the batch touched and never higher for any check.

The last clause is what would have caught 2026-07-29/30.

**Coverage is always quoted against the reachable ceiling, never the raw candidate pool.** The
`variant_claims` ceiling is 4,743 of 7,429 (see Context above); ~35% of the adjudication effort in
Track C produces no DB row for reasons that have nothing to do with the reviewer's decision. A
denominator nobody can reach makes every batch look like a failure and hides real progress.

### The findings rule

The gap this closes: the repo already has a strong convention for *recording* stray findings (the
"Findings this pass did not fix" sections; the DEV-115/119/121/122 discipline). Nothing decides
whether to **act** on one — and the observed behaviour is to record it, then fix it in the very next
commit. That loop is the drift, in one sentence.

> **New findings are routed, not chased.** Every pass over the data surfaces defects that are not
> the one being worked. Classify each, in this order:
>
> 1. **Reaches users now** — the defect is in *seeded* data, which is not review-gated (the
>    GAP-007 / GAP-008 shape). **This is the only class that interrupts the batch.** Fix, reseed,
>    continue.
> 2. **Blocks the rows in front of you** — the current passage cannot be decided without it (e.g. an
>    alias gap leaves the claim's subject unresolvable). Fix inline, minimally, for the rows in hand
>    only. If the fix outgrows the batch, it is demoted to class 3.
> 3. **Affects rows the queue has not reached yet** — record it against the passage or queue
>    position where it will be met, and keep going; the queue brings it back on its own.
>    **Most findings are class 3, and treating them as class 1 is precisely the drift.**
> 4. **Would need new tooling to find systematically** — record as a candidate detector in
>    `docs/DATA-GAPS.md` with a stated row-yield hypothesis. It spends the detector budget, is never
>    built mid-batch, and if its first sweep promotes nothing it is recorded as a dead end (the A13
>    precedent) rather than iterated.
> 5. **Mechanically undetectable** (the GAP-005 in-narrative-deception shape) — straight to
>    "Known and accepted". Do not design a detector for it.
>
> **A16 is the arbiter.** A proposed interrupt that would not move a coverage number for the table
> being worked is not an interrupt.
>
> **One destination.** Classes 3–5 land in `docs/DATA-GAPS.md` with a "rows at stake" line, so
> recording is not losing. Class 1–2 fixes are named in the batch's `promotion_log.json` rationale.
>
> **Amendment (2026-08-01) — a class-2 finding may interrupt when the loss is irreversible**
> `[DEVIATED - see DEVIATIONS.md #DEV-150]`. Class 1 stays the only class that interrupts *on the
> strength of live bad data*. A class-2 finding may also interrupt, and only if all three hold:
> **(a)** the defect destroys information the batch had on screen, so the loss is taken at write time
> rather than discovered later; **(b)** the passage leaves the queue in the same act, so the queue
> cannot bring it back — the class-3 escape hatch is genuinely unavailable, measured, not assumed;
> and **(c)** the per-batch rate of loss is stated with its construction. B9–B13 is the case this was
> written for and the only one so far. **Class 4's "never built mid-batch" is amended in the same
> narrow way and for the same reason** — tooling whose absence is what makes the loss irreversible.
> **Why this is an amendment and not a reading of the rule:** the original B9–B13 justification
> claimed the queue never returns to *any* of the 639 standing rejections. That is false (252 of 268
> passages are still queued; 390 rows come back for free), and clause (b) is what makes the
> difference between the standing backlog — class 3, correctly — and everything written from here on.
> Without the amendment stated, the next class-2 finding inherits an interrupt precedent that the
> rule text forbids, which is the drift the rule exists to stop.

This composes with the existing cross-cutting rule *"Root cause first, code fix only if still
needed"* — that rule governs **how** to fix; this one governs **whether to fix now**. Applied
retroactively, DEV-125 through DEV-127 were all class 3 or 4 treated as class 1.

---

## Track A — Instrument and freeze

*Nothing else starts until "are we drifting?" is answerable in one command.*

- [x] **A1** — Write `ingestion/audit/coverage.py`, `NAME = "A16"`. Sibling of `prominence.py` (A8)
      and `group_inventory.py` (A10); conforms to `ingestion/audit/contract.py` (auto-discovered via
      `NAME` + `run()`, no registration). **Must always return `CheckResult(findings=(), summary=...)`**
      — it is data, never a defect, so it can never accumulate waivers or gate `seedgen`.
- [x] **A2** — Metrics. Numerator from the live DB (`_connect_db()` in `audit/__main__.py`),
      denominator from `ingestion/extraction/output/`. **State the layer in every summary line**
      (the existing cross-cutting rule). **Every metric must pass the alias maps** — A10 reports
      795 groups with them and 838 without, and the alias-blind pair is what went into DEV-128.

      | table | metric | today | reuse — do not re-derive |
      |---|---|---|---|
      | `entities` | seeded ÷ (seeded + distinct unknown names in candidate relationships) = **name-space coverage** | 1,990/2,337 = 85.2% | `drop_accounting.compute_drop_accounting(...).unknown_names` |
      | `relationships` | seeded ÷ cleaned candidates, with the A2 four-way drop split printed beneath | 3,367/6,882 = 48.9% | the same `DropAccounting` object |
      | `variant_claims` | **headline: conflict-group coverage** — groups with ≥2 distinct `source_id` **and** ≥2 distinct `lower(trim(claim_value))`, promoted ÷ **reachable** | **62/715 = 8.7%** (pool 764 printed beside it) | `group_inventory.build_group_inventory` |
      | `variant_claims` | secondary: *decided* fraction = (tier1 + tier2) ÷ all candidates | 734/7,429 = 9.9% | — |
      | `variant_claims` | secondary: row coverage **÷ the 4,743 reachable ceiling**, never ÷ 7,429 | 300/4,743 = 6.3% | new — see A2a |
      | `myths` / `myth_participants` | `n/a (frozen — see DATA-GAPS.md coverage statement)` | — | — |

      Group coverage is the headline, **not** row coverage: rows are gameable by promoting six
      epithets of one god, and the row denominator is unreachable by 36% (A2a).
      **The headline divides by 715, not 764** `[DEVIATED - see DEVIATIONS.md #DEV-132]` — the
      reachable group ceiling from A2a, per this stage's own "always against the reachable ceiling,
      never the raw candidate pool" rule, which the first draft of this row broke while the row
      secondary two lines down obeyed it. Print the pool beside it (`62/715 = 8.7%, pool 764`) so
      both numbers are visible and the stage's terminal target is legibly **715/715**, not 715/764.
      **715 is pre-P6** `[DEVIATED - see DEVIATIONS.md #DEV-149]` — the reachable group count moved
      with the 9,096-row pool; A2a re-derives the actual terminal target. See C1's figure note.

      Two layer notes that will otherwise read as contradictions on first run:
      - The `entities` **denominator is the reference name-space (2,337), not the 2,594 raw
        candidates** — two different denominators for one table, so label the line.
      - The four-way drop split needs `db_conn` too: `compute_drop_accounting` without the
        `claim_type`/`relation` alias maps computes `seeded_count = 3,485`, which will not match the
        live 3,367 headline. A2's existing drift check already depends on passing them — do the same.
- [x] **A2a** — Report **both `variant_claims` ceilings**, since they are the numbers that decide
      whether a batch "failed" `[DEVIATED - see DEVIATIONS.md #DEV-132]`:
      - **rows:** `candidates → −(subject absent from entities) → −(4-tuple dedup collapse) →
        seedable`. Today: `7,429 → −359 → −2,327 → 4,743` (63.8%).
      - **groups:** the same filter applied at group granularity → **715 of 764** surfaceable-conflict
        groups reachable (93.6%). **This one is not optional** — it is the denominator of A2's
        headline metric and the figure Track C's honest-ceiling paragraph cites as "the 4,743-row /
        715-group figure from A2a". As first written this item specified only the row derivation
        while three other places already depended on the group number.
      Reuse `seedgen.variant_claims_gen._reviewed_rows` against a tier-blind copy of the candidates
      rather than reimplementing the filter, so neither ceiling can drift from what seedgen does.
- [x] **A3** — Emit `coverage.json` from `run()`. **`coverage_history.json` is appended only from a
      `main()`/`--out` CLI path, never from `run()`** `[DEVIATED - see DEVIATIONS.md #DEV-132]`, and
      that split is the whole point: `coverage.json` is a *report* — re-running reproduces it and
      nothing compares against the previous value — while an appended history is **accumulated
      committed state**, which is what DEV-127 caught A10 failing open on. As first drafted, A3 had
      `run()` append the history and then asserted "A16 writes a report, not a tracker", which the
      append contradicts; appending is also strictly worse than overwriting here, since a bad run
      silently extends the series instead of being reproducible away. Every other `write_text` in the
      package already sits behind a `main()` `--output` argument (DEV-127 finding 1b) — match it, and
      A16 stays the findings-free instrument A1 requires. Commit today's baseline.
- [x] **A4** — Append the **seeding rule** to `## Cross-cutting rules` in `docs/TODO2.md`. *Landed
      2026-07-30 with this checklist (DEV-128), ahead of the rest of Track A, because it is the
      guard that stops further drift while the work proceeds.*
  - [x] **A4a** — Mirror as a 3-line pointer in `ingestion/audit/README.md` under `## Design notes`
        (where check-authors actually read).
  - [x] **A4b** — One bullet in `CLAUDE.md`'s **Key Tech Guardrails**.
- [x] **A5** — Append the **findings rule** to `## Cross-cutting rules` in `docs/TODO2.md`. *Landed
      2026-07-30 with this checklist (DEV-128), same rationale as A4.*
- [x] **A6** — **Move** the **602 scope-shaped A6 waivers** out of
      `ingestion/audit/audit-waivers.json` and into E5's backlog artifact `[DEVIATED - see
      DEVIATIONS.md #DEV-130]`. They were waived for being outside a frozen tranche — that is a
      backlog, not a waiver. They become the Track C priority label.
      **Relocation, not deletion, and the distinction is load-bearing:** `AuditRun.exit_code`
      (`audit/__main__.py:104`) returns 1 on any finding that is neither waived nor deferred, and
      waivers are the only thing suppressing these 602 today. Deleting the entries outright makes A6
      emit 602 unwaived findings on every run, which pins `python -m audit` at exit 1 until Track C
      has adjudicated all of them — against Track A's own exit criterion and against the gate at the
      foot of *every* Track C batch. E5's `DEFERRED` disposition is what keeps the suite green while
      the count stays visible and shrinking; A6 must not run before it exists.
      **Do not touch the other 47.** Measured split of the 649 — construction: load
      `audit-waivers.json`, filter `check == "A6"`, partition on
      `reason.startswith(("F0b", "F0c"))`:
      | reason prefix | count | disposition |
      |---|---|---|
      | `F0b/F0c (Stage P4 Track F0, DEV-109): …` | **602** | move to backlog — scope-shaped |
      | everything else — DEV-119 / DEV-122 per-row triage verdicts | **47** | **keep as waivers** |
      The 47 break down nine ways, not four: `the dropped rival is ALREADY represented` **15**,
      `the cited passage contains NO parentage claim` **15**, `already reviewed and REJECTED` **7**,
      `a GENUINE variant tradition` **3**, `a NEW extraction-error shape` **2**,
      `reversed direction — the named 'parent' …` **2**, `the claim is TRUE but reaches us under a…`
      **1**, `GAP-007 / DEV-122: not a lost rival parent…` **1**, `DEV-122: the rival is real and
      correctly extracted, but the CHILD is a…` **1**. **The last two do not carry the `A6 triage`
      prefix at all** — which is why A7a keys its filter off the revoke side (A7a).
      All 47 are per-row judgements against cited passages, not deferrals. They stay in
      `audit-waivers.json` as waivers — moving them to the backlog would re-open rows that were
      already decided, and deleting them would discard real review work outright.
      Two earlier statements are corrected here: DEV-128's claim that all 649 share one stated
      reason, and DEV-129's four-row table, whose rows summed to **642** and which described all 47
      keepers as `A6 triage`-prefixed when only 45 are.
- [x] **A7** — **Move every scope-shaped waiver out first (E5 for the 347 A2 entries, A6 for the 602
      A6 entries), or A7 breaks the whole suite.** `load_waivers` (`audit/__main__.py:52`) **raises
      `ValueError`** at load time and is called unconditionally at line 199, *before* `--only`
      filtering. So the moment it rejects scope-shaped waivers while the 347 A2 entries
      (`F0c … GAP-002's unknown-name long tail`) are still in the file, **every** `python -m audit`
      invocation dies — including `python -m audit --only A16`, which is this track's own exit
      criterion, and every step of Track C's per-batch loop. A7 therefore lands only once
      `audit-waivers.json` holds **zero** `F0b`/`F0c`-prefixed entries, at which point the filter is
      a guard against reintroduction rather than a change of behaviour. Order: **E5 → A6 → A7.**
  - [x] **A7a** — Implement the scope-shaped filter as an **allow-list on the revoke side**: reject a
        waiver iff `reason.startswith(("F0b", "F0c"))` `[DEVIATED - see DEVIATIONS.md #DEV-130]`.
        **Do not key it off the keep side.** 2 of the 47 A6 entries that must survive begin
        `GAP-007 / DEV-122:` and `DEV-122:` rather than `A6 triage`, so a "keep iff the reason starts
        with `A6 triage`" filter revokes two real per-row verdicts. That is the exact misfiling
        DEV-129 recorded as a *future* risk (finding 3) — it is already present in today's file, and
        keying off the revoke side removes it without needing the structured `scope: true` field that
        finding proposed. Unit test both directions in `ingestion/audit/tests/`, asserting explicitly
        that **all 47 non-`F0b`/`F0c` A6 entries survive, the two `DEV-122` ones by name.**
        **Corrected during implementation** `[DEVIATED - see DEVIATIONS.md #DEV-133]`: "iff
        `reason.startswith(...)`" alone is a blind reason-prefix scan, not check-scoped — 92 waivers
        under `A1`/`A4`/`A10` also start `F0b`/`F0c` for unrelated, genuinely permanent dispositions
        (verified live: 82/9/1) that this wording would have wrongly rejected too. Landed as
        `SCOPE_SHAPED_WAIVER_CHECKS = ("A2", "A6")` gating the match instead.
- [x] **A8** — A3's 86 candidate-layer cycles (verified at HEAD: `A3: FINDINGS -- candidates: 86
      parent_of cycle(s); db: 0 parent_of cycle(s)`): state once in `ingestion/audit/README.md` that
      the candidate layer is expected to be cyclic and the DB is the gated layer (the seeded graph is
      measurably acyclic since DEV-118), then stop carrying the count as an open item. This also
      resolves the DEV-066 homelessness that `TODO2.md` P5 flagged — the non-exhaustiveness is
      documented in A3's own output rather than fixed with Johnson's algorithm.
- [x] **A9** — Fix the `<UNKNOWN>` placeholder leak before anything ranks on A8 or A2 output. It is
      **rank 19 by `composite` in `audit/prominence_ranking.json`** — so it was one of the 20
      subjects P4's F3 "closed 20/20" — and simultaneously the **#1 entry in A2's unknown-name list
      at 133 references**, where it consumes the highest-value slot of Track D1's budget. It also
      heads the unseedable `variant_claims` subjects at 101 tier-3 rows. Exclude
      `<UNKNOWN>`/`<none>`/empty from both rankings at source, so no downstream tranche or budget
      spends a slot on a token that can never become an entity.

**Exit:** `python -m audit --only A16` prints all six metric lines (four tables; `variant_claims`
carries a headline plus two secondaries) plus the A2a ceiling derivation; baseline committed;
`audit-waivers.json` holds **zero** `F0b`/`F0c`-prefixed entries **under `A2`/`A6`** and all 47 A6
triage verdicts, so no *waiver* records a scoping decision — **which requires both E5 and A6 to have
run**, per A7. **Corrected** `[DEVIATED - see DEVIATIONS.md #DEV-133]`: unqualified "holds zero
`F0b`/`F0c`-prefixed entries" is false on the live file by design — 92 entries under `A1`/`A4`/`A10`
carry that prefix for unrelated, permanent dispositions and are meant to stay; only the `A2`/`A6`
subset is what this stage relocates.
**Both `python -m audit` (full suite) and `python -m audit --only A16` exit 0**, with the 949
relocated findings (602 A6 + 347 A2) reported `DEFERRED` and their per-check counts printed
`[DEVIATED - see DEVIATIONS.md #DEV-130]`. **Corrected** `[DEVIATED - see DEVIATIONS.md #DEV-134]`:
`--only A16` exits 0; the full suite does not, and no item in this track changes that — `A3`'s 86
candidate-layer cycle findings have never carried a waiver (a pre-existing condition this item's own
text measures at HEAD), and A8's fix is documentation, not a disposition change. "Both exit 0" does
not survive contact with A8 as actually written; Track A's real gate is `--only A16` exiting 0 plus
the deferred-count bookkeeping, not the full suite's exit code.

**"Exit cleanly" here means exit code 0, not merely "does not crash"** — the earlier wording was
ambiguous in a way that hid a real conflict. `AuditRun.exit_code` (`audit/__main__.py:104`) returns 1
on any finding that is neither waived nor deferred, so relocating 949 waivers *without* E5's
`DEFERRED` disposition would fail this gate, and Track C's per-batch gate, for the remainder of the
stage — no item in this checklist could then close. E5 is a prerequisite for that reason as much as
for A7's crash.

---

## Track B — Build the review engine

- [x] **B1** — New `ingestion/extraction/claim_evidence.py`. It **exposes no `NAME`**, so
      `discover_checks()` never picks it up — it cannot emit findings, cannot gate `seedgen`, cannot
      grow `audit-waivers.json`. That is the structural answer to the detector suite having become a
      maintenance surface, and it holds **wherever the file lives**: `discover_checks()` skips on the
      attribute check, not on the directory (`audit/__main__.py:47`), so an `audit/`-resident module
      without `NAME` is equally inert. An earlier draft gave the `NAME` mechanism as the reason for
      the *location*, which does not follow. The actual reason for `extraction/`: this is review
      tooling that reads candidates and corpus segments, the same job as its neighbours there, and
      `audit/` is the package whose growth this stage is trying to stop.
      **Found during implementation** `[DEVIATED - see DEVIATIONS.md #DEV-135]`: `extraction.run_extraction`
      is imported lazily inside `build_passage_queue`, not at module level — a module-level import
      transitively pulls in `extraction.claim_extractor`, which reads `ANTHROPIC_API_KEY`/`EXTRACTION_MODEL`
      from the environment at import time, so merely `import`ing this review-tooling module (including its
      own unit tests) would fail without live Anthropic credentials for no reason connected to what it does.
- [x] **B2** — Import rather than reimplement, and **adapt between two alias-map shapes that are not
      interchangeable** — passing one where the other is expected raises `TypeError` inside
      `_spellings` at `{name} | aliases.get(name, set())`:
      | import | from | shape |
      |---|---|---|
      | `_attests` / `_spellings` | `audit/parentage_direction.py` (A11) | consume `dict[str, set[str]]` — canonical → corpus spellings |
      | `load_aliases` | `audit/parentage_direction.py` | produces `dict[str, set[str]]`, **DB `entity_aliases` only** |
      | `parse_parent` | `audit/claim_direction.py` (A14) | consumes `dict[str, str]` |
      | `load_name_aliases` | `audit/claim_direction.py` | produces `dict[str, str]` — surface → canonical, `known_aliases.json` **+** DB |
      Build one map and invert it explicitly. Prefer `load_name_aliases` as the source of truth (it is
      the only one carrying the curated JSON layer) and invert to `canonical → {surfaces}` for
      `_attests`; **do not** feed `load_aliases` alone to anything that adjudicates, or the JSON layer
      is invisible — which is DEV-126's bug shape.
  - [x] **B2a** — **Cross-check `entity_aliases` against `known_aliases.json` before B3 runs.** This
        is DEV-126 finding (5), still open, and B3's bucket D is a direct function of it: a subject
        present in the corpus under a spelling that only one layer knows lands in D and looks like a
        misattribution. Report the symmetric difference; it is a prerequisite for C5, not a nice-to-have.
- [x] **B3** — Bucket each tier-3 row by attestation **within its own cited passage segment** (not
      the whole source — that distinction is what made A13 useless at 82% noise). Verified feasible:
      **all 1,059 tier-3 `(source_id, passage_ref)` pairs resolve against `build_segment_map`** —
      zero unresolvable refs across all six sources — so no row is unbucketable for want of a segment.
      - **Z** — **subject absent from `entities`** → cannot seed whatever the verdict is; classify
        *before* reading, never queue for a read. 354 rows / 39 subjects today. Split three ways:
        **108 rows are junk subjects** (`<UNKNOWN>` 101, `<none>` 3, empty 4) → **reject
        mechanically at `trust_tier=2`** — a subject that can never become an entity is a decidable
        row, not a blocked one; **80 rows** belong to names D4 rules out of scope (Ascalaphus 22,
        Thoas 14, Hippolytus 13, Electra 11, Oenomaus 8, Phineus 7, Eurytus 5) → **enter the
        bucket-Z blocked register**, do not read; the rest (incl. `Helios`, 10 rows) → hold for
        Track D and re-queue once the entity exists, entering the register only if D1's bound never
        reaches them.
      - **The bucket-Z blocked register** `[DEVIATED - see DEVIATIONS.md #DEV-130]`: rows that stay
        at `trust_tier=3` because a *decision taken elsewhere in this stage* makes them unseedable,
        each entry naming the blocking decision (D4's namesake exclusion, or an entity outside D1's
        60-name bound). It is deliberately narrow — a row whose subject could exist and is simply
        unreached does not qualify — and it exists because Track C's exit would otherwise claim an
        adjudication rate the Z classification excludes ~246 rows from. It is a queue with a stated
        blocker, not a waiver: E6 gives it a "rows at stake" line like every other backlog.
      - **A** — forward reading attested verbatim, reverse never → batch-confirmable with its matched span
      - **C** — both names present, no kinship formula → genuine read required
      - **D** — one name absent from the cited passage. **Two causes, not one, and the bucket cannot
        tell them apart**: an alias gap (the name *is* there, spelled otherwise) or a genuine
        misattribution. Therefore D is **read-required, not rejection-leaning**, until B2a has run;
        after B2a an alias-clean D is rejection-leaning **on an opened segment, and is never
        batch-rejected at all** — B7's carve-out reaches bucket E only, because one party *is*
        attested here.
      - **E** — neither name present → **rejection-leaning** `[DEVIATED - see DEVIATIONS.md
        #DEV-130]`. Two routes, and both are legitimate: **inside a normal Track C passage batch the
        segment is already open** for that passage's C/D/unparsed rows, so its E rows are decided
        per-row on an opened segment like any other — B7 constrains *batch rejection without an
        opened segment*, not review. The **unopened** route is C5's budgeted one-time sweep across
        passages the queue never reached, which is what B7's carve-out exists for and which is
        budgeted as a denominator win under the seeding rule. Either way an E row leaves tier 3.
      - unparsed → read
- [x] **B4** — Emit the passage-ordered work queue. **Primary sort:** count of A6-contested rows in
      the passage — those rows *are* conflicts by construction, since the contested collapse only
      fires on ≥2 competing parents. **Secondary:** total rows in the passage.
- [x] **B5** — Add `review_passage(source_id, passage_ref)` to
      `ingestion/notebooks/02_verify_conflicts.ipynb`, beside the existing `review_group`. Reuse
      `build_segment_map` (already in the notebook) and the `_CLAIM_IDENTITY` 5-tuple imported from
      `run_extraction` — same keys, same `approved_keys` / `rejected_keys` emission, same additive
      tier-1/tier-2 write (never demote), same `promotion_log.json` append. One read, N adjudications.
- [x] **B6** — Unit tests for the bucketing, alongside the existing
      `audit/tests/test_parentage_direction.py` / `test_claim_direction.py`.
- [x] **B7** — **ADR-004 Amendment 1** in `docs/adr/adr-004-seed-data-extraction-strategy.md`. Follow
      the ADR-014 amendment precedent; ADR-004 owns the gate, so amend rather than write a new ADR.
      Define what "explicit per-row developer review" means operationally:
      - Every promoted row is displayed with its `claim_value` **and** the verbatim span from its own
        cited passage that pre-verification matched — or the full segment when nothing matched.
      - The approval *action* may cover many rows at once, provided every row was displayed with its
        evidence and every row is recorded individually in `promotion_log.json`.
      - **The pre-verification signal may order and annotate; it may never promote.** No code path
        writes `trust_tier=1`.
      - A row whose evidence line reads "no match" may not be **approved** in a batch — it requires an
        opened segment.
      - **The same rule binds batch rejection.** A rejection is a recorded per-row verdict written to
        `trust_tier=2` and marked `[ALREADY REJECTED]` for every later reviewer, so it is a decision
        of the same weight as a promotion, not the absence of one. A row whose evidence line reads
        "no match" therefore may not be batch-*rejected* either. Without this clause the amendment
        permits wholesale rejection on precisely the evidence it forbids promoting on.
      - **One carve-out, stated as a condition on the segment and not on the reviewer's confidence**
        `[DEVIATED - see DEVIATIONS.md #DEV-130]`. Where **neither** party is attested anywhere in
        the cited segment under any spelling either alias layer knows — B3 bucket E, and only after
        B2a reports the layers clean — **the absence is itself the displayed evidence**, and the
        batch may reject. Where **one** party is attested and the other is not (bucket D), it may
        not: that asymmetry is the alias-gap-vs-misattribution ambiguity B2a exists to resolve, and
        an opened segment is the only thing that settles it.
        **Without this carve-out the clause above forbids C5 outright** — bucket E is *defined* as
        "neither name present", so every bucket-E row's evidence line reads "no match" by
        construction, and gating C5 on B2a does not change that. DEV-129 noticed the tension and
        resolved it with the B2a gate; the gate is necessary but was never sufficient.
      - Rationale to record: ADR-004 already calls the notebook "a sufficient review UI for a PoC"
        (`adr-004…md:119`) and rejects a review web app as over-engineering. This amendment keeps
        that, and removes only the per-row *re-reading*, which was never the guarantee.
- [x] **B8** — Update the `CLAUDE.md` "Review-gated `variant_claims`" guardrail so "per-row"
      survives but "one at a time" is not implied. Log a DEV entry per the deviation protocol.

**Exit:** `review_passage('apollodorus-bibliotheca', '3.12.5')` prints the segment once with every
row annotated by bucket and emits pasteable keys. **B7 merged before any batch approval is used.**

### B9–B13 — the rejection half of the engine (reopened 2026-08-01, before C1 batch 10)

`[DEVIATED - see DEVIATIONS.md #DEV-150]` — see **ADR-023** and **GAP-012**.

B1–B8 made the engine efficient at *deciding* rows and left it unable to *write* anything but a
verdict. Three losses follow, all measured on the live pool (9,096 candidates, 639 at `trust_tier=2`;
construction is `extraction/rejection_audit.py`, B9):

- a rejection records **no reason**, so `reversed_direction` (a correctable error) is
  indistinguishable from `not_in_passage` (nothing to recover) and from `wrong_subject_namesake` (an
  entity problem) across all 639 rows;
- of 581 rejected `parentage` rows, **560 yield a derivable inverse key** (the other 21 are
  uncheckable by this join, not negative). Of those 560 the corrected inverse row is attested at the
  same passage for only **34**; exists only at a *different* passage for 243 (the citation is lost);
  and is **absent from the whole pool for 283 — 51% of the 560** — of which **101** would be seedable
  today and 182 wait on Track D. The four figures partition the 581 (`34 + 243 + 283 + 21`).
  Re-extraction does not recover them: A14's rule fires only where the source attests the reversed
  reading and never the correct one, so the same model reproduces the same reversal;
- **162** rejected claims still have their mirror `parent_of` edge in
  `relationships_candidates_cleaned.json`, which has **no human gate** and flows into V11 — GAP-012.

**Findings-rule classification, and the amendment this needs, stated because the rule governs whether
this interrupts.** The 162 mirror edges are **class 1** (may reach users now, the GAP-011 shape on a
new seam), but they do **not** carry the interrupt on their own: A16 is the arbiter and an unsorted
162 moves no coverage number (GAP-012 says so in as many words). The untyped rejection and the
missing correction channel are **class 2** for every batch from C1 batch 10 on — and the rule as
written says class 1 is *the only class that interrupts*, so **this is an amendment to the findings
rule, not an application of it**, and it is recorded as one: see the *Cross-cutting rules* block
above and `docs/TODO2.md`. Class 4's *"never built mid-batch"* clause is amended by the same stroke
for B9/B12, independently of the detector budget, which they do not spend.

**Why the amendment is warranted here, on the corrected measurement.** The original argument — *all
639 existing rejections sit at passages a batch has already opened, so the queue never works them
off* — **is false and is not the reason.** Measured: **252 of the 268** passages holding those 639
still carry tier-3 rows, so the queue reaches them on its own and F5's mechanism types the **390**
rejections there for free; only **249 rows over 16 passages** are stranded today. Under the rule
those 390 are textbook **class 3** — *the queue brings it back on its own*.

The real asymmetry is prospective. A reading batch **finishes** the passages it opens: of the 23
passages C1 has adjudicated, only **6** still hold a tier-3 row. So every rejection written from here
on lands at a passage that leaves the queue in the same act — permanent residue at the moment of
writing, at ~**14 rejections per batch** (batches 5–9: 16 / 20 / 15 / 4 / 13, mean 13.6) — and every
correction on screen is discarded with it. The backlog behind us is largely absorbed; the residue
each further batch creates is not. That is what the interrupt buys, and it is why deferring costs
more than the standing 639 suggest.

Construction for all of the above: `trust_tier`/`passage_ref` join over
`variant_claims_candidates.json`, and the `p5-track-c1-*` entries of `promotion_log.json` for the
adjudicated-passage set — B9 commits it.

**Detector budget: zero spent.** B9 and B12 live in `ingestion/extraction/`, outside the `audit`
package, so `discover_checks()` (`audit/__main__.py`) never sees them — the location invariant Stage
P6 used for its G-track tooling. B11 edits A16, which the budget exempts as an instrument that cannot
emit a finding.

- [ ] **B9** — `ingestion/extraction/rejection_audit.py`. Commit the measurement, so every figure in
      ADR-023, GAP-012 and DEV-150 is re-derivable rather than quoted ("a recorded figure names its
      construction"). Joins `variant_claims_candidates.json` to
      `relationships_candidates_cleaned.json`, `entities_candidates_confirmed_v1.json` and
      `promotion_log.json`; inverse key = `(parent, "parentage", "child of " + subject, source_id)`,
      parent parsed with A14's own `parse_parent` rule (first confirmed entity name in the
      remainder), **imported from `audit.claim_direction` rather than reimplemented** — a second
      parser is a second thing to drift.
      Also emits the **queue-reachability split** every other item's arithmetic now rests on: for the
      tier-2 set, how many rows and passages still carry tier-3 rows (the queue returns) versus not,
      and the distinct-passage count of the `p5-track-c1-*` batches.
      **Exit:** reproduces 639 / 581 / 283 / 101 / 162 / 268 **and** 560 + 21 / 390 at 252 / 249 at
      16 / 23 C1 passages on the current pool. A divergence means a document is quoting a stale
      number, and the document is wrong, not the script. **The 34 / 243 / 283 split is against the
      560 rows with a derivable inverse key, not the 581** — the first draft of ADR-023 quoted 49%
      against 581 while partitioning 560, which is what the `+21` term exists to close.
- [ ] **B10** — **Rejection typing.** Add `rejection_reason` to the reject path in
      `extraction/claim_evidence.py` and the notebook write cell, drawn from ADR-023's closed
      eight-value vocabulary. A rejection without a code **raises** — the same posture as the existing
      approved∩rejected contradiction guard, and for the same reason: a missing code is an omission,
      not a default. Generalise `run_extraction._write_claims_preserving_review` from the hardcoded
      `trust_tier` to `_REVIEW_OWNED_FIELDS = ("trust_tier", "rejection_reason")` — **without this the
      codes are erased by the next extraction run**, which is DEV-101's failure through a new door.
      `rejectedKeys` entries in `promotion_log.json` become `{"key": [...], "reason": "..."}`; keep a
      reader for the legacy bare-5-tuple form (29 existing entries, which read as
      `unclassified_legacy`).
      **Exit:** a batch cannot record a reasonless rejection; a `run_extraction` re-run carries all
      639 codes across (0 lost), asserted in the existing merge unit tests.
- [ ] **B11** — **The correction channel.** New `extraction/output/claim_corrections.json` (six
      candidate fields + `origin`, `corrects`, `evidence_span`, `batchLabel`, `date`), consumed by
      `seedgen/variant_claims_gen._reviewed_rows` — unioned in, then passed through the **same**
      entity-presence and 4-tuple dedup filters, because an overlay row is not exempt from the
      reachable ceiling. `review_passage` pre-fills a proposed correction for every
      `reversed_direction` rejection, showing A14's matched span, and requires explicit confirmation
      (ADR-023 §4; ADR-004 Amendment 2).
      **A16 changes in this same item, not later:** `audit/coverage.py::variant_claims_ceilings`
      derives numerator *and* ceiling from the candidate pool alone, so a seeded row absent from that
      pool makes the instrument every batch closes on misreport. Overlay rows count in both, and the
      printed derivation chain gains an `+N overlay` term.
      **Do not write corrections into `variant_claims_candidates.json`** — merge-on-write drops any
      reviewed row extraction no longer produces, and it never produces a reviewer-authored one.
      **Exit:** a confirmed correction survives a `run_extraction` re-run untouched, appears in a
      regenerated `V12_1__…`, and moves A16 row coverage.
- [ ] **B12** — **The claim↔edge seam (GAP-012).** `ingestion/extraction/claim_edge_reconcile.py`:
      for **every** tier-2 rejection with a derivable mirror key, report whether the mirror
      `parent_of` edge is still in `relationships_candidates_cleaned.json` and whether it is live in
      V11, **bucketed by `rejection_reason`**. The reason code does the sorting; it must **not** be
      the input filter — filtering the input to `reversed_direction`/`not_in_passage` would exclude
      `wrong_subject_namesake` by construction, which is exactly buckets 2 and 3 of this item's own
      exit, leaving ~160 of the 162 outside the report. Invoked from the notebook and once per sprint
      (added to the Track C per-batch loop).
      **Exit:** the 162 split three ways — *edge is wrong and live* (fix the cleaned file), *edge
      belongs to a different figure* (GAP-011 / namesake work), *rejection was namesake-scoped and
      the edge is correct*. They cannot be told apart before B10 types them, and that is the finding,
      not a limitation of the tool.
- [ ] **B13** — **Mechanical backfill**, no corpus reads. A14's 42 and A15's 6 direction findings →
      `reversed_direction`; any `<UNKNOWN>` / `<none>` / empty subject → `malformed_subject`
      (**0 such rows are at tier 2 today** — the 108 junk rows are still tier 3 and are Track C's, per
      that track's exit); everything else → `unclassified_legacy`.
      **Exit:** every tier-2 row carries a code, and the `unclassified_legacy` count is recorded as
      F5's opening balance — **591 rows** at the time of writing (`639 − 48` mechanically typed).
      **B13 records the queue-reachability split of those 591, not just the total** — over the full
      639 it is 390 rows at 252 reopened passages against 249 at 16 stranded ones, and B13's 48 come
      off one side or the other, so the split must be recomputed after typing rather than inherited.
      The stranded count is the only number F5 has to spend reads on.

**Exit for B9–B13:** rejection is a typed, queryable verdict; a correction authored from an open
segment reaches `V12_1__…`; A16 counts it; and `claim_edge_reconcile` runs in the batch loop.

---

## Track C — Seeding sprints (full pool, top passages first)

Run the B4 queue in order. Bucket A rows batch-confirm against their matched span; C/D/unparsed get
read; Z is classified without a read (B3).

Per-batch loop, every time (the P3 fix loop, unchanged except for the last line):
```
python -m seedgen --strict           # regenerates V10/V11/V12; fails on missing floor conflicts
scripts/reseed-local.sh --local-only # regenerating an applied migration breaks flyway validate
python -m audit --only A16 --out reports/coverage   # coverage delta -- the number that closes the batch
python -m audit                      # 16 checks; exit 1 on any finding neither waived nor DEFERRED
python -m extraction.claim_edge_reconcile          # B12: did this batch's rejections leave a live edge?
```
**The gate is exit 0 with a non-growing backlog**, not exit 0 alone `[DEVIATED - see DEVIATIONS.md
#DEV-130]`. After E5 and A6, the 949 relocated findings report `DEFERRED` and do not fail the run, so
a batch that adjudicates nothing still exits 0 — read the per-check deferred counts, which must be
**strictly lower** than the previous batch's for the checks that batch touched, and never higher for
any check. A new *unwaived, undeferred* finding still fails the run and still stops the batch.
**`--out` on the A16 run is not optional, and the order matters.** Both invocations write
`reports/<today>-findings.json` and `reports/<today>.md` from the same date-derived filename
(`audit/__main__.py:208-210`), so an unredirected `--only A16` run **overwrites the full-suite report
with a one-check report** — verified live. Redirect it, and run it before the full suite so the
day's committed report is the 16-check one.

Sprint sizes below are row counts, which understate the work: the read cost is the segment text.
C1's 100 passages are **~257k characters**; the full 1,059 are **~2.54M characters ≈ 424k words**
(median segment 2,504 chars). Budget by characters, not by checkbox.

- [ ] **C0** — **The 101-row correction pass** `[DEVIATED - see DEVIATIONS.md #DEV-150]`. Runs
      immediately after B13, before C1 batch 10. **Table: `variant_claims`. Expected rows: ≤101**,
      less whatever the seedgen 4-tuple dedup collapses — named up front per the seeding rule, and
      closed on an A16 move like any seeding batch.
      Re-open the **62 passages** behind the 101 rejections whose correction is immediately seedable
      (both names already in `entities`) and author those corrections. This is the highest
      row-per-read ratio anywhere in the stage — **101 rows from 62 segment reads**, against C1's
      2,229 adjudications from 100 reads, most of which are not promotions — and it is available only
      because B11 exists; before it, those 62 reads produced nothing.
      The remaining 182 corrections of the 283 are blocked on a missing entity and are **Track D's**,
      not this item's; they re-queue here once the `Z_HOLD` entities land.
- [ ] **C1** — Passages 1–100 → 2,229 tier-3 rows (33% of the pool), ~257k chars.
      **Batches 1–9 done** (batches 1–3 = 7 passages pre-P6; batches 4-re-review through 9 landed
      2026-08-01 after the P6 gate lifted — DEV-148). Construction: the `p5-track-c1-*` entries in
      `ingestion/audit/promotion_log.json`. **Batch 10 is gated on B9–B13**
      `[DEVIATED - see DEVIATIONS.md #DEV-150]`, then C0 — see the *Track order* block. The collision
      signal is live in `review_passage` (risk line + most-suspicious-first ordering, G6) and identity
      is no longer the largest rejection cause.
      **What batches 1–9 could not record, and batch 10 onward must:** every rejection they wrote is
      untyped (`unclassified_legacy`) and every correction they read is lost — 639 rows over 268
      passages. **F5 owns only the part the queue cannot reach** (249 rows at 16 passages); the other
      390, at the 252 passages that still hold tier-3 rows, are typed for free when the queue reopens
      them. **Batches 1–9 have adjudicated 23 of C1's 100 passages, leaving 77.**
      **What changed under
      C1 while it was paused, and what a batch-10 reviewer must know** (it was written for batch 4,
      and every word of it still binds — the pool has not been regenerated since)**:** the candidate pool was
      regenerated (7,429 → 9,096 rows; the group space moved 798 → **1,405 or 1,412 — reconcile
      before quoting either**, see the figure note below), the fuzzy step no longer
      auto-merges, and `namesake_registry.json` carries 63 adjudicated splits — so batch 4 works a
      materially different pool than batches 1–3 did. **63 previously-decided rows sit at tier 3
      awaiting re-adjudication**, individually named in `promotion_log.json` under the three `p6-*`
      batch labels; they are C-track work and the natural first item of batch 4.
      **Also C-track, and previously homeless** `[DEVIATED - see DEVIATIONS.md #DEV-149]`:
      **A14's 42 and A15's 6 direction findings** (reversed / self-referential `parentage` and
      `death` claims) were recorded only in DEV-148's *Carried out of the stage* bullet, which is
      append-only history rather than a work queue, so nothing would have surfaced them. **None is
      promoted or live** — they are tier-3 `variant_claims` rows, i.e. exactly what Track C
      adjudicates — so they need no separate track, but a batch that meets one should reject it on
      the A14/A15 evidence rather than re-deriving the direction by hand.
      > **Figure note, unresolved** `[DEVIATED - see DEVIATIONS.md #DEV-149]`. This line read
      > **1,405** groups; DEV-148 and the live `A10` summary both report **1,412**. The two are
      > plausibly the alias-blind/alias-aware split that DEV-129 already hit once (838/749 vs
      > A10's 795/723) and DEV-127 documents for no-DB runs, but that is a hypothesis, not a
      > reconciliation — `build_group_inventory`'s alias-aware path needs both DB-sourced alias
      > maps, so it cannot be settled offline. **Settle it on the next live `A10` run and state
      > which construction each number came from; do not quote either figure until then.**
      `[DEVIATED - see DEVIATIONS.md #DEV-139]` — see the *Track order* block. C1's batches 1–3
      measured identity collisions at 20–30% of every batch's rejections, and the fix re-keys review
      decisions, so it is paid before the queue grows. The gate is at the **next batch**, not at the
      C1/C2 boundary: C1's remaining ~93 passages grow the exposure exactly like C2's would.
- [ ] **C2** — Passages 101–250 → 3,673 cumulative (55%). Downstream of the C1 gate, which is now
      lifted (DEV-148).
- [ ] **C3** — Passages 251–500 → 5,183 cumulative (77%)
- [ ] **C4** — Passages 501–1,059 → 6,695 cumulative (100%)
- [ ] **C5** — *Optional, only if the queue drags:* one-time batch rejection of the **bucket E** rows
      **in passages the queue has not opened** (neither party named in the cited passage under any
      spelling either alias layer knows). E rows in passages Track C has already read are decided
      per-row on the open segment and never reach this item. This is a **denominator** win, not
      coverage — budget it explicitly under the seeding rule or it is itself the drift.
      **Permitted by B7's bucket-E carve-out and by nothing else** `[DEVIATED - see DEVIATIONS.md
      #DEV-130]`. Two conditions, both required: **B2a has run and reports the alias layers clean**
      (an absence is only evidence once both layers have been consulted), and the rows are bucket E.
      **Bucket D stays excluded whatever B2a reports** — one party *is* in the passage there, so
      B7's no-batch-on-"no match" clause binds with full force and each row needs an opened segment.
      As first written this item read as excluding D only *until* B2a ran, which B7's rejection
      clause forbids in either state.
- [ ] **C6** — GAP-001 Root cause 3's promotion half (a′) closes here as a by-product: the ~690
      non-top-20 dropped rival parents are A6-contested rows, so B4's primary sort front-loads them.
      Carried in from P4 `[DEVIATED - see DEVIATIONS.md #DEV-128]`; was homed to P5b before the freeze.

**Exit per sprint:** A16 `variant_claims` group coverage strictly increased; the batch entry carries
before/after figures; `seedgen --strict` clean; reseed green; no new audit check added without budget.

**Exit for the track:** all 1,059 passages adjudicated — every tier-3 row is now tier 1, tier 2, or
in the **bucket-Z blocked register** with its blocking decision named `[DEVIATED - see DEVIATIONS.md
#DEV-130]` — **and every tier-2 row carries a rejection reason, and every `reversed_direction`
rejection has either a confirmed correction or a recorded statement of why none is owed**
`[DEVIATED - see DEVIATIONS.md #DEV-150]`. Without that second clause the track can exit having
adjudicated everything and discarded half of what it read, which is the state B9 measured. The register is not a loophole: it is closed to any row whose subject could exist and was
merely unreached, and today it holds the **80** D4-blocked rows plus whatever part of the ~166
Track-D-dependent rows D1's 60-name bound does not reach. The 108 junk-subject rows are *not* in it —
they are rejected outright at tier 2.

As first written this exit read "every tier-3 row is now tier 1 or tier 2", which bucket Z's own
disposition ("record as blocked-by-decision, do not read") contradicts for ~246 rows.

**What "100%" does and does not mean here, stated up front so no sprint reads as a failure.**
Adjudicating every tier-3 row does **not** put every row in the DB, and the gap is not the reviewer's:
of the 6,695 rows, **354** are bucket Z (subject absent from `entities`; 359 across all tiers) and
**2,327** across the whole pool collapse under seedgen's 4-tuple dedup. Track C's honest ceiling is the **4,743-row / 715-group**
figure from A2a, and per-sprint success is measured by the group number moving, never by
`rows_seeded ÷ rows_adjudicated`. Of bucket Z, only the ~166 rows Track D can unblock are recoverable
within this stage; the 108 junk-subject rows never are and are rejected at tier 2, and the 80
D4-blocked rows are a recorded decision, not a defect — they and any unreached remainder of the ~166
close out in the **bucket-Z blocked register**, which is what makes "all 1,059 adjudicated" true
without claiming they were seeded.

---

## Track D — Relationships and entities seam

*Starts after C2.* The mechanical table has no human gate and sits at **48.9%** edge coverage
(3,367/6,882); 901 candidate rows are dropped for referencing 347 names absent from `entities`
(name-space coverage 1,990/2,337 = **85.2%**).

> ⚠️ **Every figure in this track predates Stage P6 — re-derive before starting** (2026-08-01,
> DEV-149). P6 re-extracted the candidate pool and changed the identity layer under all of it:
> `variant_claims` candidates 7,429 → 9,096 rows, groups 798 → 1,412, `entities` 1,990 → 1,995,
> edge coverage 48.9% → **49.1%**. D1's bound of 60 and the ≥53% / ≥87% exits were computed against
> the pre-P6 numbers, and DEV-132 already had to correct this same table once when its arithmetic
> went stale. **Re-derive the ranked list from `compute_drop_accounting(...).unknown_names` and the
> projections from a fresh A16 run before fixing the bound** — the instruction to re-derive is
> already in D1; this note says the *exits* may move too, not just the list.
>
> **Three new inputs this track now owns, none of which existed when it was written:**
> 1. **57 split identities in `Z_HOLD`** (39 from P6 G3, 18 from G5) — adjudicated, reason-bearing,
>    and blocked only on an `entities` row. They are the highest-confidence entity work available
>    and should be ranked ahead of the unknown-name tail, which is triaged from scratch.
> 2. **GAP-011** (`docs/DATA-GAPS.md`) — **39 live `V11` edges** attach to the wrong figure because
>    P6's registry never reached `relationships_candidates_cleaned.json`. **Ordering matters and is
>    the reason this is homed here:** 53 of the 57 correct identities do not exist as entities yet,
>    so propagating in bulk converts wrong edges into *dropped* edges and moves A16 coverage
>    **down**. Land the `Z_HOLD` entities (item 1) first, then re-key the cleaned file's endpoints.
>    **3 live rows are re-keyable today at zero entity cost** — their split identity is already in
>    `V10` (`Mestor (son of Pterelaus)` ×2, `Orsilochus (elder)`); take those first, as a worked
>    example of the re-key before it runs at scale.
> 3. **GAP-009's ~66 unguarded splits** — genuine spelling variants the fuzzy demote separated
>    without a curated alias. No `audit/` check covers them (A1 reads the *confirmed* set, which the
>    demote does not touch). Read the ledger's `fuzzy_suggestion` rows before promoting any name
>    that looks like a near-duplicate of an existing entity.

**Size the budget from the exit criteria, not from a round number.** An earlier draft bounded D1 at
"top-20 unknown names" and set the exits at ≥53% / ≥87%. Both are unreachable at that bound, because
the top-20 list is mostly unavailable:

| top-20 by reference count | count | why unavailable |
|---|---|---|
| `<UNKNOWN>` (133 refs, **rank 1**) | 1 | placeholder — can never become an entity (A9) |
| `Electra` 23, `Phineus` 17, `Eurytus` 14, `Ascalaphus` 13, `Thoas` 13, `Hippolytus` 12 | 6 | **excluded by D4** as namesake collisions |
| workable remainder | **13** | — |

Measured yield: the 13 workable names unblock **+116 edges → 50.6%** and reach **85.7%** name-space —
short of both exits. Even adding all 20 including the placeholder reaches only 53.7% / 86.0%, and
≥87% needs **+44 entities** in the first place (`0.87 × 2,337 = 2,033.2`, so 2,034 seeded; +43 lands
at 2,033/2,337 = **86.99%**, just under — corrected from `+43`
`[DEVIATED - see DEVIATIONS.md #DEV-132]`). The exits are the right targets; the **bound** was
wrong, so this track raises the bound and keeps the exits. Measured over the *eligible* list
(placeholders and D4 names removed):

| eligible names worked | edges unblocked | edge coverage | name-space | lowest ref count |
|---|---|---|---|---|
| 20 | +155 | 51.2% | 86.0% | 6 |
| 45 | +253 | 52.6% | 87.1% | 4 |
| **60** | **+299** | **53.3%** | **87.7%** | **3** |
| 80 | +348 | 54.0% | 88.6% | 2 |

- [ ] **D1** — Work **GAP-002 bucket 1, bounded to the first 60 unknown names by reference count
      that are neither placeholders (A9) nor D4 exclusions.** 60 is the smallest bound clearing both
      exits with margin — 45 clears entity coverage by 0.1pp, which D3 can erase by rejecting three
      names as extraction corruption. The 60th name still has 3 references, well clear of the 192
      singletons, so the worthless tail stays out. Re-derive the ranked list from
      `compute_drop_accounting(...).unknown_names` after A9 lands, rather than from the table above.
- [ ] **D2** — Check `Helios` first: a genuinely missing major god. It also blocks **10 tier-3
      `variant_claims` rows** in bucket Z, so it is the one D-track name that pays into Track C too —
      re-queue those rows once it exists.
- [ ] **D3** — **Mandatory discipline:** confirm each name against corpus token counts using
      `name_coverage.py`'s (A7) existing machinery **before** adding any entity. DEV-096/098 proved
      this triage is error-prone — `Arges` turned out to be extraction corruption of `Ares`, not a
      missing Cyclops. Every addition needs a corpus-count line in its DEV entry.
- [ ] **D4** — `[DEVIATED - see DEVIATIONS.md #DEV-149]` **The premise of this exclusion no longer
      holds — re-decide it, do not inherit it.** Bucket-2 namesake collisions (`Electra`, `Eurytus`,
      `Phineus`, `Thoas`, `Oenomaus`, `Hippolytus`, `Ascalaphus`, `Clitus`/`Pisenor`) were ruled out
      of scope because "they are not fixable by a spelling alias, which is GAP-002's own transferable
      lesson." That was true when written and is **false since ADR-022**: a spelling alias was never
      the candidate mechanism — `namesake_registry.json` is, it is keyed on corpus location rather
      than on a name pair, it beats exact match (which is what a byte-identical collision needs), and
      it has now separated 57 such figures. **None of these nine names carries a registry entry yet**
      (construction: `{e['name'] for e in namesake_registry.json} & <the nine>` → empty), so this is
      unworked, not silently done.
      **The recorded cost is what changed the arithmetic:** these names hold **80 tier-3
      `variant_claims` rows** (bucket Z) that can never seed while the exclusion stands, plus their
      share of the relationship edges. Under ADR-022 that is a *reachable* 80, not a permanent write-
      off. Re-decide on the same terms every other bound in this track uses: measure the yield
      first, then set the bound. If the exclusion is kept it is now a **budget** decision, so record
      it as one — the old "not fixable" reason may not be reused.

**Exit:** A16 `relationships` edge coverage **≥ 53%**; entity name-space coverage **≥ 87%**; zero
names added without a corpus-count line. Unchanged from the original — reachable now that D1's bound
is 60 eligible names (projected 53.3% / 87.7%). Re-check the projection against A16 after A9, since
removing the placeholder shifts the ranked list.

---

## Track E — Stop doing / retire / consolidate

> **E5 is not in track order — it runs first, inside Track A, before A6 and A7.** Two reasons, both
> verified: `load_waivers` raises at load time, so A7 with the 347 A2 scope waivers still present
> kills every `python -m audit` invocation; and A6's 602 need somewhere to *go* — relocating them
> without E5's `DEFERRED` disposition leaves them unwaived and pins the suite at exit 1 for the whole
> stage `[DEVIATED - see DEVIATIONS.md #DEV-130]`. The rest of Track E can run at the end as written.

- [ ] **E1** — **Stop adding audit checks.** **A16 (Track A1) is the last one**, and it is admitted
      as an *instrument*, not a detector: it can never emit a finding, so it carries the standing
      exemption in the seeding rule. A1–A16 is enough. Do not revisit GAP-008 with a wider regex —
      A13's negative result is properly recorded. (An earlier draft of this item read "A1–A15 is
      enough" while Track A1 was already specifying A16, which read as a contradiction.)
- [ ] **E2** — **Stop subject-prominence tranche selection.** A8 stays useful as a tiebreak *inside*
      a passage, but is no longer the scoping axis — **and only after A9 removes the `<UNKNOWN>`
      placeholder from its ranking**, since a tiebreak that ranks a placeholder 19th is not a
      tiebreak worth keeping.
- [ ] **E3** — **Stop writing measurement tables into DEV entries.** `docs/DEVIATIONS.md` is large
      and its numbers go stale on the next regeneration. Cite an A16 run and a `promotion_log.json`
      `batchLabel` instead. **Where a figure must appear in prose, record the construction that
      produced it** — DEV-128's `838/749` and `2,621/753` were unreproducible precisely because the
      method went unrecorded, and the first pair turned out to be alias-blind.
      **Hard budget: ~4 KB per DEV entry** `[DEVIATED - see DEVIATIONS.md #DEV-131]`. Measured, this
      is the binding constraint and the one E3 was missing: average entry size grew **1.2 KB →
      10.4 KB (8.5×)** from DEV-001..011 to DEV-126..130, which is what pushed the file past a
      single read at ~169K tokens and forced the DEV-131 archive. Entry *count* was never the
      problem. For calibration, DEV-130 is 12 KB — the 4th-largest entry in the file — so this rule
      binds the entries this stage is itself writing, not just future ones.
- [ ] **E4** — Archive the closed-stage checklists (`TODO.md`, `TODO-stage1..9.md`,
      `TODO-adr-015.md`, `TODO-adr-016.md`, `TODO-phase2-stage-p1..p4.md`) to `docs/archive/` in one
      commit. **`docs/TODO2.md` + this file become the only live checklists.**
      **Follow the DEV-131 precedent** `[DEVIATED - see DEVIATIONS.md #DEV-131]`: move files
      verbatim, leave a resolvable pointer behind rather than rewriting inbound references, and
      verify the references still resolve before committing. `TODO-phase2-stage-p3.md` alone holds
      89 `DEVIATIONS.md` references and `TODO.md` 60, so an archive that breaks pointers is worse
      than no archive.
- [x] **E5** — **[runs first — see the note above]** Create the backlog artifact
      (`ingestion/audit/backlog.json`) and move the **347 A2** waiver entries out of
      `audit-waivers.json` into it; **Track A6 then moves its 602 into the same file.** Like the A6
      entries, they are a triage queue, not waivers.
      **The runner must give backlog entries their own disposition** `[DEVIATED - see DEVIATIONS.md
      #DEV-130]`: a finding matching a backlog entry is reported **`DEFERRED`**, is **excluded from
      `AuditRun.exit_code`** (`audit/__main__.py:104`, which counts any finding that is neither
      waived nor deferred), and is **counted per check in the run summary** — so the number is loud
      rather than silent. That is the whole point of the move: a waiver is a permanent judgement that
      nothing will ever change, a deferral is a queue position with a count that shrinks as Track C
      works. Without the disposition, moving 949 entries simply un-waives them and pins the suite at
      exit 1 for the entire stage. A16 reads the artifact and reports the remaining backlog per check
      as a "rows at stake" line (E6). **Prerequisite for both A6 and A7**, and therefore for Track
      A's exit criterion.
- [ ] **E6** — **`docs/DATA-GAPS.md` becomes the only open-work backlog.** Every GAP gains a
      mandatory **"rows at stake"** line computed by A16. GAP-001 (a′) and GAP-002 dissolve into
      Tracks C and D. **Two machine-readable queues sit under it and get the same line**
      `[DEVIATED - see DEVIATIONS.md #DEV-130]`: E5's `backlog.json` (the 949 deferred findings, per
      check) and the **bucket-Z blocked register** (B3). Neither is a waiver; both shrink or close
      out in F1.
- [ ] **E7** — Move GAP-005 (in-narrative deception) and GAP-008 (misattributed passage refs) to a
      **"Known and accepted"** section. Both are documented as mechanically undetectable; leaving
      them in the open list is what keeps generating detector ideas.

---

## Track F — Close

- [ ] **F1** — Write the **coverage statement** in `docs/DATA-GAPS.md`: per-table seeded fraction
      **against the reachable ceiling, with the ceiling's own derivation shown**, what is knowingly
      absent, and the closing A16 baseline. Knowingly absent, each with its row count: GAP-005,
      GAP-008, the `myths`/`myth_participants` freeze, the **108 junk-subject rows**, the **closing
      bucket-Z blocked register** (the 80 rows blocked by D4's namesake decision plus any part of the
      ~166 Track-D-dependent rows D1's bound did not reach, each with its named blocker), and the
      **~2,327 rows the seedgen 4-tuple dedup collapses**
      (multi-attestation of one claim within one source, of which only the first `passage_ref`
      survives — note that this is a provenance loss, not a claim loss, and that DEV-021 added
      `passage_ref` precisely so surfaced conflicts cite like RAG answers).
- [ ] **F2** — Add 2–3 CONFLICT gold questions to `evaluation/gold-questions.json` drawn from newly
      seeded groups.
- [ ] **F3** — Re-run the `evaluation/` harness; `compare.py` against the prior result directory.
      CONFLICT category must not regress, and should rise as groups gain sources. Remember the
      cross-cutting rules: never act on a single-run delta, and a run containing transport timeouts
      is invalid, not evidence.
- [ ] **F4** — Confirm every DEV entry from this stage cites a `batchLabel` rather than restating
      counts, and that any figure it does state names its construction (E3).
- [ ] **F5** — **The rejection reconciliation register** `[DEVIATED - see DEVIATIONS.md #DEV-150]`.
      The named home for the rejections B13 could only type mechanically. **This is scheduled work,
      not a deferral**, and it needs its own item because most of it is *not* an asymmetry: the bulk
      of the register is worked off for free like every other backlog here, and the item exists to
      keep the part that is not from hiding inside the part that is.
      The register is the set of `unclassified_legacy` rows, each bound to its `(source_id,
      passage_ref)`. `review_passage` surfaces any legacy rejection for a passage it opens, so a row
      whose passage is re-opened for *any* reason is typed for free and the register shrinks without a
      dedicated read — which is why the count is read, not the passage list.
      **Opening balance: 591 rows over at most 268 passages** (B13's exit). The queue-reachability
      split is measured over the full 639 — **390 rows at 252 passages the queue reopens, 249 at the
      16 it does not** — so B13's 48 mechanical typings come off one side or the other and B13 records
      the post-typing split rather than inheriting this one. **The 390 are ordinary class-3 work and
      need no reads of their own. The register's real cost is the ≤249 rows at the 16 passages the
      queue never returns to**, less whatever C0's 62-passage pass absorbs; after C0, 206 of the 268
      passages remain in the register at all. Read
      the second number, not the first: the opening balance overstates the work by an order of
      magnitude and was, in the first draft of this item, the whole justification for it.
      **Exit:** the register is empty, **or** every remaining entry carries a stated reason why
      re-reading its passage is not worth its rows — the same "rows at stake" discipline E6 requires
      of `docs/DATA-GAPS.md`. The stage does not close on an untyped rejection with no recorded
      judgement; it may close on one that was judged not worth the read.

**Stage done when:** every tier-3 `variant_claims` row is decided — tier 1, tier 2, or in the
bucket-Z blocked register with a named blocking decision (Track C exit) — **every tier-2 row carries
a rejection reason and F5's register is closed out** — A16's closing figures are
written into `docs/DATA-GAPS.md`, per-category eval floors hold across a 3-run eval, and the relevant
ADR/DEV entries are logged.

---

## Track order

Not the alphabetical order — three items run out of sequence, each for a verified reason, and a
whole stage (**P6**) interrupts between C1 and C2 `[DEVIATED - see DEVIATIONS.md #DEV-139]`:

```
E5  -> backlog artifact + DEFERRED disposition (A7 crashes the suite otherwise; A6 has nowhere to
                                                put its 602 and would pin exit 1 for the stage)
A9  -> drop the <UNKNOWN> placeholder          (D1's budget and E2's tiebreak both rank on it)
A6, A7/A7a, A1-A3, A2a, A8                     (rest of Track A -- the serial gate)
B1, B2, B2a, B3-B6                             (engine; B2a gates C5)
B7, B8                                         (ADR-004 Amendment 1 -- merged before ANY batch approval)
C1 batches 1-3                                 (sprint 1, first 7 of 100 passages)
>>> STAGE P6 <<<  [DONE 2026-08-01]            (entity identity -- INTERRUPTED *inside* C1, after
                                                batch 3 and before batch 4; G0-G7 complete,
                                                ADR-022 Accepted, DEV-140/142-148)
C1 batches 4-9                                 (rest of sprint 1 -- UNBLOCKED; started with the 63
                                                rows P6 re-queued, named in promotion_log.json)
B9-B13                                         (the rejection half of the engine -- INTERRUPTS C1
                                                after batch 9, before batch 10; ADR-023, GAP-012,
                                                DEV-150. Hard edge, see below.)
C0                                             (the 101-row correction pass -- 62 reads, the first
                                                work B11 makes possible; runs before C1 resumes)
C1 batches 10+                                 (rest of sprint 1, now typing rejections)
C2                                             (sprint 2)
D1-D4                                          (starts after C2; D2 re-queues Helios's 10 rows into C)
C3, C4, C5                                     (C5 only if the queue drags; bucket E only, and only
                                                once B2a reports the alias layers clean)
E1-E4, E6, E7                                  (retire/consolidate)
F1-F5                                          (close; F5 is the rejection register, DEV-150)
```

**The P6 interrupt is a hard edge too** `[DEVIATED - see DEVIATIONS.md #DEV-139]`. Track C1's first
three batches measured identity collisions (`docs/DATA-GAPS.md` GAP-009/GAP-010) at **20-30% of
every batch's rejections** — the largest single rejection cause in each — and found **five defects**
already in live data (enumerated once in `docs/TODO-phase2-stage-p6.md` → *The class-1 set*). The fix
changes `resolve()`, which rewrites `subject_name`, which re-keys `_CLAIM_IDENTITY` and therefore
every affected tier-1/tier-2 verdict. That exposure is **1,092 decisions today** and grows with every
batch, so **no further Track C batch runs first — including C1's own batch 4.** Deferring past C1
would spend ~93 more passage reads against identities P6 corrects; deferring past C2-C4 would both
quadruple the re-key and spend ~4,400 adjudications the same way. See
`docs/TODO-phase2-stage-p6.md` and ADR-022.

**B9–B13 → C1 batch 10 is a hard edge too** `[DEVIATED - see DEVIATIONS.md #DEV-150]`, and for a
different reason than P6's. P6 interrupted because further batches would *grow the re-key exposure*;
this one interrupts because a reading batch **finishes the passages it opens**, so what it fails to
record there is lost rather than queued.

**Not** because the standing backlog is unreachable — it mostly is reachable, and the first draft of
this paragraph had that backwards. Of the 268 passages holding the 639 existing rejections, **252
still carry tier-3 rows**: the queue returns on its own and F5's mechanism types the **390**
rejections there for free. Only **249 rows over 16 passages** are stranded, and under the findings
rule the other 390 are class 3, not a reason to interrupt anything.

The prospective loss is the reason. Of the **23 passages** C1 has adjudicated, only **6** still hold
a tier-3 row — a batch closes its passages out of the queue as it goes. So every rejection written on
the current engine is permanent residue the moment the batch ends (~**14 per batch**; batches 5–9:
16 / 20 / 15 / 4 / 13), and every correction on screen is discarded with it. Deferring to the C1/C2
boundary takes that loss across C1's remaining **77 passages**; deferring past C2–C4 takes it across
the rest of the queue. This required an **amendment to the findings rule** — a class-2 finding does
not otherwise interrupt — recorded in the *Cross-cutting rules* block above. See ADR-023 and GAP-012.

**E5 → A6 is a hard edge, not a preference.** A6 without E5 deletes 602 waivers with no deferral
mechanism to catch them; combined with E5's own 347 that is 949 findings that are neither waived nor
deferred, and `AuditRun.exit_code` (`audit/__main__.py:104`) then returns 1 on every run for the rest
of the stage — failing Track A's exit and the gate at the foot of every Track C batch.

## Deviation protocol

Each of these needs a `docs/DEVIATIONS.md` entry and inline
`[DEVIATED - see DEVIATIONS.md #DEV-NNN]` markers:

- The P5 re-scope itself and the `myths` freeze — **DEV-128** (landed 2026-07-30)
- The corrections to DEV-128's own figures and track arithmetic — **DEV-129** (landed 2026-07-30)
- The five execution-blocking conflicts found by the contradiction pass — **DEV-130** (landed
  2026-07-30)
- ADR-004 Amendment 1, including the batch-*rejection* clause **and its bucket-E carve-out** (B7)
- The A6 waiver **relocation** — 602 of 649 moved to the backlog, not deleted; the other 47 kept (A6)
- The backlog artifact and the `DEFERRED` disposition in the audit runner (E5)
- The scope-shaped waiver filter, keyed off the revoke side (A7a)
- The bucket-Z blocked register (B3, Track C exit, F1)
- The A16 metric definitions, incl. the reachable-ceiling metric (A1–A3, A2a)
- Dropping `<UNKNOWN>` from the A8 and A2 rankings (A9)
- **Typed rejections, the correction channel, and the Track B reopening — DEV-150** (ADR-023,
  ADR-004 Amendment 2, GAP-012; covers B9–B13, C0, F5, the Track C exit clause and the amended
  seeding rule in `docs/TODO2.md`)
