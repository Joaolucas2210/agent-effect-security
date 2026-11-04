"""ADR 0036: a single leading dot per path component is a valid read intent; the token files that the old grammar
hid by accident are named in sensitive_path_policy_v2; every deny carries a bundle; nothing valid before is invalid now.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks/adf-read-hook.py"
sys.path.insert(0, str(ROOT))
from integration.local_read_adapter import LocalReadAdapter, schemas  # noqa: E402
from integration.local_evidence_bundle import verify_offline  # noqa: E402
from runtime.local_read_runtime import sensitive_path  # noqa: E402
from tools import pdp  # noqa: E402

V2 = ROOT / "runtime/v1/policies/sensitive-path-policy-v2.json"
TOKEN_FILES = (".npmrc", ".pypirc", ".netrc", ".git-credentials", ".docker/config.json", ".kube/config", ".aws/credentials", ".ssh/id_rsa",
               ".gnupg/pubring.kbx", ".terraform.d/credentials.tfrc.json", ".vault-token", ".pgpass", ".my.cnf", ".boto", ".s3cfg", ".config/gh/hosts.yml")
BENIGN = (".gitignore", ".gitleaks.toml", ".editorconfig", ".dockerignore", ".github/workflows/ci.yml", ".claude/settings.json", "docs/.gitkeep", "src/.keep")


def git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


class RootDotfilesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); base = Path(cls.temp.name).resolve()
        cls.repo = base / "repo"; cls.repo.mkdir()
        for rel in BENIGN + TOKEN_FILES + (".env", ".env.example", "config/.env.local", "README.md"):
            path = cls.repo / rel; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("x\n")
        git(cls.repo, "init", "-q"); git(cls.repo, "config", "user.email", "m@example.invalid"); git(cls.repo, "config", "user.name", "m"); git(cls.repo, "add", "-f", "."); git(cls.repo, "commit", "-qm", "f")
        cls.base, cls.schemas = base, schemas()

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def read(self, rel, run="run-dot"):
        return LocalReadAdapter(self.repo, "HEAD", self.base / "evidence", self.base).read(run, rel, 4096)

    def bundle(self, result):
        self.assertIsNotNone(result["bundle_path"], f"{result['reason_code']}: a deny after the contract carries a bundle")
        bundle = json.loads(Path(result["bundle_path"]).read_text()); self.assertTrue(verify_offline(bundle, self.schemas)); return bundle

    def test_v2_policy_is_a_superset_of_v1_and_names_the_token_files(self):
        v1 = json.loads((ROOT / "runtime/v1/policies/sensitive-path-policy-v1.json").read_text()); v2 = json.loads(V2.read_text())
        self.assertEqual((v2["policy_version"], v2["provenance"]["adr"]), ("2.0", "0036"))
        for key in ("deny_components", "deny_component_prefixes", "deny_component_suffixes"):
            self.assertTrue(set(v1[key]) <= set(v2[key]), key)
        for rel in TOKEN_FILES:
            self.assertTrue(sensitive_path(rel, v2), rel)
        for rel in BENIGN:
            self.assertFalse(sensitive_path(rel, v2), rel)
        oracle = json.loads((ROOT / "runtime/v1/tests/normative-oracles.json").read_text())["contracts"]["SensitivePathPolicyV2"]
        self.assertTrue(set(oracle["required_components"]) <= set(v2["deny_components"]))

    def test_benign_root_dotfiles_are_delivered_with_a_bundle(self):
        for rel in BENIGN:
            with self.subTest(rel):
                result = self.read(rel); self.assertEqual(result["outcome"], "delivered", result["reason_code"]); self.assertEqual(self.bundle(result)["decision_outcome"], "admit_read")

    def test_secret_dotfiles_are_denied_with_a_bundle(self):
        self.assertEqual(self.read(".env")["reason_code"], "invalid_scope"); self.bundle(self.read(".env"))
        self.assertEqual(self.read(".git/HEAD")["reason_code"], "invalid_scope")
        for rel in (".env.example", "config/.env.local") + TOKEN_FILES:
            with self.subTest(rel):
                result = self.read(rel); self.assertEqual((result["outcome"], result["reason_code"]), ("deny", "sensitive_path_denied")); self.assertNotIn("content", result)
                self.assertEqual(self.bundle(result)["receipt"]["reason_code"], "sensitive_path_denied")

    def test_malformed_paths_stay_rejected(self):
        for rel in ("..", ".", "./x", "x/.", "x/..", "docs//readme.md", ".hidden/../README.md", "..env", "/.env", ".env\x00", "-.env", ". env"):
            with self.subTest(repr(rel)):
                result = self.read(rel); self.assertEqual(result["outcome"], "deny"); self.assertIn(result["reason_code"], ("invalid_referenced_contract", "invalid_scope", "invalid_arguments")); self.assertNotIn("content", result)
        for rel in ("..", ".", "a/./b", "..a", "a/..b"):
            self.assertFalse(pdp._PATH.fullmatch(rel), rel)

    def test_every_path_valid_under_v1_is_valid_under_1_1(self):
        old = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
        schema = json.loads((ROOT / "tools/v1/schemas/list-files-input.schema.json").read_text())["properties"]["path"]["pattern"]
        for rel in ("README.md", "docs/readme.md", "a/b/c.d-e_f", "x", "9/8", "a.b.c", "a-b/c_d/e.f", "deep/" * 10 + "leaf"):
            self.assertTrue(old.fullmatch(rel) and pdp._PATH.fullmatch(rel) and re.search(schema, rel), rel)
        for rel in BENIGN:
            self.assertTrue(pdp._PATH.fullmatch(rel) and re.search(schema, rel), rel)

    def test_deny_gate_and_cat_gate_use_v2(self):
        home = self.base / "adf-home"; home.mkdir(exist_ok=True); (home / "enabled-projects").write_text(f"{self.repo}\n")
        env = {"PATH": os.environ["PATH"], "HOME": str(self.base), "ADF_HOME": str(home), "CLAUDE_PROJECT_DIR": str(self.repo)}
        def hook(tool, tool_input, **extra):
            payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "sess-dot", "tool_input": tool_input, **extra}
            proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, cwd=str(self.repo), timeout=120)
            self.assertEqual((proc.returncode, proc.stderr), (0, "")); return proc.stdout
        self.assertIn("uncovered_read_denied_sensitive", hook("Grep", {"pattern": "x", "path": str(self.repo / ".npmrc")}))
        self.assertIn("uncovered_write_denied_sensitive", hook("Edit", {"file_path": str(self.repo / ".netrc"), "old_string": "a", "new_string": "b"}))
        self.assertIn("uncovered_read_denied_sensitive", hook("Bash", {"command": "head .git-credentials"}))
        self.assertIn("deny/sensitive_path_denied", hook("Bash", {"command": "cat .kube/config"}, cwd=str(self.repo)), "the cat gate goes through the adapter: bundle, not contract")
        self.assertIn("read_delivered", hook("Read", {"file_path": str(self.repo / ".gitignore")}))
        self.assertIn("deny/invalid_scope", hook("Read", {"file_path": str(self.repo / ".env")}), "root .env now denied by the PDP with a bundle")


if __name__ == "__main__": unittest.main(verbosity=2)
