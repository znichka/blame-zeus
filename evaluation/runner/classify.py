"""N-run classification + pessimistic aggregation (Track C5).

Pure functions over Track-B `QuestionScore`s — no HTTP, no DB — so the
stable/flaky/stable-fail logic and the worst-run aggregate are unit-testable
without a server (C7). Also defines `RunResults`, the in-memory contract that
Track C (producer) hands to Track D's `report.write` (consumer).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .gold import GoldQuestion
from .scoring import Aggregate, QuestionScore, aggregate

STABLE_PASS = "stable-pass"
STABLE_FAIL = "stable-fail"
FLAKY = "flaky"


@dataclass(frozen=True)
class QuestionClassification:
    id: int
    category: str
    label: str  # stable-pass | stable-fail | flaky
    per_run_passed: list[bool]
    per_run_total: list[int]

    @property
    def is_flaky(self) -> bool:
        return self.label == FLAKY


def classify_question(scores_across_runs: list[QuestionScore]) -> QuestionClassification:
    """stable-pass (N/N full score), stable-fail (0/N), flaky (mixed) — §2.3."""
    if not scores_across_runs:
        raise ValueError("classify_question needs at least one run's score")
    passes = [s.passed for s in scores_across_runs]
    if all(passes):
        label = STABLE_PASS
    elif not any(passes):
        label = STABLE_FAIL
    else:
        label = FLAKY
    first = scores_across_runs[0]
    return QuestionClassification(
        id=first.id,
        category=first.category,
        label=label,
        per_run_passed=passes,
        per_run_total=[s.total for s in scores_across_runs],
    )


def classify_all(scores_by_run: list[list[QuestionScore]]) -> list[QuestionClassification]:
    """Transpose per-run score lists → per-question classifications.

    Runs are aligned by question **id** (not positional index) so a reordered or
    subset run can't silently misalign. All runs must cover the same id set.
    """
    if not scores_by_run:
        return []
    # Preserve first run's question order.
    ordered_ids = [s.id for s in scores_by_run[0]]
    by_id_per_run = [{s.id: s for s in run} for run in scores_by_run]

    classifications: list[QuestionClassification] = []
    for qid in ordered_ids:
        across = []
        for run_map in by_id_per_run:
            if qid not in run_map:
                raise ValueError(f"question id {qid} missing from a run — runs must be aligned")
            across.append(run_map[qid])
        classifications.append(classify_question(across))
    return classifications


def worst_run_aggregate(
    scores_by_run: list[list[QuestionScore]],
    category_floors: dict[str, float | None],
    overall_target: float,
) -> tuple[int, Aggregate]:
    """Pessimistic aggregate = the single worst run (§2.3).

    Worst = fewest full-3/3 passes, tie-broken by fewest total points. Returns
    (worst_run_index, that run's Aggregate).
    """
    if not scores_by_run:
        raise ValueError("worst_run_aggregate needs at least one run")
    aggregates = [aggregate(run, category_floors, overall_target) for run in scores_by_run]
    worst_idx = min(
        range(len(aggregates)),
        key=lambda i: (aggregates[i].passed_questions, aggregates[i].total_points),
    )
    return worst_idx, aggregates[worst_idx]


@dataclass(frozen=True)
class RunResults:
    """Everything a run produces, ready for Track D's `report.write`.

    `raw_by_run` preserves the untouched server JSON per question per repetition
    (D2 — the poor-man's query history); `scores_by_run` is the parsed/scored view.
    """

    label: str
    runs: int
    base_url: str
    questions: list[GoldQuestion]
    raw_by_run: list[list[dict]]
    scores_by_run: list[list[QuestionScore]]
    classifications: list[QuestionClassification]
    worst_run_index: int
    aggregate: Aggregate
    per_run_aggregates: list[Aggregate] = field(default_factory=list)

    @property
    def flaky_ids(self) -> list[int]:
        return [c.id for c in self.classifications if c.is_flaky]
