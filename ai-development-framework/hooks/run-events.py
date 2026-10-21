"""Opt-in instrumentation of the Bash eval gate; no agent, runtime or replay engine."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone


ROOT = Path(__file__).absolute().parent.parent
RUNNER = ROOT / "hooks/eval-agent-flow.sh"
SCHEMAS = ROOT / "contracts/v1"
try:
    GATE_SCHEMA = json.loads((SCHEMAS / "gate-result.schema.json").read_text(encoding="utf-8"))
    EVENT_SCHEMA = json.loads((SCHEMAS / "run-event.schema.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    print("events v1: contracts unavailable or invalid", file=sys.stderr)
    raise SystemExit(2)


def require(condition: bool) -> None:
    if not condition:
        raise ValueError("invalid v1 input or contract")


def identifier(value: str) -> None:
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value) is not None)


def fields(value: dict, schema: dict) -> None:
    require(type(value) is dict and set(value) == set(schema["required"]))


def number(value, integer: bool = False) -> None:
    require(type(value) in ((int,) if integer else (int, float)))
    require(math.isfinite(value) and value >= 0)


def text(value) -> None:
    require(isinstance(value, str) and bool(value))


def refs(value) -> None:
    require(type(value) is list)
    for item in value:
        text(item)


def validate_gate(gate: dict) -> None:
    """Only the GateResult 1.0 shape, not a general JSON Schema interpreter."""
    fields(gate, GATE_SCHEMA)
    require(gate["schema_version"] == "1.0")
    for key in ("gate_id", "run_id"):
        identifier(gate[key])
    for key in ("category", "status"):
        require(gate[key] in GATE_SCHEMA["properties"][key]["enum"])
    require(type(gate["required"]) is bool)
    for key in ("reason_code", "checker_version"):
        text(gate[key])
    if gate["duration_seconds"] is not None:
        number(gate["duration_seconds"])
    require(gate["exit_code"] is None or type(gate["exit_code"]) is int)
    refs(gate["evidence_refs"])
    require(isinstance(gate["input_digest"], str) and
            re.fullmatch(r"[0-9a-f]{64}", gate["input_digest"]) is not None)


def validate_event(event: dict) -> None:
    """Validate exactly the four published payloads; reject unknown fields/types."""
    fields(event, EVENT_SCHEMA)
    require(event["schema_version"] == "1.0")
    for key in ("event_id", "run_id", "task_id"):
        identifier(event[key])
    number(event["sequence"], integer=True)
    require(event["sequence"] >= 1)
    text(event["timestamp"])
    require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", event["timestamp"]) is not None)
    datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    fields(event["source"], EVENT_SCHEMA["properties"]["source"])
    for value in event["source"].values():
        text(value)
    refs(event["artifact_refs"])
    kind, payload = event["type"], event["payload"]
    require(kind in EVENT_SCHEMA["properties"]["type"]["enum"])
    if kind == "gate.finished":
        validate_gate(payload)
        require(payload["run_id"] == event["run_id"])
        return
    fields(payload, EVENT_SCHEMA["definitions"][kind])
    validate_payload(kind, payload)


def validate_payload(kind: str, payload: dict) -> None:
    if kind == "run.started":
        identifier(payload["case"])
        for key in ("repo_revision", "instrumentation_version"):
            text(payload[key])
    elif kind == "gate.started":
        identifier(payload["gate_id"])
        require(payload["category"] in GATE_SCHEMA["properties"]["category"]["enum"])
        require(type(payload["required"]) is bool)
    else:
        require(payload["outcome"] in ("success", "failure", "skipped", "error"))
        if payload["duration_seconds"] is not None:
            number(payload["duration_seconds"])
        require(all(payload[key] is None for key in ("tokens_in", "tokens_out", "cost_usd")))


def directory(path: Path, create: bool = False) -> int:
    """Walk using directory FDs, refusing symlinks in every component."""
    fd = os.open(path.anchor or ".", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts:
            if part == path.anchor:
                continue
            require(part not in ("..", "."))
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def new_stream(adf: Path, run_id: str):
    parent = directory(adf / "docs/observability/runs", create=True)
    try:
        os.mkdir(run_id, mode=0o700, dir_fd=parent)  # exclusive ownership; never resume
        child = os.open(run_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            fd = os.open("events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=child)
            return os.fdopen(fd, "wb", buffering=0)
        finally:
            os.close(child)
    finally:
        os.close(parent)


def fixture_digest(fixture: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(fixture.rglob("*")):
        require(not path.is_symlink())
        if path.is_file() and "__pycache__" not in path.parts:
            digest.update(path.relative_to(fixture).as_posix().encode("utf-8") + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii") + b"\n")
    return digest.hexdigest()


def shell(body: str, *args: str, check: bool = True, discard: bool = False) -> subprocess.CompletedProcess:
    # Body and function names are literals below. Data travels only as positional args.
    return subprocess.run(["bash", "-c", 'set -e; source "$1"; shift; ' + body,
                           "events-v1", str(RUNNER), *args],
                          stdout=subprocess.DEVNULL if discard else subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True, check=check)


def check_stream(adf: Path, run_id: str, stream) -> None:
    fd = directory(adf / "docs/observability/runs" / run_id)
    try:
        visible = os.stat("events.jsonl", dir_fd=fd, follow_symlinks=False)
        opened = os.fstat(stream.fileno())
        require((visible.st_dev, visible.st_ino) == (opened.st_dev, opened.st_ino))
        require(opened.st_nlink == 1)
    finally:
        os.close(fd)


def append_event(stream, event: dict) -> None:
    validate_event(event)
    data = (json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    offset = stream.tell()
    try:
        if stream.write(data) != len(data):
            raise OSError("short trace write")
        os.fsync(stream.fileno())
    except OSError:
        # Preserve earlier events, discard only this unsuccessful append (not history).
        os.ftruncate(stream.fileno(), offset)
        raise


def check_projection(adf: Path, case: str) -> None:
    obs = adf / "docs/observability"
    for path in (obs / "events.jsonl", obs / "trajectories",
                 obs / "trajectories" / ("eval-" + case + ".trajectory.md"),
                 adf / "docs/evals/results.csv"):
        require(not path.is_symlink())
        if path.is_file():
            require(path.stat().st_nlink == 1)


def inputs(case: str):
    identifier(case)
    adf = Path(os.environ.get("ADF", "ai-development-framework")).absolute()
    fd = directory(adf)
    os.close(fd)
    fixture = adf / "docs/evals/fixtures" / case
    fd = directory(fixture)
    os.close(fd)
    trajectory = adf / "docs/evals/runs" / (case + ".trajectory.md")
    require(trajectory.is_file() and not trajectory.is_symlink())
    lang, need = shell('detect_lang "$1"', str(fixture)).stdout.split()
    require((lang, need) in (("js", "node"), ("py", "python3")))
    iters = shell('field iterations "$1"', str(trajectory)).stdout.strip() or "na"
    tokens = shell('field est_tokens "$1"', str(trajectory)).stdout.strip() or "na"
    return adf, fixture, lang, need, iters, tokens


def run(case: str) -> int:
    if os.environ.get("ADF_EVAL_WRITE") == "0":
        print("eval_persistence_disabled", file=sys.stderr)
        return 2
    run_id = os.environ.get("RUN_ID", str(uuid.uuid4()))
    identifier(run_id)
    adf, fixture, lang, need, iters, tokens = inputs(case)
    digest = fixture_digest(fixture)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    started = time.monotonic()
    with new_stream(adf, run_id) as stream:
        sequence = 0

        def emit(kind, payload):
            nonlocal sequence
            sequence += 1
            event = dict(schema_version="1.0", event_id=str(uuid.uuid4()), run_id=run_id,
                         task_id=case, sequence=sequence,
                         timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                         type=kind, source=dict(component="eval-agent-flow", version="1.0"),
                         payload=payload, artifact_refs=[])
            check_stream(adf, run_id, stream)
            append_event(stream, event)

        emit("run.started", dict(case=case, repo_revision=revision, instrumentation_version="1.0"))
        gate_id = case + "." + ("node-test" if lang == "js" else "unittest")
        emit("gate.started", dict(gate_id=gate_id, category="functional", required=True))
        gate = execute_gate(fixture, lang, need, run_id, gate_id, digest)
        emit("gate.finished", gate)
        status = gate["status"]
        resolved, legacy_gate, outcome = {
            "pass": ("yes", "pass", "success"), "fail": ("no", "fail", "failure"),
            "skipped": ("na", "skipped-no-" + need, "skipped"),
        }[status]
        check_projection(adf, case)
        shell('project_case "$@"', case, resolved, legacy_gate, iters, tokens,
              str(int(time.monotonic() - started)))
        emit("run.completed", dict(outcome=outcome, duration_seconds=time.monotonic() - started,
                                   tokens_in=None, tokens_out=None, cost_usd=None))
    print("events v1: " + run_id + " (" + status + ")")
    return int(status == "fail")


def execute_gate(fixture, lang, need, run_id, gate_id, digest):
    started = time.monotonic()
    code, duration, version = None, None, need + ":unavailable"
    status, reason = "skipped", "runtime_unavailable"
    if shutil.which(need):
        raw_version = subprocess.check_output([need, "--version"], text=True, stderr=subprocess.DEVNULL).strip()
        match = re.fullmatch(r"(?:Python |v)([0-9]+\.[0-9]+\.[0-9]+)", raw_version)
        version = need + ":" + (match[1] if match else "unknown")
        code = shell('run_gate "$1" "$2"', str(fixture), lang, check=False, discard=True).returncode
        duration = time.monotonic() - started
        status, reason = ("pass", "gate_passed") if code == 0 else ("fail", "gate_failed")
    return dict(schema_version="1.0", gate_id=gate_id, run_id=run_id, category="functional",
                required=True, status=status, reason_code=reason, duration_seconds=duration,
                exit_code=code, evidence_refs=[], checker_version=version, input_digest=digest)


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 2)
        sys.exit(run(sys.argv[1]))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        # Do not echo paths, arguments, environment, tool output or raw exceptions.
        print("events v1: invalid input, contract or trace; run not completed", file=sys.stderr)
        sys.exit(2)
