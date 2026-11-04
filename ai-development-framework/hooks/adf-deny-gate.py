#!/usr/bin/env python3
"""ADR 0028 slice 1a: deny-only PreToolUse gate for tools ADF does not mediate.

Grep/Glob (read-equivalent) are denied on `sensitive_path_policy_v1` paths; Edit/Write/MultiEdit/NotebookEdit
are denied on those plus `agent_config_policy_v1` (agent, IDE and CI configuration that later executes) and
on anything under `$ADF_HOME`. Everything else returns no decision, so the client's own permissions apply.
Paths only: the gate never opens a file, never inspects content, never persists evidence (deny without bundle).
Root comes from the host (`ADF_TRUSTED_REPOSITORY`, set by adf-read-hook.py), never from the payload.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from integration import mcp_registry  # noqa: E402
from integration.adapter_attempt import AttemptJournal  # noqa: E402
from integration.local_read_adapter import schemas as _schemas  # noqa: E402
from integration.otel_export import emit_local_read  # noqa: E402
from integration.read_gate_host import local_principal  # noqa: E402
import time  # noqa: E402
from runtime.local_read_runtime import sensitive_path  # noqa: E402

_READ_TOOLS = {"Grep": "path", "Glob": "path"}
_WRITE_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
_NETWORK_TOOLS = {"WebFetch"}
_NETWORK_BASH = re.compile(r"(?<![\w./-])(curl|wget)(?![\w-])")
# ADR 0028 1c: a run that tried to reach a sensitive path may not open a network channel afterwards (trifecta leg 3).
_TAINTING = {"sensitive_path_denied", "sensitive_argument_rejected", "invalid_scope", "uncovered_read_denied_sensitive", "uncovered_write_denied_sensitive"}
_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
# ADR 0028 1b: a closed grammar of Bash read-equivalents. Path only; everything the parser cannot see through is ambiguous.
_READ_COMMANDS = {"cat", "head", "tail", "less", "more", "sed", "awk", "grep", "egrep", "fgrep", "rg", "strings", "xxd", "hexdump", "od", "nl", "tac", "cut", "sort", "uniq", "wc", "diff", "cmp", "file", "stat", "bat"}
_PATTERN_FIRST = {"sed", "awk", "grep", "egrep", "fgrep", "rg"}  # first operand is a script/pattern, not a path
_INTERPRETERS = {"python", "python3", "python2", "node", "perl", "ruby", "php", "deno", "bun"}
_OPAQUE = {"eval", "sh", "bash", "zsh", "dash", "ksh", "fish", "xargs", "source", "."}
_WRAPPERS = {"env", "nice", "nohup", "command", "exec", "builtin", "sudo", "doas", "stdbuf", "time"}
_WRAPPERS_ARG = {"timeout", "nice", "ionice"}  # may take one numeric/flag operand before the real command
_EXPANSION = re.compile(r"[$`<>]")  # checked outside single quotes: substitution, expansion, redirection
_GLOB = re.compile(r"[*?\[\]~{}]")  # checked on path operands only
_SINGLE_QUOTED = re.compile(r"'[^']*'")
_SEPARATORS = set(";|&\n()")
# Options that take the next token as an argument (never a path) and options whose argument IS a path (a read).
_OPT_ARG = {
    "grep": {"-e", "--regexp", "-m", "--max-count", "-A", "-B", "-C", "-d", "--directories", "--include", "--exclude", "--exclude-dir", "--color"},
    "rg": {"-e", "--regexp", "-t", "--type", "-T", "-g", "--glob", "--iglob", "-m", "--max-count", "-A", "-B", "-C", "--after-context", "--before-context", "--context", "-j", "--threads", "--max-depth", "--color"},
    "sed": {"-e", "--expression", "-l"}, "awk": {"-v", "-F"}, "head": {"-n", "-c", "--lines", "--bytes"}, "tail": {"-n", "-c", "--lines", "--bytes", "--pid"},
    "cut": {"-d", "-f", "-b", "-c"}, "sort": {"-k", "-t", "-S", "-T"}, "od": {"-j", "-N", "-t", "-w", "-A"}, "xxd": {"-l", "-s", "-c", "-g"}, "strings": {"-n", "-t"},
    "diff": {"-U", "-C", "-I", "-x"}, "uniq": {"-f", "-s", "-w"}, "wc": set(), "nl": {"-b", "-n", "-s", "-w"},
}
_OPT_PATH = {"grep": {"-f", "--file"}, "egrep": {"-f", "--file"}, "fgrep": {"-f", "--file"}, "rg": {"-f", "--file"}, "sed": {"-f", "--file"}, "awk": {"-f", "--file"}, "sort": {"-o", "--output"}}
_PATTERN_OPTS = {"-e", "--regexp", "-f", "--file", "--expression"}  # given one of these, every positional is a path
for alias in ("egrep", "fgrep"):
    _OPT_ARG[alias] = _OPT_ARG["grep"]
_SENSITIVE = json.loads((ROOT / "runtime/v1/policies/sensitive-path-policy-v2.json").read_text(encoding="utf-8"))
_AGENT_CONFIG = json.loads((ROOT / "runtime/v1/policies/agent-config-policy-v1.json").read_text(encoding="utf-8"))


def _decision(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": f"adf: {reason}"}}


def _under(path, base):
    return path == base or path.startswith(base.rstrip("/") + "/")


def _relatives(target, root):
    """Lexical and real relative paths of `target` under `root`; a path outside yields nothing."""
    absolute = target if target.startswith("/") else os.path.join(root, target)
    out = set()
    for candidate, base in ((os.path.normpath(absolute), root), (os.path.realpath(absolute), os.path.realpath(root))):
        if _under(candidate, base) and candidate != base:
            out.add(os.path.relpath(candidate, base))
    return out


def _agent_config(rel):
    return any(part in _AGENT_CONFIG["deny_components"] for part in rel.split("/")) or any(_under(rel, deny) for deny in _AGENT_CONFIG["deny_paths"])


def _mcp(tool):
    """ADR 0031 slice 1: names only, against the host-pinned registry; unconfigured -> no decision."""
    try:
        config = mcp_registry.configured()
        if config is None:
            return None
        registry = mcp_registry.load(*config)
        reason = mcp_registry.decide(tool, registry)
        if reason is None:  # ADR 0031 slice 2: the client's definition of the server must still be the pinned one
            server = tool.split("__", 2)[1]
            reason = mcp_registry.check_definition(server, registry["servers"][server], os.environ.get("ADF_TRUSTED_REPOSITORY", "/"), os.environ.get("HOME") or str(Path.home()))
    except mcp_registry.RegistryInvalid:
        return _decision("mcp_registry_invalid")
    return _decision(reason) if reason else None


def network_shaped(payload):
    """True for WebFetch and for Bash whose command names curl/wget; the dispatcher routes those here first."""
    tool = payload.get("tool_name") if isinstance(payload, dict) else None
    command = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) and isinstance(payload.get("tool_input"), dict) else None
    return tool in _NETWORK_TOOLS or (tool == "Bash" and isinstance(command, str) and _NETWORK_BASH.search(command) is not None)


def _run_tainted(evidence_dir, run_id):
    """Journal-only, path-free: did this run already attempt a sensitive path? Any unreadable journal counts as tainted."""
    project_dir = Path(evidence_dir).parent  # evidence/<project>/<day>: a session may cross midnight
    try:
        for path in project_dir.rglob("_attempts/*.jsonl"):
            try:
                events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            except (OSError, ValueError):
                return True
            for event in events:
                if isinstance(event, dict) and event.get("phase") == "completed" and event.get("run_id") == run_id and (event.get("payload") or {}).get("reason_code") in _TAINTING:
                    return True
    except OSError:
        return True
    return False


def _segments(command):
    """Split on ; | & ( ) and newlines *outside* quotes; a backslash outside quotes escapes the next char.
    Unbalanced quotes propagate as a segment shlex will refuse (-> ambiguous)."""
    out, buf, quote, i = [], [], None, 0
    while i < len(command):
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            elif ch == "\\" and quote == '"' and i + 1 < len(command):
                buf.append(command[i + 1]); i += 1
        elif ch in ("'", '"'):
            quote = ch; buf.append(ch)
        elif ch == "\\" and i + 1 < len(command):
            buf.append(ch); buf.append(command[i + 1]); i += 1
        elif ch in _SEPARATORS:
            out.append("".join(buf)); buf = []
        else:
            buf.append(ch)
        i += 1
    out.append("".join(buf))
    return [part.strip() for part in out if part.strip()]


def _strip_wrappers(tokens):
    while tokens:
        head = tokens[0].rsplit("/", 1)[-1]
        if head in _WRAPPERS_ARG:
            tokens = tokens[1:]
            while tokens and (tokens[0].startswith("-") or re.fullmatch(r"[0-9]+[smhd]?", tokens[0])):
                tokens = tokens[1:]
        elif head in _WRAPPERS:
            tokens = tokens[1:]
            while tokens and (tokens[0].startswith("-") or "=" in tokens[0]):
                tokens = tokens[1:]
        else:
            return tokens
    return tokens


def _operands(tokens):
    """-> (path operands, pattern given by option). `--` ends options; a bare `-` is stdin; an option that takes an
    argument consumes the next token (never a path) unless it is a path-taking option (then the argument is a read);
    `--opt=value` forms likewise."""
    name = tokens[0].rsplit("/", 1)[-1]
    takes, paths = _OPT_ARG.get(name, set()), _OPT_PATH.get(name, set())
    out, options_done, pattern_given, i = [], False, False, 1
    while i < len(tokens):
        token = tokens[i]
        if options_done or not token.startswith("-") or token == "-":
            if token != "-":
                out.append(token)
        elif token == "--":
            options_done = True
        elif "=" in token and token.startswith("--"):
            opt, value = token.split("=", 1)
            if opt in paths:
                out.append(value)
            if opt in _PATTERN_OPTS:
                pattern_given = True
        elif token in paths or token in takes:
            if token in _PATTERN_OPTS:
                pattern_given = True
            if i + 1 < len(tokens):
                if token in paths:
                    out.append(tokens[i + 1])
                i += 1
        i += 1
    return out, pattern_given


def bash_read(payload):
    """-> deny (sensitive path or ambiguous) or None (benign read, or not a read at all). Never admits."""
    command = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) and isinstance(payload.get("tool_input"), dict) else None
    if not isinstance(command, str):
        return None
    root = os.environ.get("ADF_TRUSTED_REPOSITORY") or "/"
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) and payload["cwd"].startswith("/") else root
    for segment in _segments(command):
        try:
            tokens = _strip_wrappers(shlex.split(segment, posix=True))
        except ValueError:
            return _decision("uncovered_bash_ambiguous")
        if not tokens:
            continue
        name = tokens[0].rsplit("/", 1)[-1]
        mentions_read = any(part.rsplit("/", 1)[-1] in _READ_COMMANDS for token in tokens[1:] for part in re.split(r"[\s;|&()]+", token) if part)
        if name in _OPAQUE and (mentions_read or any(("open(" in token or "readFile" in token or "File." in token) for token in tokens[1:])):
            return _decision("uncovered_bash_ambiguous")
        if name in _INTERPRETERS and any(flag in tokens[1:] for flag in ("-c", "-e", "-r", "--eval")) and any(("open(" in token or "readFile" in token or "File." in token or "IO." in token) for token in tokens[1:]):
            return _decision("uncovered_bash_ambiguous")
        if name not in _READ_COMMANDS:
            continue
        if _EXPANSION.search(_SINGLE_QUOTED.sub("", segment)):
            return _decision("uncovered_bash_ambiguous")
        operands, pattern_given = _operands(tokens)
        if name in _PATTERN_FIRST and not pattern_given:
            operands = operands[1:]  # the first positional is the pattern/script
        if any(_GLOB.search(operand) for operand in operands):
            return _decision("uncovered_bash_ambiguous")
        for operand in operands:
            absolute = os.path.normpath(operand if operand.startswith("/") else os.path.join(cwd, operand))
            candidates = {absolute, os.path.realpath(absolute)}
            if any(sensitive_path(candidate.lstrip("/"), _SENSITIVE) for candidate in candidates):
                return _decision("uncovered_read_denied_sensitive")
    return None


def journal_deny(payload, reason):
    """Two-event attempt journal for a deny that never reached the adapter; failure to journal never turns a deny into an allow."""
    evidence_dir, run_id = os.environ.get("ADF_EVIDENCE_DIR"), payload.get("session_id") if isinstance(payload, dict) else None
    if not evidence_dir or not isinstance(run_id, str) or not _RUN.fullmatch(run_id):
        return
    principal = local_principal(payload, "claude") if isinstance(payload, dict) else None
    try:
        journal = AttemptJournal(evidence_dir, run_id, _schemas()["adapter_attempt_event"], principal, adapter_id="deny-only-gate")
        try:
            journal.finish({"outcome": "deny", "reason_code": reason, "bundle_id": None})
        finally:
            journal.close()
    except Exception:
        pass


def emit_decision(payload, reason, start_ns):
    """ADR 0021 for this edge: one span per decision, after it; tool name, outcome, reason code and duration only."""
    tool = payload.get("tool_name") if isinstance(payload, dict) else None
    principal = local_principal(payload, "claude") if isinstance(payload, dict) else None
    agent_type = principal["sub"].split(":", 1)[1] if principal else None
    emit_local_read("deny_gate", {"outcome": "deny" if reason else "no_decision", "reason_code": reason, "bundle_id": None}, start_ns, hook=True, agent_type=agent_type, tool=tool if isinstance(tool, str) else None)


def gate(payload):
    """Path-only mapping to `deny` or None; a malformed payload in an enabled project denies. Every deny is journaled and spanned."""
    start_ns = time.time_ns()
    decision = _decide(payload)
    reason = decision["hookSpecificOutput"]["permissionDecisionReason"].removeprefix("adf: ") if decision is not None else None
    if reason:
        journal_deny(payload, reason)
    emit_decision(payload, reason, start_ns)
    return decision


def _decide(payload):
    tool = payload.get("tool_name") if isinstance(payload, dict) else None
    if network_shaped(payload):
        evidence_dir, run_id = os.environ.get("ADF_EVIDENCE_DIR"), payload.get("session_id")
        if not evidence_dir or not isinstance(run_id, str):
            return _decision("host_configuration_invalid")
        return _decision("uncovered_network_denied_after_sensitive_read") if _run_tainted(evidence_dir, run_id) else None
    if tool == "Bash":
        return bash_read(payload)  # ADR 0028 1b: after the cat gate passed the command through
    if isinstance(tool, str) and tool.startswith("mcp__"):
        return _mcp(tool)
    key = _READ_TOOLS.get(tool) or _WRITE_TOOLS.get(tool)
    if key is None:
        return _decision("unsupported_tool")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return _decision("unexpected_tool_input")
    target = tool_input.get(key)
    if target is None and tool in _READ_TOOLS:
        return None  # ponytail: Grep/Glob over the whole root stay a documented residual (ADR 0028)
    if not isinstance(target, str) or not target or "\x00" in target:
        return _decision("unexpected_tool_input")
    root = os.environ.get("ADF_TRUSTED_REPOSITORY")
    if not root or not root.startswith("/"):
        return _decision("host_configuration_invalid")
    write = tool in _WRITE_TOOLS
    adf_home = os.environ.get("ADF_HOME") or str(Path.home() / ".adf")
    absolute = target if target.startswith("/") else os.path.join(root, target)
    if write and any(_under(os.path.normpath(absolute), base) or _under(os.path.realpath(absolute), os.path.realpath(base)) for base in (adf_home,)):
        return _decision("uncovered_write_denied_agent_config")
    rels = _relatives(target, root)
    if any(sensitive_path(rel, _SENSITIVE) for rel in rels):
        return _decision("uncovered_write_denied_sensitive" if write else "uncovered_read_denied_sensitive")
    if write and any(_agent_config(rel) for rel in rels):
        return _decision("uncovered_write_denied_agent_config")
    return None


def main():
    try:
        decision = gate(json.loads(sys.stdin.read()))
    except Exception:
        decision = _decision("adapter_failed")
    if decision is not None:
        print(json.dumps(decision, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
