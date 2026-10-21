"""policy-packs/effect-security-read-v0: the built host policy denies secrets on the real gates."""
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
from integration.local_read_adapter import LocalReadAdapter

PACK_DIR = ROOT / "policy-packs/effect-security-read-v0"
_SPEC = importlib.util.spec_from_file_location("effect_security_read_v0", PACK_DIR / "build.py")
pack = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(pack)
_GATE = importlib.util.spec_from_file_location("claude_code_read_gate", ROOT / "hooks/claude-code-read-gate.py")
gate = importlib.util.module_from_spec(_GATE); _GATE.loader.exec_module(gate)
SECRET, PUBLIC = "AKIA-fake-pack-secret", "public readme"
REFUSED = [".env", ".env.local", "config/.ENV", "certs/server.pem", "tls.key", "secrets/db.txt", "a/credentials/x", ".git/config",
           ".ssh/id_ed25519", ".aws/credentials", "keys/id_rsa", "store.p12", "infra/prod.tfvars", "terraform.tfstate",
           "secrets.yaml", "home/.npmrc", "../README.md", "/etc/passwd", "", "docs//x.md"]


def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class PolicyPackTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.repo, self.evidence, self.out = base / "repo", base / "evidence", base / "host-policy.json"
        self.repo.mkdir()
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "pack@example.invalid"); git(self.repo, "config", "user.name", "pack")
        (self.repo / "config").mkdir(); (self.repo / "secrets").mkdir()
        for name in (".env", "config/.env", "secrets/db.txt"): (self.repo / name).write_text(SECRET)
        (self.repo / "README.md").write_text(PUBLIC)
        git(self.repo, "add", "-f", "."); git(self.repo, "commit", "-qm", "fixture")

    def built(self, run_id="session-1", paths=("README.md",)):
        target, pin = pack.write(pack.build(run_id, list(paths), 64), self.out)
        return LocalReadAdapter(self.repo, "HEAD", self.evidence, host_policy_path=target, host_policy_sha256=pin), target, pin

    def test_pack_denylist_never_weakens_the_runtime_policy(self):
        runtime = json.loads((ROOT / "runtime/v1/policies/sensitive-path-policy-v1.json").read_text())
        deny = pack.denylist()
        for key in pack._KEYS: self.assertTrue({item.lower() for item in runtime[key]} <= set(deny[key]), key)

    def test_secret_and_malformed_paths_are_refused_and_no_pin_is_printed(self):
        for path in REFUSED:
            with self.subTest(path=path), self.assertRaises(ValueError): pack.build("session-1", ["README.md", path])
        for argv in (["--allow", ".env"], [], ["--allow", "README.md", "--max-output-bytes", "0"]):
            with self.subTest(argv=argv):
                self.assertEqual(pack.main(["--run-id", "s", "--out", str(self.out), *argv]), 2)
                self.assertFalse(self.out.exists())

    def test_built_policy_delivers_allowlisted_and_denies_everything_else(self):
        adapter, _, _ = self.built()
        delivered = adapter.read("session-1", "README.md", 64)
        self.assertEqual((delivered["outcome"], delivered["content"]), ("delivered", PUBLIC))
        # Layered: v1 path contract (root dotfile) -> PDP scope rules (.env/.git) -> pinned allowlist.
        for run_id, path, reason in (("session-1", ".env", "invalid_referenced_contract"), ("session-1", "config/.env", "invalid_scope"), ("session-1", "secrets/db.txt", "scope_not_allowlisted"), ("other-session", "README.md", "run_binding_mismatch"), ("session-1", "README.md", "budget_exceeds_ceiling")):
            result = adapter.read(run_id, path, 65 if reason == "budget_exceeds_ceiling" else 64)
            self.assertEqual((result["outcome"], result["reason_code"]), ("deny", reason)); self.assertNotIn(SECRET, json.dumps(result))

    def test_runtime_still_denies_a_secret_that_bypassed_the_builder(self):
        with patch.object(pack, "refused", return_value=None):
            adapter, _, _ = self.built(paths=("README.md", "secrets/db.txt"))
        result = adapter.read("session-1", "secrets/db.txt", 64)
        self.assertEqual((result["outcome"], result["reason_code"]), ("deny", "sensitive_path_denied")); self.assertNotIn(SECRET, json.dumps(result))

    def test_claude_read_gate_enforces_the_pinned_pack(self):
        _, target, pin = self.built()
        env = {"ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_EVIDENCE_DIR": str(self.evidence), "ADF_MAX_OUTPUT_BYTES": "64", "ADF_READ_POLICY_FILE": str(target), "ADF_READ_POLICY_SHA256": pin}
        payload = lambda path: {"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": "session-1", "tool_input": {"file_path": str(self.repo / path)}}
        with patch.dict(os.environ, env, clear=True):
            allowed = gate.gate(payload("README.md"))
            denied = {path: gate.gate(payload(path))["hookSpecificOutput"] for path in (".env", "config/.env", "secrets/db.txt")}
        self.assertTrue(allowed == {} or allowed["hookSpecificOutput"]["permissionDecision"] == "allow")
        for path, reason in ((".env", "invalid_referenced_contract"), ("config/.env", "invalid_scope"), ("secrets/db.txt", "scope_not_allowlisted")):
            self.assertEqual(denied[path]["permissionDecision"], "deny"); self.assertIn(reason, denied[path]["permissionDecisionReason"])


if __name__ == "__main__": unittest.main(verbosity=2)
