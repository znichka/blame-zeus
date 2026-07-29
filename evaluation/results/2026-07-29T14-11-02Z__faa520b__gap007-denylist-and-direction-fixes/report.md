# Evaluation Report — gap007-denylist-and-direction-fixes

- Run: `2026-07-29T14-11-02Z` | sha: `faa520b` | label: `gap007-denylist-and-direction-fixes` | runs: 3
- Base URL: http://localhost:8080
- **Overall (pessimistic / worst-run #1)**: 22/25 full-score = **88%** (target 75%) — PASS
- Category pass rates:
  - FACT: 5/5 (100%) — floor n/a
  - DATA: 5/7 (71%) — floor 50% PASS
  - MIXED: 1/2 (50%) — floor n/a
  - CONFLICT: 7/7 (100%) — floor 60% PASS
  - REFUSAL: 4/4 (100%) — floor 50% PASS
- Floor breaches: none
- Flaky questions: [9]
- Slowest request: Q8, run 2 — 70.7s

Point cells and actual-route below are from the **worst run**; `class` is across all runs. Fill the **triage** column manually (Track H): one of `pipeline-bug` / `data-gap` / `corpus-gap` / `eval-bug`.

| id | category | route exp | route act | route | author | content | total | latency | class | triage |
|---:|----------|-----------|-----------|:-----:|:------:|:-------:|:-----:|--------:|-------|--------|
| 1 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 10.3s | stable-pass | |
| 2 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 11.6s | stable-pass | |
| 3 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 10.2s | stable-pass | |
| 4 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 8.0s | stable-pass | |
| 5 | FACT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 8.2s | stable-pass | |
| 6 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 11.8s | stable-pass | |
| 7 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 7.8s | stable-pass | |
| 8 | DATA | SQL | RAG | ✗ | ✗ | ✓ | 1/3 | 70.7s | stable-fail | |
| 9 | DATA | SQL | SQL | ✓ | ✓ | ✗ | 2/3 | 12.3s | flaky | |
| 10 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 6.6s | stable-pass | |
| 11 | MIXED | MIXED | MIXED | ✓ | ✗ | ✓ | 2/3 | 9.4s | stable-fail | |
| 12 | MIXED | MIXED | MIXED | ✓ | ✓ | ✓ | 3/3 | 16.8s | stable-pass | |
| 13 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 9.0s | stable-pass | |
| 14 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 7.6s | stable-pass | |
| 15 | CONFLICT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 17.2s | stable-pass | |
| 16 | REFUSAL | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 9.1s | stable-pass | |
| 17 | REFUSAL | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 9.3s | stable-pass | |
| 18 | CONFLICT | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 8.0s | stable-pass | |
| 19 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 10.5s | stable-pass | |
| 20 | REFUSAL | RAG | RAG | ✓ | ✓ | ✓ | 3/3 | 5.7s | stable-pass | |
| 21 | REFUSAL | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 6.2s | stable-pass | |
| 22 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 6.6s | stable-pass | |
| 23 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 7.2s | stable-pass | |
| 24 | CONFLICT | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 10.6s | stable-pass | |
| 25 | DATA | SQL | SQL | ✓ | ✓ | ✓ | 3/3 | 9.2s | stable-pass | |
