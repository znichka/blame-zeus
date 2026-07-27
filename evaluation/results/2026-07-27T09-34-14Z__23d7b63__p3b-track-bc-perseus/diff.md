# Diff — `p3b-track-a-hestia-olympian` → `p3b-track-bc-perseus`

- Baseline: `p3b-track-a-hestia-olympian` @ `e861a17` — overall 12/16 (75%)
- Candidate: `p3b-track-bc-perseus` @ `23d7b63` — overall 15/16 (94%)

## ⛔ Stable PASS→FAIL regressions (gate-blocking)
- none

## Per-category rate deltas
- FACT: 80% → 100% (+20 pts)
- DATA: 60% → 100% (+40 pts)

## Route changes
- Q8: RAG → SQL

## Conflict-count changes (conflicts[] length)
- none

## Informational (not gate-blocking)
- ✅ improvement Q7 (DATA): stable-fail → stable-pass
- ✅ improvement Q8 (DATA): stable-fail → stable-pass
- 🌀 flaky flip Q3 (FACT): flaky → stable-pass (single-run delta — ignored by the gate)
