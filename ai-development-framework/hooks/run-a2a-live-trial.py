#!/usr/bin/env python3
"""Repeatable A2A live trial: real HTTP against the loopback gateway, redacted report only.

Hermetic: a throwaway Git fixture (README.md + fake secrets), a host policy built by
policy-packs/effect-security-read-v0, and either an HS256 pilot secret that lives only in memory or
(--auth rs256) an openssl-backed test IdP whose private keys stay in a temp dir: the gateway only
sees the pinned public JWKS, exactly as with a real IdP.
The report keeps status, reason_code and ids; never a token, the secret, a path or file content.
Exit 1 when any case differs from the expected matrix, a record fails verify_record, or a leak is found.
"""
import argparse
import hashlib
import importlib.util
import json
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import integration.a2a_gateway as a2a  # noqa: E402

_PACK = importlib.util.spec_from_file_location("effect_security_read_v0", ROOT / "policy-packs/effect-security-read-v0/build.py")
pack = importlib.util.module_from_spec(_PACK); _PACK.loader.exec_module(pack)

ISSUER, AUDIENCE, SKILL = "adf-trial-idp", "adf-a2a-trial", "read_workspace_file"
PUBLIC, SECRET = "ADF trial fixture: public README.\n", "AKIA-trial-fake-secret-do-not-ship"
# (case, label, gateway, token, skill, path, expected status, expected reason_code)
CASES = [
    ("T1", "no Authorization", "plain", None, SKILL, "README.md", 401, "auth_missing"),
    ("T2a", "bad signature", "plain", "forged", SKILL, "README.md", 401, "token_signature_invalid"),
    ("T2b", "expired token", "plain", "expired", SKILL, "README.md", 401, "token_expired"),
    ("T3", "valid token, missing scope", "plain", "other_scope", SKILL, "README.md", 403, "insufficient_scope"),
    ("T4", "unknown skill", "plain", "reader", "write_workspace_file", "README.md", 403, "unknown_skill"),
    ("T5a", "secrets/ path not approved by host policy", "plain", "reader", SKILL, "secrets/db.txt", 200, "scope_not_allowlisted"),
    ("T5b", "path outside workspace", "plain", "reader", SKILL, "../etc/passwd", 400, "invalid_request"),
    ("T5c", "root .env (request schema refuses dotfile)", "plain", "reader", SKILL, ".env", 400, "invalid_request"),
    ("T5d", "nested .env (PDP scope rule)", "plain", "reader", SKILL, "config/.env", 200, "invalid_scope"),
    ("T6", "approved path README.md", "plain", "reader", SKILL, "README.md", 200, "read_delivered"),
    ("T7a", "input-required pause", "confirm", "reader", SKILL, "README.md", 200, "input_required"),
    ("T7b", "human confirm resume", "confirm", "human", SKILL, "README.md", 200, "read_delivered"),
]


def _git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


def fixture(base):
    repo = base / "repo"
    for directory in ("config", "secrets"): (repo / directory).mkdir(parents=True)
    (repo / "README.md").write_text(PUBLIC)
    for name in (".env", "config/.env", "secrets/db.txt"): (repo / name).write_text(SECRET)
    _git(repo, "init", "-q"); _git(repo, "config", "user.email", "trial@example.invalid"); _git(repo, "config", "user.name", "trial")
    _git(repo, "add", "-f", "."); _git(repo, "commit", "-qm", "fixture")
    return repo


def tokens(mint, forge):
    """`forge` signs with a key the gateway does not trust (same kid for RS256)."""
    claims = lambda scope, exp=300: {"iss": ISSUER, "aud": AUDIENCE, "sub": "agent-alpha", "scope": scope, "exp": int(time.time()) + exp}
    return {None: None, "forged": forge(claims("workspace:read")), "expired": mint(claims("workspace:read", -60)),
            "other_scope": mint(claims("other:read")), "reader": mint(claims("workspace:read")),
            "human": mint(claims(f"workspace:read {a2a.CONFIRM_SCOPE}"))}


def _openssl(*args, data=None): return subprocess.run(["openssl", *args], input=data, check=True, capture_output=True).stdout


