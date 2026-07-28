# Evaluation Report — p3b-a7-findings-triage

- Run: `2026-07-27T21-21-29Z` | sha: `3a3f894` | label: `p3b-a7-findings-triage` | runs: 3
- Base URL: http://localhost:8080
- **Overall (pessimistic / worst-run #2)**: 13/16 full-score = **81%** (target 75%) — PASS
- Category pass rates:
  - FACT: 5/5 (100%) — floor n/a
  - DATA: 4/5 (80%) — floor 50% PASS
  - MIXED: 1/2 (50%) — floor n/a
  - CONFLICT: 3/4 (75%) — floor 50% PASS
- Floor breaches: none
- Flaky questions: [3, 8, 13, 15]

Point cells and actual-route below are from the **worst run**; `class` is across all runs. Fill the **triage** column manually (Track H): one of `pipeline-bug` / `data-gap` / `corpus-gap` / `eval-bug`.

| id | category | route exp | route act | route | author | content | total | class | triage |
|---:|----------|-----------|-----------|:-----:|:------:|:-------:|:-----:|-------|--------|
| 1 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 2 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 3 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | flaky | |
| 4 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 5 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 6 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 7 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 8 | DATA | SQL | SQL | ✗ | ✗ | ✗ | 0/3 | flaky | |
| 9 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 10 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 11 | MIXED | MIXED | MIXED | ✓ | ✗ | ✓ | 2/3 | stable-fail | |
| 12 | MIXED | MIXED | MIXED | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 13 | CONFLICT | SQL | — | ✗ | ✗ | ✗ | 0/3 | flaky | |
| 14 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 15 | CONFLICT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | flaky | |
| 18 | CONFLICT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
