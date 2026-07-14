"""A7 resilience: per-segment checkpointing so one failed segment doesn't lose
the whole run, and re-running the script doesn't redo already-succeeded
extraction calls.

Append-only JSONL: one line per segment attempt, keyed by (source_id,
start_offset) -- start_offset is unique per source since segments never
overlap, unlike passage_ref which can repeat for oversized-paragraph
sub-chunks. Later lines for the same key override earlier ones when replayed,
so a segment that failed once and succeeded on a later run reads back as
"ok" -- nothing needs to rewrite prior lines.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from extraction.schema import ExtractedFacts


@dataclass
class CheckpointEntry:
    source_id: str
    start_offset: int
    status: str  # "ok" | "failed"
    facts: ExtractedFacts | None = None
    error: str | None = None


def load_checkpoint(path: Path) -> dict[tuple[str, int], CheckpointEntry]:
    if not path.exists():
        return {}
    entries: dict[tuple[str, int], CheckpointEntry] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        facts = ExtractedFacts.model_validate(row["facts"]) if row.get("facts") is not None else None
        entry = CheckpointEntry(row["source_id"], row["start_offset"], row["status"], facts, row.get("error"))
        entries[(entry.source_id, entry.start_offset)] = entry
    return entries


def append_checkpoint(path: Path, entry: CheckpointEntry) -> None:
    row: dict = {"source_id": entry.source_id, "start_offset": entry.start_offset, "status": entry.status}
    if entry.facts is not None:
        row["facts"] = entry.facts.model_dump()
    if entry.error is not None:
        row["error"] = entry.error
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
