"""P0-A redacted adapter lifecycle; never an admission or a replacement for a bundle."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import uuid

from jsonschema import Draft7Validator, FormatChecker
from referencing import Registry

from integration.local_evidence_bundle import digest


def event_digest(event):
    return digest({"domain": "adapter-attempt-event-v1", "event": {key: value for key, value in event.items() if key != "event_sha256"}})


def verify_attempt(events, schema):
    """Pure integrity/lifecycle check: complete is not success, and never authorization."""
    try:
        if not isinstance(events, list) or len(events) not in (1, 2) or not isinstance(schema, dict):
            return "invalid"
        Draft7Validator.check_schema(schema)
        validator = Draft7Validator(schema, format_checker=FormatChecker(), registry=Registry())
        if any(not validator.is_valid(event) or event["event_sha256"] != event_digest(event) for event in events):
            return "invalid"
        start = events[0]
        if start["phase"] != "started":
            return "invalid"
        if len(events) == 1:
            return "incomplete"
        end = events[1]
        if end["phase"] != "completed" or end["previous_event_sha256"] != start["event_sha256"] or any(end[key] != start[key] for key in ("attempt_id", "adapter_id", "run_id")):
            return "invalid"
        return "complete"
    except Exception:
        return "invalid"


class AttemptJournal:
    """One exclusively created two-event stream per attempt; no resume/overwrite."""
    def __init__(self, evidence_dir, run_id, schema, principal=None):
        self.cleanup_outcome = "not_attempted"
        self._completed = False
        self._directory, self._stream = None, None
        self._validator = Draft7Validator(schema, format_checker=FormatChecker(), registry=Registry())
        self._start = {"schema_version": "1.0", "canonicalization": "json-c14n-v1", "attempt_id": uuid.uuid4().hex, "adapter_id": "local-read-adapter", "run_id": run_id, "phase": "started", "previous_event_sha256": None, "payload": {"principal_sub": principal["sub"]} if isinstance(principal, dict) and isinstance(principal.get("sub"), str) else {}}  # ADR 0023: who asked, never a credential
        self._name = self._start["attempt_id"] + ".jsonl"
        try:
            evidence_dir = Path(evidence_dir)
            evidence_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            root = os.open(evidence_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                try: os.mkdir("_attempts", mode=0o700, dir_fd=root)
                except FileExistsError: pass
                self._directory = os.open("_attempts", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            finally:
                os.close(root)
            fd = os.open(self._name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self._directory)
            self._stream = os.fdopen(fd, "wb", buffering=0)
            self._append(self._start)
        except BaseException:
            self.close()
            raise

    def _append(self, event):
        event["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        event["event_sha256"] = event_digest(event)
        self._validator.validate(event)
        visible = os.stat(self._name, dir_fd=self._directory, follow_symlinks=False)
        opened = os.fstat(self._stream.fileno())
        if (visible.st_dev, visible.st_ino) != (opened.st_dev, opened.st_ino) or opened.st_nlink != 1:
            raise OSError("attempt_evidence_failed")
        data = (json.dumps(event, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        offset = self._stream.tell()
        try:
            if self._stream.write(data) != len(data):
                raise OSError("attempt_evidence_failed")
            os.fsync(self._stream.fileno())
        except OSError:
            os.ftruncate(self._stream.fileno(), offset)
            raise

    def finish(self, outcome):
        """Record the calculated result before return; this is not a consumer acknowledgement."""
        if self._completed:
            raise ValueError("attempt_already_completed")
        event = {**self._start, "phase": "completed", "previous_event_sha256": self._start["event_sha256"], "payload": {"outcome": outcome["outcome"], "reason_code": outcome["reason_code"], "bundle_id": outcome["bundle_id"], "cleanup_outcome": self.cleanup_outcome}}
        self._append(event)
        self._completed = True

    def close(self):
        try:
            if self._stream is not None: self._stream.close()
        finally:
            if self._directory is not None: os.close(self._directory)
