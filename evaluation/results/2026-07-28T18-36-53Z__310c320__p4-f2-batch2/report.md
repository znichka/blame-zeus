# Evaluation Report — p4-f2-batch2

- Run: `2026-07-28T18-36-53Z` | sha: `310c320` | label: `p4-f2-batch2` | runs: 3
- Base URL: http://localhost:8080
- **Overall (pessimistic / worst-run #2)**: 21/23 full-score = **91%** (target 75%) — PASS
- Category pass rates:
  - FACT: 5/5 (100%) — floor n/a
  - DATA: 5/6 (83%) — floor 50% PASS
  - MIXED: 1/2 (50%) — floor n/a
  - CONFLICT: 6/6 (100%) — floor 50% PASS
  - REFUSAL: 4/4 (100%) — floor 50% PASS
- Floor breaches: none
- Flaky questions: [8, 11]
- Slowest request: Q12, run 2 — 12.7s

Point cells and actual-route below are from the **worst run**; `class` is across all runs. Fill the **triage** column manually (Track H): one of `pipeline-bug` / `data-gap` / `corpus-gap` / `eval-bug`.

| id | category | route exp | route act | route | author | content | total | latency | class | triage |
|---:|----------|-----------|-----------|:-----:|:------:|:-------:|:-----:|--------:|-------|--------|
| 1 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 12.0s | stable-pass | |
| 2 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 7.9s | stable-pass | |
| 3 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 9.2s | stable-pass | |
| 4 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 6.5s | stable-pass | |
| 5 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 6.8s | stable-pass | |
| 6 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 5.9s | stable-pass | |
| 7 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 8.1s | stable-pass | |
| 8 | DATA | SQL | RAG | ✗ | ✗ | ✓ | 1/3 | 10.3s | flaky | |
| 9 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 8.4s | stable-pass | |
| 10 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 4.6s | stable-pass | |
| 11 | MIXED | MIXED | MIXED | ✓ | ✗ | ✓ | 2/3 | 10.4s | flaky | |
| 12 | MIXED | MIXED | MIXED | ✓ | ✓ | ✓ | 3/3 | 12.7s | stable-pass | |
| 13 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 11.5s | stable-pass | |
| 14 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 6.4s | stable-pass | |
| 15 | CONFLICT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 9.0s | stable-pass | |
| 16 | REFUSAL | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 5.2s | stable-pass | |
| 17 | REFUSAL | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 5.6s | stable-pass | |
| 18 | CONFLICT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 7.4s | stable-pass | |
| 19 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 11.1s | stable-pass | |
| 20 | REFUSAL | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 6.1s | stable-pass | |
| 21 | REFUSAL | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 4.3s | stable-pass | |
| 22 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 7.4s | stable-pass | |
| 23 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 5.7s | stable-pass | |
