# Evaluation Report — p2-rung1

- Run: `2026-07-23T13-05-46Z` | sha: `bc309ff` | label: `p2-rung1` | runs: 3
- Base URL: http://localhost:8080
- **Overall (pessimistic / worst-run #2)**: 10/16 full-score = **62%** (target 75%) — BELOW TARGET
- Category pass rates:
  - FACT: 4/5 (80%) — floor n/a
  - DATA: 1/5 (20%) — floor 50% BREACH
  - MIXED: 1/2 (50%) — floor n/a
  - CONFLICT: 4/4 (100%) — floor 50% PASS
- Floor breaches: DATA
- Flaky questions: [2]

Point cells and actual-route below are from the **worst run**; `class` is across all runs. Fill the **triage** column manually (Track H): one of `pipeline-bug` / `data-gap` / `corpus-gap` / `eval-bug`.

| id | category | route exp | route act | route | author | content | total | class | triage |
|---:|----------|-----------|-----------|:-----:|:------:|:-------:|:-----:|-------|--------|
| 1 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 2 | FACT | RAG | RAG | ✓ | ✓ | ✗ | 2/3 | flaky | |
| 3 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 4 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 5 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 6 | DATA | SQL | SQL | ✓ | ✓ | ✗ | 2/3 | stable-fail | |
| 7 | DATA | SQL | SQL | ✓ | ✓ | ✗ | 2/3 | stable-fail | |
| 8 | DATA | SQL | SQL | ✗ | ✗ | ✗ | 0/3 | stable-fail | |
| 9 | DATA | SQL | SQL | ✓ | ✓ | ✗ | 2/3 | stable-fail | |
| 10 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 11 | MIXED | MIXED | MIXED | ✓ | ✗ | ✓ | 2/3 | stable-fail | |
| 12 | MIXED | MIXED | MIXED | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 13 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 14 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 15 | CONFLICT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 18 | CONFLICT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
