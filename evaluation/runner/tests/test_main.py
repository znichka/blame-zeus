"""Track D1/D5 (DEV-105) — `query_once` records per-request elapsed seconds.

A timer around the existing transport/retry logic, not a redesign (D1's own
wording) — these tests exercise it via the injectable `Transport` type, no
live server needed, matching this package's `no live LLM calls in tests` /
`no live server in tests` convention.
"""

from __future__ import annotations

import time

from runner.config import load_config
from runner.__main__ import TransportError, query_once

CFG = load_config()


def test_query_once_records_elapsed_seconds_on_success():
    def slow_ok_transport(method, url, body, timeout):
        time.sleep(0.05)
        return 200, {"answer": "hi", "routeDecision": "RAG", "serviceError": False}

    raw, parsed = query_once(CFG, "Q?", debug=False, transport=slow_ok_transport)

    assert raw["_elapsedSeconds"] >= 0.05
    assert "_runnerNote" not in raw
    assert parsed.answer == "hi"


def test_query_once_records_elapsed_seconds_including_retries_on_transport_error():
    calls = {"n": 0}

    def always_fails(method, url, body, timeout):
        calls["n"] += 1
        time.sleep(0.02)
        raise TransportError("connection refused")

    raw, parsed = query_once(CFG, "Q?", debug=False, transport=always_fails, retries=1)

    assert calls["n"] == 2  # initial attempt + 1 retry, per ADR-018 §Decision 4
    assert raw["_runnerNote"] == "transport error: connection refused"
    assert raw["_elapsedSeconds"] >= 0.04  # both attempts' sleeps are included
    assert parsed.service_error is True


def test_query_once_records_elapsed_seconds_on_4xx_no_retry():
    def bad_request(method, url, body, timeout):
        return 400, {"error": "bad request"}

    raw, _parsed = query_once(CFG, "Q?", debug=False, transport=bad_request)

    assert raw["_runnerNote"] == "HTTP 400"
    assert isinstance(raw["_elapsedSeconds"], float)
    assert raw["_elapsedSeconds"] >= 0
