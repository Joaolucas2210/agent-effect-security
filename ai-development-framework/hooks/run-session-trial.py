#!/usr/bin/env python3
"""P0-D: project a closed local evidence directory into a redacted session report."""
import argparse
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

from integration.local_read_adapter import schemas
from integration.session_trial import build_session_report, verify_session_report


ROOT = Path(__file__).resolve().parent.parent
TRIALS_DIR = ROOT / "docs/observability/trials"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_MAX_FILES = 10000
_MAX_BYTES = 1 << 20


def _read_file(fd, name, lines=False):
    try:
        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                return None
            data = os.read(file_fd, _MAX_BYTES + 1)
            if len(data) > _MAX_BYTES:
                return None
            return [json.loads(line) for line in data.splitlines()] if lines else json.loads(data)
        finally:
            os.close(file_fd)
    except Exception:
        return None


def _files(root_fd, directory, suffix):
    try:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
    except FileNotFoundError:
        return []
    try:
        names = sorted(name for name in os.listdir(fd) if name.endswith(suffix))
        if len(names) > _MAX_FILES:
            raise ValueError("session_evidence_limit_exceeded")
        return [_read_file(fd, name, lines=suffix == ".jsonl") for name in names]
    finally:
        os.close(fd)


def collect_session(evidence_dir, trial_id, task_id, session_id, *, provenance=None):
    """Read only the fixed journal and run directories; never follow entry symlinks."""
    if any(not isinstance(value, str) or not _ID.fullmatch(value) for value in (trial_id, task_id, session_id)):
        raise ValueError("invalid_session_id")
    if not Path(evidence_dir).is_absolute():
        raise ValueError("session_evidence_dir_invalid")
    try:
        root_fd = os.open(evidence_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        raise ValueError("session_evidence_dir_invalid") from None
    try:
        journals = _files(root_fd, "_attempts", ".jsonl")
        bundles = _files(root_fd, session_id, ".json")
        timings = _files(root_fd, "_timings", ".json")
    finally:
        os.close(root_fd)
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return build_session_report(trial_id, task_id, session_id, journals, bundles, schemas(), created_at, timings=timings, provenance=provenance)


def persist_report(report, trials_dir=TRIALS_DIR):
    if not verify_session_report(report):
        raise ValueError("session_report_invalid")
    trials_dir = Path(trials_dir)
    trials_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = trials_dir / f"{report['trial_id']}-{report['session_id']}.v2.json"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--session-id", required=True)
    for field in ("agent-name", "agent-version", "revision-sha", "acceptance-sha256"):
        parser.add_argument(f"--{field}", default="")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    try:
        provenance = {field: getattr(args, field) for field in ("agent_name", "agent_version", "revision_sha", "acceptance_sha256")}
        report = collect_session(args.evidence_dir, args.trial_id, args.task_id, args.session_id, provenance=provenance if any(provenance.values()) else None)
        if not args.no_write:
            persist_report(report)
        print(f"session report: observed attempts {report['attempts_observed_total']}, valid bundles {report['bundles_valid_total']}, coverage {report['coverage']}")
        return 0
    except Exception:
        print("session_trial_failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
