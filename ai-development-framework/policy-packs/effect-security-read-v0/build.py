#!/usr/bin/env python3
"""Build an ADR 0011 host read policy from this pack: exact-path allowlist, secret paths refused.

The runtime still enforces `sensitive-path-policy-v1` on every read; this pack only refuses to
allowlist paths matching that list plus `pack.json` extras (case-insensitive). No new engine:
the output is the existing pinned host policy, verified with `load_host_policy` before writing.
"""
import argparse
import copy
import json
import re
import sys
from pathlib import Path

from jsonschema import ValidationError

PACK = Path(__file__).resolve().parent
ADF = PACK.parents[1]
sys.path.insert(0, str(ADF))
from integration.local_read_adapter import digest, load_host_policy, schemas  # noqa: E402
from runtime.local_read_runtime import sensitive_path  # noqa: E402

_KEYS = ("deny_components", "deny_component_prefixes", "deny_component_suffixes")


def _load(relative): return json.loads((ADF / relative).read_text(encoding="utf-8"))
def _rehash(value, field): value[field] = digest({key: item for key, item in value.items() if key != field})


def manifest(): return json.loads((PACK / "pack.json").read_text(encoding="utf-8"))


def denylist():
    builtin, extra = _load("runtime/v1/policies/sensitive-path-policy-v1.json"), manifest()["deny"]
    return {key: sorted({item.lower() for item in builtin[key] + extra[key]}) for key in _KEYS}


def refused(path, deny):
    """Same lexical rules as the runtime, plus the pack denylist on the lower-cased path."""
    if not isinstance(path, str) or not path or path.startswith("/") or "\x00" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        return "invalid_path"
    return "sensitive_path" if sensitive_path(path.lower(), deny) else None


_SUB = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@:-]{0,127}\Z")


def principal_rules(principals, paths, deny):
    """ADR 0024: `sub -> exact paths`, each path already in the host allowlist (the ceiling) and never a secret."""
    rules = []
    for sub, allowed in (principals or {}).items():
        if not isinstance(sub, str) or not _SUB.fullmatch(sub) or not allowed:
            raise ValueError(f"refused: principal {sub!r} needs a valid sub and at least one path")
        problems = {path: reason for path in allowed if (reason := refused(path, deny) or ("outside_allowlist" if path not in paths else None))}
        if problems:
            raise ValueError(f"refused: principal {sub!r}: {problems}")
        rules.append({"sub": sub, "allowed_scopes": [{"kind": "filesystem", "path": path} for path in sorted(set(allowed))]})
    return sorted(rules, key=lambda item: item["sub"])


def build(run_id, paths, max_output_bytes=None, principals=None):
    deny, pack = denylist(), manifest()
    problems = {path: reason for path in paths if (reason := refused(path, deny))}
    if not paths or problems:
        raise ValueError(f"refused: {problems or 'no --allow path'}")
    by_principal = principal_rules(principals, set(paths), deny)
    budget = pack["max_output_bytes"] if max_output_bytes is None else max_output_bytes
    if type(budget) is not int or budget < 1:
        raise ValueError("refused: max_output_bytes must be a positive integer")
    scopes = [{"kind": "filesystem", "path": path} for path in sorted(set(paths))]
    examples = "tools/v1/examples"
    profile, policy = _load(f"{examples}/tool-profile/valid/read-worktree.json"), _load(f"{examples}/policy-bundle/valid/read-worktree.json")
    context = _load(f"{examples}/policy-context/valid/read-worktree.json")
    profile["operations"][0].update(supported_scopes=copy.deepcopy(scopes), max_risk={"level": "low", "max_output_bytes": budget})
    _rehash(profile, "profile_sha256")
    policy.update(policy_id=pack["pack_id"])
    policy["rules"][0].update(rule_id="allow-pinned-paths", profile_sha256=profile["profile_sha256"], allowed_scopes=copy.deepcopy(scopes), max_output_bytes=budget)
    if by_principal:
        policy["principal_rules"] = by_principal
    _rehash(policy, "policy_sha256")
    for name in ("organizational_constraints", "repository_constraints", "mode_constraints"):
        context[name].update(allowed_scopes=copy.deepcopy(scopes), max_output_bytes=budget)
    context["resolved_run_config_ref"]["run_id"] = run_id
    context["policy_ref"] = {"policy_id": policy["policy_id"], "policy_sha256": policy["policy_sha256"]}
    return {"schema_version": "1.0", "profiles": [profile], "policy": policy, "context": context}


def write(config, target):
    """Write, then reload through the adapter's own loader: a pin that does not load is never printed."""
    target = Path(target).resolve()
    target.write_text(json.dumps(config, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    pin = digest(config)
    load_host_policy(target, pin, schemas())
    return target, pin


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-id", required=True, help="host run/session id the policy is bound to (Claude: session_id)")
    parser.add_argument("--allow", action="append", default=[], help="repo-relative file path to allow; repeat")
    parser.add_argument("--principal", action="append", default=[], metavar="SUB=PATH[,PATH]", help="ADR 0024: restrict a principal (e.g. claude:backend-reviewer) to these --allow paths; repeat. Any --principal closes the policy to unnamed principals")
    parser.add_argument("--max-output-bytes", type=int, help="byte ceiling per read (default: pack.json)")
    parser.add_argument("--out", required=True, help="where to write the host policy JSON")
    args = parser.parse_args(argv)
    try:
        principals = {}
        for item in args.principal:
            sub, _, allowed = item.partition("=")
            principals.setdefault(sub, []).extend(part for part in allowed.split(",") if part)
        target, pin = write(build(args.run_id, args.allow, args.max_output_bytes, principals), args.out)
    except (ValueError, ValidationError) as error:  # never print a pin for a policy that does not load
        Path(args.out).unlink(missing_ok=True)
        print(f"effect-security-read-v0: {getattr(error, 'message', error)}", file=sys.stderr)
        return 2
    print(f"export ADF_READ_POLICY_FILE={target} ADF_READ_POLICY_SHA256={pin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
