"""ADR 0024: a pinned policy that names principals is closed to anyone it does not name, and can only narrow the host allowlist."""
import copy
import importlib.util
import json
import secrets
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import integration.a2a_gateway as a2a
from integration.local_read_adapter import LocalReadAdapter, build_request, digest, load_host_policy, schemas
from tools.pdp import decide

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("effect_security_read_v0", ROOT / "policy-packs/effect-security-read-v0/build.py")
pack = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(pack)
ISSUER, AUDIENCE, RUN = "adf-test-idp", "adf-a2a-local", "run-principal"
BACKEND, SECURITY, STRANGER = "claude:backend-reviewer", "claude:security-reviewer", "claude:stranger"
FILES = {"src/backend/app.py": "backend code", "config/settings.yaml": "settings", "README.md": "readme"}


def principal(sub, exp=300):
    return {"schema_version": "1.0", "sub": sub, "scopes": ["workspace:read"], "act": [], "token_aud": "local-host", "authn_method": "bearer_jwt_hs256", "expires_at": int(time.time()) + exp}


def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


class PrincipalPolicyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(); self.repo = self.base / "repo"
        for name, text in FILES.items(): (self.repo / name).parent.mkdir(parents=True, exist_ok=True); (self.repo / name).write_text(text)
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "p@example.invalid"); git(self.repo, "config", "user.name", "p")
        git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "fixture")
        self.schemas = schemas()

    def policy(self, principals, name="policy"):
        config = pack.build(RUN, list(FILES), 64, principals)
        return pack.write(config, self.base / f"{name}.json")

    def decide_for(self, config, path, who):
        request = build_request({"snapshot_digest": "a" * 64}, RUN, path, 64, host_policy=config)
        return decide(request["intent"], request["profiles"], request["policy"], request["context"], self.schemas, principal=who)["stable_reason_code"]

    def test_pdp_closes_a_principal_policy_and_only_narrows_the_host_allowlist(self):
        config = pack.build(RUN, list(FILES), 64, {BACKEND: ["src/backend/app.py", "README.md"], SECURITY: ["config/settings.yaml"]})
        self.assertEqual(self.decide_for(config, "src/backend/app.py", principal(BACKEND)), "admit_read")
        self.assertEqual(self.decide_for(config, "config/settings.yaml", principal(BACKEND)), "scope_not_allowlisted_for_principal")
        self.assertEqual(self.decide_for(config, "config/settings.yaml", principal(SECURITY)), "admit_read")
        self.assertEqual(self.decide_for(config, "src/backend/app.py", principal(STRANGER)), "principal_not_allowlisted")
        self.assertEqual(self.decide_for(config, "src/backend/app.py", None), "principal_required", "a principal policy never admits an anonymous request")
        self.assertEqual(self.decide_for(config, "config/.env", principal(SECURITY)), "invalid_scope", "contract and host rules still come first")
        widened = copy.deepcopy(config); widened["policy"]["principal_rules"][0]["allowed_scopes"].append({"kind": "filesystem", "path": "secrets/db.txt"})
        pack._rehash(widened["policy"], "policy_sha256"); widened["context"]["policy_ref"]["policy_sha256"] = widened["policy"]["policy_sha256"]  # consistently re-pinned, still capped by the host allowlist
        self.assertEqual(self.decide_for(widened, "secrets/db.txt", principal(BACKEND)), "scope_not_allowlisted")
        plain = pack.build(RUN, list(FILES), 64)
        self.assertEqual(self.decide_for(plain, "src/backend/app.py", principal(STRANGER)), "admit_read", "no principal_rules: unchanged behaviour")
        self.assertEqual(self.decide_for(plain, "src/backend/app.py", None), "admit_read")

    def test_builder_refuses_what_the_pdp_would_never_admit_and_the_pin_covers_principals(self):
        for principals in ({BACKEND: ["docs/missing.md"]}, {BACKEND: ["config/.env"]}, {"bad sub": ["README.md"]}, {BACKEND: []}, {BACKEND: ["../README.md"]}):
            with self.subTest(principals=principals), self.assertRaises(ValueError): pack.build(RUN, list(FILES), 64, principals)
        target, pin = self.policy({BACKEND: ["README.md"]})
        loaded = load_host_policy(target, pin, self.schemas)
        self.assertEqual(loaded["policy"]["principal_rules"], [{"sub": BACKEND, "allowed_scopes": [{"kind": "filesystem", "path": "README.md"}]}])
        edited = json.loads(target.read_text()); edited["policy"]["principal_rules"][0]["sub"] = STRANGER
        target.write_text(json.dumps(edited))
        with self.assertRaises(ValueError): load_host_policy(target, pin, self.schemas)  # the pin covers principal_rules
        self.assertEqual(subprocess.run(["python3", str(ROOT / "policy-packs/effect-security-read-v0/build.py"), "--run-id", RUN, "--allow", "README.md", "--principal", f"{BACKEND}=config/settings.yaml", "--out", str(self.base / "cli.json")], capture_output=True, text=True).returncode, 2)
        self.assertFalse((self.base / "cli.json").exists(), "no pin is printed for a policy that does not load")

    def test_two_principals_through_the_a2a_edge_with_verifiable_evidence(self):
        target, pin = self.policy({"agent-backend": ["src/backend/app.py"], "agent-security": ["config/settings.yaml"]})
        secret = secrets.token_bytes(32); evidence = self.base / "evidence"
        gateway = a2a.A2AGateway(a2a.HS256TokenValidator(secret, ISSUER, AUDIENCE), self.repo, "HEAD", evidence, host_policy_path=str(target), host_policy_sha256=pin, max_output_bytes=64, port=0)
        def call(sub, path):
            token = a2a.mint_hs256({"iss": ISSUER, "aud": AUDIENCE, "sub": sub, "exp": int(time.time()) + 300, "scope": "workspace:read"}, secret)
            body = {"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {"message": {"kind": "message", "role": "user", "messageId": "m1", "parts": [{"kind": "data", "data": {"skill": "read_workspace_file", "arguments": {"path": path}}}]}}}
            status, payload = gateway.handle(f"Bearer {token}", json.dumps(body).encode())
            return status, payload["result"]
        status, result = call("agent-backend", "src/backend/app.py")
        self.assertEqual((status, result["outcome"], result["content"]), (200, "delivered", FILES["src/backend/app.py"]))
        status, result = call("agent-security", "src/backend/app.py")
        self.assertEqual((status, result["outcome"], result["reason_code"], "content" in result), (200, "deny", "scope_not_allowlisted_for_principal", False))
        status, result = call("agent-nobody", "README.md")
        self.assertEqual((result["outcome"], result["reason_code"]), ("deny", "principal_not_allowlisted"))
        records = [json.loads(path.read_text()) for path in (evidence / "_a2a").glob("*.json")]
        self.assertEqual(sorted(record["reason_code"] for record in records), ["principal_not_allowlisted", "read_delivered", "scope_not_allowlisted_for_principal"])
        for record in records:
            bundle = json.loads(next(evidence.glob(f"*/{record['bundle_id']}.json")).read_text())
            self.assertTrue(a2a.verify_record(record, bundle, self.schemas))
            self.assertNotIn("agent-", json.dumps(bundle), "bundles stay principal-free; the record carries who")

    def test_local_adapter_applies_the_principal_rules_too(self):
        target, pin = self.policy({BACKEND: ["README.md"]})
        adapter = LocalReadAdapter(self.repo, "HEAD", self.base / "evidence", host_policy_path=str(target), host_policy_sha256=pin)
        self.assertEqual(adapter.read(RUN, "README.md", 64, principal=principal(BACKEND))["outcome"], "delivered")
        self.assertEqual(adapter.read(RUN, "README.md", 64, principal=principal(SECURITY))["reason_code"], "principal_not_allowlisted")
        self.assertEqual(adapter.read(RUN, "README.md", 64)["reason_code"], "principal_required", "a local edge without a principal is denied by a principal policy")


if __name__ == "__main__": unittest.main(verbosity=2)
