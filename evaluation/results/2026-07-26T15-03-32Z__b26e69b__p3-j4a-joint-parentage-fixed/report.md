# Evaluation Report — p3-j4a-joint-parentage-fixed

- Run: `2026-07-26T15-03-32Z` | sha: `b26e69b` | label: `p3-j4a-joint-parentage-fixed` | runs: 3
- Base URL: http://localhost:8080
- **Overall (pessimistic / worst-run #0)**: 11/16 full-score = **69%** (target 75%) — BELOW TARGET
- Category pass rates:
  - FACT: 4/5 (80%) — floor n/a
  - DATA: 1/5 (20%) — floor 50% BREACH
  - MIXED: 2/2 (100%) — floor n/a
  - CONFLICT: 4/4 (100%) — floor 50% PASS
- Floor breaches: DATA
- Flaky questions: [2, 11]

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
| 8 | DATA | SQL | RAG | ✗ | ✗ | ✗ | 0/3 | stable-fail | |
| 9 | DATA | SQL | SQL | ✓ | ✓ | ✗ | 2/3 | stable-fail | |
| 10 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 11 | MIXED | MIXED | MIXED | ✓ | ✓ | ✓ | 3/3 | flaky | |
| 12 | MIXED | MIXED | MIXED | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 13 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 14 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 15 | CONFLICT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
| 18 | CONFLICT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | stable-pass | |
