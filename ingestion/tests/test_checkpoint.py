from extraction.checkpoint import CheckpointEntry, append_checkpoint, load_checkpoint
from extraction.schema import ExtractedEntity, ExtractedFacts


def test_load_checkpoint_returns_empty_dict_when_file_does_not_exist(tmp_path):
    assert load_checkpoint(tmp_path / "missing.jsonl") == {}


def test_append_and_load_round_trips_an_ok_entry_with_facts(tmp_path):
    path = tmp_path / ".checkpoint.jsonl"
    facts = ExtractedFacts(entities=[ExtractedEntity(name="Zeus", type="olympian")])
    append_checkpoint(path, CheckpointEntry("hesiod-theogony", 42, "ok", facts=facts))

    loaded = load_checkpoint(path)

    entry = loaded[("hesiod-theogony", 42)]
    assert entry.status == "ok"
    assert entry.facts.entities[0].name == "Zeus"
    assert entry.error is None


def test_append_and_load_round_trips_a_failed_entry(tmp_path):
    path = tmp_path / ".checkpoint.jsonl"
    append_checkpoint(path, CheckpointEntry("homer-iliad", 100, "failed", error="boom"))

    loaded = load_checkpoint(path)

    entry = loaded[("homer-iliad", 100)]
    assert entry.status == "failed"
    assert entry.facts is None
    assert entry.error == "boom"


def test_later_line_for_the_same_key_overrides_the_earlier_one(tmp_path):
    path = tmp_path / ".checkpoint.jsonl"
    append_checkpoint(path, CheckpointEntry("homer-iliad", 100, "failed", error="first attempt failed"))
    facts = ExtractedFacts(entities=[ExtractedEntity(name="Achilles", type="hero")])
    append_checkpoint(path, CheckpointEntry("homer-iliad", 100, "ok", facts=facts))

    loaded = load_checkpoint(path)

    assert len(loaded) == 1  # same key, not two entries
    entry = loaded[("homer-iliad", 100)]
    assert entry.status == "ok"
    assert entry.facts.entities[0].name == "Achilles"


def test_distinct_keys_are_kept_separately(tmp_path):
    path = tmp_path / ".checkpoint.jsonl"
    append_checkpoint(path, CheckpointEntry("homer-iliad", 100, "ok", facts=ExtractedFacts()))
    append_checkpoint(path, CheckpointEntry("homer-iliad", 200, "ok", facts=ExtractedFacts()))
    append_checkpoint(path, CheckpointEntry("homer-odyssey", 100, "ok", facts=ExtractedFacts()))

    loaded = load_checkpoint(path)

    assert set(loaded.keys()) == {("homer-iliad", 100), ("homer-iliad", 200), ("homer-odyssey", 100)}


def test_append_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "output" / ".checkpoint.jsonl"
    append_checkpoint(path, CheckpointEntry("s", 0, "ok", facts=ExtractedFacts()))
    assert path.exists()


def test_blank_lines_are_ignored(tmp_path):
    path = tmp_path / ".checkpoint.jsonl"
    append_checkpoint(path, CheckpointEntry("s", 0, "ok", facts=ExtractedFacts()))
    path.write_text(path.read_text() + "\n\n")  # trailing blank lines

    loaded = load_checkpoint(path)
    assert len(loaded) == 1
