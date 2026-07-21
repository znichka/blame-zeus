# evaluation.runner — Phase 2 Stage P1 evaluation harness (ADR-018).
#
# A standalone offline operator tool, invoked as `python -m runner` against an
# already-running, seeded core-api server. NOT part of the Gradle build or CI
# (ADR-018 §Decision 2) — live LLM calls are sanctioned here, unlike the mocked
# Gradle/CI test suite (DEV-055).
