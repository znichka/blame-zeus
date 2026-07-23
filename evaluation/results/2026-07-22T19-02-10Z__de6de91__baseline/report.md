# Evaluation Report — baseline

- Run: `2026-07-22T19-02-10Z` | sha: `de6de91` | label: `baseline` | runs: 3
- Base URL: http://localhost:8080
- **Overall (pessimistic / worst-run #0)**: 10/16 full-score = **62%** (target 75%) — BELOW TARGET
- Category pass rates:
  - FACT: 5/5 (100%) — floor n/a
  - DATA: 1/5 (20%) — floor 50% BREACH
  - MIXED: 0/2 (0%) — floor n/a
  - CONFLICT: 4/4 (100%) — floor 50% PASS
- Floor breaches: DATA
- Flaky questions: [11, 12]

Point cells and actual-route below are from the **worst run**; `class` is across all runs. Fill the **triage** column manually (Track H): one of `pipeline-bug` / `data-gap` / `corpus-gap` / `eval-bug`.

| id | category | route exp | route act | route | author | content | total | class | triage |
|---:|----------|-----------|-----------|:-----:|:------:|:-------:|:-----:|-------|--------|
| 1 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 2 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 3 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 4 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 5 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 6 | DATA | SQL | SQL | ✓ | ✓ | ✗ | 2/3 | stable-fail |  data-gap — Hades/Hestia typed `other_god`, dropped by `type='olympian'` filter → P3 |
| 7 | DATA | SQL | SQL | ✓ | ✓ | ✗ | 2/3 | stable-fail |  data-gap — Zeus→Heracles/Perseus parent edges missing → P3 |
| 8 | DATA | SQL | SQL | ✗ | ✗ | ✗ | 0/3 | stable-fail |  data-gap — Perseus has no modeled relations; SQL also serviceErrors → P3/P2 |
| 9 | DATA | SQL | SQL | ✗ | ✗ | ✗ | 0/3 | stable-fail |  pipeline-bug — `WITH RECURSIVE` serviceError (DEV-054) → P2 |
| 10 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 11 | MIXED | MIXED | MIXED | ✓ | ✗ | ✓ | 2/3 | flaky |  data-gap — no Homer/Iliad structured Troy attribution → P5b |
| 12 | MIXED | MIXED | MIXED | ✗ | ✗ | ✗ | 0/3 | flaky |  pipeline-bug — `WITH RECURSIVE` serviceError, flaky (DEV-054) → P2 |
| 13 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 14 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 15 | CONFLICT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 18 | CONFLICT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
