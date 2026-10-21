"""Host-only monotonic observations, separate from v1 evidence and authorization."""
import json
import os
import sys
import time
from pathlib import Path

from jsonschema import Draft7Validator

from integration.local_evidence_bundle import digest


STAGES = ("prepare", "decision", "read", "persistence", "cleanup", "total")
TIMING_SCHEMA = json.loads((Path(__file__).parent / "v2/schemas/attempt-timing.schema.json").read_text())


def timing_digest(record):
    return digest({"domain": "adapter-attempt-timing-v1", "record": {k: v for k, v in record.items() if k != "verification"}})


def verify_timing(record):
    try:
        if not Draft7Validator(TIMING_SCHEMA).is_valid(record) or record["verification"]["record_sha256"] != timing_digest(record):
            return False
        durations = record["durations_ms"]
        return all(value is None or value <= durations["total"] for value in durations.values())
    except Exception:
        return False


class AttemptTiming:
    def __init__(self):
        self.start = None
        self.nanoseconds = {}

    def call(self, stage, function, *args, **kwargs):
        started = time.monotonic_ns()
        try:
            return function(*args, **kwargs)
        finally:
            elapsed = time.monotonic_ns() - started
            self.nanoseconds[stage] = self.nanoseconds.get(stage, 0) + elapsed

    def record(self, return_state):
        record = {
            "schema_version": "1.0", "attempt_id": self.start["attempt_id"],
            "run_id": self.start["run_id"], "start_event_sha256": self.start["event_sha256"],
            "return_state": return_state,
            "durations_ms": {stage: self.nanoseconds[stage] // 1_000_000 if stage in self.nanoseconds else None for stage in STAGES},
            "provenance": {"kind": "host_adapter_timing", "collector_version": "1.0", "adapter_version": "1.0", "clock": "monotonic_ns", "unit": "ms", "total_boundary": "adapter_read_return_or_raise"},
        }
        record["verification"] = {"canonicalization": "json-c14n-v1", "record_sha256": timing_digest(record)}
        return record


def call_stage(timing, stage, function, *args, **kwargs):
    return function(*args, **kwargs) if timing is None else timing.call(stage, function, *args, **kwargs)


def persist_timing(record, evidence_dir):
    if not verify_timing(record):
        raise ValueError("timing_evidence_invalid")
    root = os.open(evidence_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            os.mkdir("_timings", mode=0o700, dir_fd=root)
        except FileExistsError:
            pass
        directory = os.open("_timings", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
    finally:
        os.close(root)
    try:
        fd = os.open(record["attempt_id"] + ".json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(directory)


def read_observed(adapter, run_id, path, budget, evidence_dir, principal=None):
    """Measure the adapter's return/raise; exporting the observation is outside this span."""
    timing, return_state = AttemptTiming(), "raised"
    try:
        result = timing.call("total", adapter.read, run_id, path, budget, timing=timing, principal=principal)
        return_state = "returned"
        return result
    finally:
        if timing.start is not None:
            try:
                persist_timing(timing.record(return_state), evidence_dir)
            except Exception:
                print("adf: timing_evidence_failed", file=sys.stderr)