class OpensslIdP:
    """Test IdP only: RSA-2048 key and RS256 (PKCS#1 v1.5) signatures from the openssl CLI, an
    implementation independent of the gateway's stdlib verifier."""
    KID = "trial-k1"

    def __init__(self, base, name):
        self.key = base / f"{name}.pem"
        _openssl("genrsa", "-out", str(self.key), "2048")

    def jwk(self):
        n = int(_openssl("rsa", "-in", str(self.key), "-noout", "-modulus").decode().strip().split("=", 1)[1], 16)
        return {"kty": "RSA", "kid": self.KID, "n": a2a._b64encode(n.to_bytes((n.bit_length() + 7) // 8, "big")), "e": "AQAB", "alg": "RS256", "use": "sig"}

    def mint(self, claims):
        segment = lambda value: a2a._b64encode(json.dumps(value, separators=(",", ":")).encode())
        signing = f"{segment({'alg': 'RS256', 'typ': 'JWT', 'kid': self.KID})}.{segment(claims)}"
        return f"{signing}.{a2a._b64encode(_openssl('dgst', '-sha256', '-sign', str(self.key), data=signing.encode()))}"


def authority(auth, base):
    """-> (validator, mint, forge, auth_mode, secret material the report must never contain)."""
    if auth == "hs256":
        secret = secrets.token_bytes(32)
        mint = lambda claims: a2a.mint_hs256(claims, secret)
        return a2a.HS256TokenValidator(secret, ISSUER, AUDIENCE), mint, lambda claims: a2a.mint_hs256(claims, secrets.token_bytes(32)), "hs256_pilot", [secret.hex()]
    idp, rogue = OpensslIdP(base, "idp"), OpensslIdP(base, "rogue")
    jwks = base / "jwks.json"
    jwks.write_text(json.dumps({"keys": [idp.jwk()]}))
    validator = a2a.RS256JwksValidator(str(jwks), hashlib.sha256(jwks.read_bytes()).hexdigest(), ISSUER, AUDIENCE)
    return validator, idp.mint, rogue.mint, "rs256_jwks_openssl_test_idp", [idp.key.read_text(), "PRIVATE KEY"]


def serve(gateway):
    server = a2a.make_server(gateway, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def post(server, token, skill, path, task_id=None):
    message = {"kind": "message", "role": "user", "messageId": "m1", "parts": [{"kind": "data", "data": {"skill": skill, "arguments": {"path": path}}}], **({"taskId": task_id} if task_id else {})}
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {"message": message}}).encode()
    headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}
    request = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}/", data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response: return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error: return error.code, json.loads(error.read())


def verified(evidence, record_id, schemas):
    """Re-verify from disk, as an auditor would: record + its bundle through verify_record."""
    if record_id is None: return None
    record = json.loads((evidence / "_a2a" / f"{record_id}.json").read_text())
    bundle = next(iter(evidence.glob(f"*/{record['bundle_id']}.json")), None) if record["bundle_id"] else None
    return a2a.verify_record(record, json.loads(bundle.read_text()) if bundle else None, schemas)


def row(case, label, status, payload, expected, evidence, schemas):
    result = payload.get("result") or {}
    error = (payload.get("error") or {}).get("data") or {}
    audit = result.get("audit") or error.get("audit") or {}
    reason = result.get("reason_code") or error.get("reason_code")
    record_id = audit.get("record_id")
    return {"case": case, "label": label, "status": status, "reason_code": reason, "outcome": result.get("outcome") or audit.get("outcome") or "deny",
            "task_state": ((result.get("task") or {}).get("status") or {}).get("state"), "content_delivered": "content" in result,
            "decision_id": audit.get("decision_id"), "bundle_id": audit.get("bundle_id"), "record_id": record_id,
            "verify_record": verified(evidence, record_id, schemas), "expected": {"status": expected[0], "reason_code": expected[1]},
            "as_expected": (status, reason) == expected}


def run(trial_id, out_dir, evidence, auth="hs256"):
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp).resolve()
        repo = fixture(base)
        validator, mint, forge, auth_mode, material = authority(auth, base)
        policy_path, pin = pack.write(pack.build(trial_id, ["README.md"], 4096), base / "host-policy.json")
        common = dict(trusted_repository=repo, trusted_revision="HEAD", evidence_dir=evidence, host_policy_path=policy_path, host_policy_sha256=pin, max_output_bytes=4096, port=0, workspace_parent=base)
        servers = {"plain": serve(a2a.A2AGateway(validator, **common)), "confirm": serve(a2a.A2AGateway(validator, **common, confirm_skills={SKILL}))}
        minted, schemas, rows, task_id, raw = tokens(mint, forge), a2a.schemas(), [], None, []
        try:
            for case, label, gateway, token, skill, path, status, reason in CASES:
                code, payload = post(servers[gateway], minted[token], skill, path, task_id if case == "T7b" else None)
                raw.append(json.dumps(payload))
                rows.append(row(case, label, code, payload, (status, reason), evidence, schemas))
                task_id = ((payload.get("result") or {}).get("task") or {}).get("id", task_id)
        finally:
            for server in servers.values(): server.shutdown(); server.server_close()
        report = json.dumps(rows)
        forbidden = [SECRET, PUBLIC.strip(), *material, str(base), *filter(None, minted.values())]
        leaks = sum(value in report for value in forbidden)
        assert any(PUBLIC.strip() in item for item in raw), "T6 must have delivered the fixture"  # the leak scan is not vacuous
    summary = {"trial_id": trial_id, "commit": _git(ROOT, "rev-parse", "--short", "HEAD"), "auth_mode": auth_mode, "policy_pack": pack.manifest()["pack_id"],
               "cases": {item["case"]: item["status"] for item in rows}, "reason_codes": {item["case"]: item["reason_code"] for item in rows},
               "as_expected": sum(item["as_expected"] for item in rows), "total": len(rows),
               "records": sum(item["record_id"] is not None for item in rows), "bundles": len({item["bundle_id"] for item in rows if item["bundle_id"]}),
               "verify_record_true": sum(item["verify_record"] is True for item in rows), "verify_record_false": sum(item["verify_record"] is False for item in rows),
               "redaction_leaks": leaks, "otel": "emitted" if a2a.os.environ.get("ADF_OTEL_ENABLED") == "1" else "disabled",
               "not_measured": ["jaeger_spans", "latency", "rs256_jwks", "tls_proxy", "langfuse"]}
    target = out_dir / trial_id
    target.mkdir(parents=True, exist_ok=False)
    (target / "rows.json").write_text(json.dumps(rows, indent=1) + "\n")
    (target / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    lines = [f"# A2A live trial · {trial_id}", "", f"Commit `{summary['commit']}` · {summary['auth_mode']} · policy pack `{summary['policy_pack']}` · OTel {summary['otel']}", "",
             f"**{summary['as_expected']}/{summary['total']} as expected** · records {summary['records']} · verify_record true {summary['verify_record_true']} · leaks {leaks}", "",
             "| Case | Label | HTTP | reason_code | outcome | verify_record | ok |", "| --- | --- | --- | --- | --- | --- | --- |",
             *(f"| {r['case']} | {r['label']} | {r['status']} | `{r['reason_code']}` | {r['outcome']} | {r['verify_record']} | {'✓' if r['as_expected'] else '✗'} |" for r in rows), "",
             "HTTP 200 with `outcome=deny` is a decision, not a success: clients must read `result.outcome`.",
             "Not measured here: " + ", ".join(summary["not_measured"]) + ". Generated by `make a2a-live-trial`."]
    (target / "report.md").write_text("\n".join(lines) + "\n")
    ok = summary["as_expected"] == summary["total"] and summary["verify_record_false"] == 0 and leaks == 0
    return ok, target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trial-id", default="a2a-live-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--out-dir", type=Path, default=ROOT / "docs/observability/trials/a2a-live")
    parser.add_argument("--auth", choices=("hs256", "rs256"), default="hs256", help="rs256 needs the openssl CLI (test IdP, pinned JWKS)")
    parser.add_argument("--evidence-dir", type=Path, help="default: docs/observability/evidence/_a2a_trials/<trial_id> (gitignored)")
    args = parser.parse_args(argv)
    evidence = (args.evidence_dir or ROOT / "docs/observability/evidence/_a2a_trials" / args.trial_id).resolve()
    if args.auth == "rs256" and shutil.which("openssl") is None:
        print("skipped: --auth rs256 needs the openssl CLI", file=sys.stderr)
        return 2
    ok, target = run(args.trial_id, args.out_dir.resolve(), evidence, args.auth)
    print(f"{'✓' if ok else '✗'} {target / 'report.md'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
