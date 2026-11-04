"""ADR 0030: host-held HMAC key signs bundles, A2A records and attempt journals; verification is offline.

Negative cases first: wrong key, flipped byte, tampered or missing sidecar, unusable key file, and the
fail-closed rule that a configured key which cannot sign delivers no byte.
"""
import importlib.util
import json
import os
import secrets
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from integration import evidence_signing as signing  # noqa: E402
from integration.local_read_adapter import LocalReadAdapter  # noqa: E402
from integration import a2a_gateway as a2a  # noqa: E402

_CLI = importlib.util.spec_from_file_location("adf_cli", ROOT / "integration/cli.py")
cli = importlib.util.module_from_spec(_CLI); _CLI.loader.exec_module(cli)


def git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


class EvidenceSigningTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.key = self.base / "evidence.key"
        signing.init_key(self.key)
        self.target = self.base / "bundle.json"; self.target.write_text('{"bundle_id":"x"}')

    def key_env(self, path=None): return patch.dict(os.environ, {"ADF_EVIDENCE_KEY_FILE": str(path or self.key)})

    def test_key_init_is_owner_read_only_and_never_overwrites(self):
        self.assertEqual(oct(self.key.stat().st_mode & 0o777), oct(0o400))
        self.assertEqual(self.key.stat().st_size, 32)
        with self.assertRaises(FileExistsError): signing.init_key(self.key)
        self.assertEqual(signing.load_key(self.key), self.key.read_bytes())

    def test_unusable_key_files_are_refused(self):
        for name, prepare in (("missing", lambda p: None), ("short", lambda p: p.write_bytes(b"x" * 16)), ("group-readable", lambda p: (p.write_bytes(secrets.token_bytes(32)), p.chmod(0o640))), ("directory", lambda p: p.mkdir())):
            path = self.base / f"key-{name}"; prepare(path)
            with self.subTest(name): self.assertRaises(signing.SigningUnavailable, signing.load_key, path)
        self.assertRaises(signing.SigningUnavailable, signing.load_key, Path("relative.key"))

    def test_sign_and_verify_roundtrip_and_every_tamper_is_invalid(self):
        key = signing.load_key(self.key)
        sidecar = signing.sign_file(self.target, key)
        self.assertEqual(sidecar, self.target.with_name("bundle.json.sig"))
        self.assertEqual(oct(sidecar.stat().st_mode & 0o777), oct(0o600))
        self.assertEqual(signing.verify_file(self.target, key), "valid")
        self.assertEqual(signing.verify_file(self.target, None), "not_checked")
        self.assertEqual(signing.verify_file(self.target, secrets.token_bytes(32)), "invalid", "wrong key")
        meta = json.loads(sidecar.read_text()); self.assertEqual(set(meta), {"sig_version", "alg", "key_id", "target_sha256", "value"})
        self.assertRaises(FileExistsError, signing.sign_file, self.target, key)
        sidecar.write_text(json.dumps({**meta, "value": "0" * 64})); self.assertEqual(signing.verify_file(self.target, key), "invalid", "tampered sidecar")
        sidecar.write_text(json.dumps(meta)); self.target.write_text('{"bundle_id":"y"}'); self.assertEqual(signing.verify_file(self.target, key), "invalid", "flipped byte")
        sidecar.unlink(); self.assertEqual(signing.verify_file(self.target, key), "unsigned")

    def _adapter(self):
        repo = self.base / "repo"; repo.mkdir(); (repo / "README.md").write_text("public")
        git(repo, "init", "-q"); git(repo, "config", "user.email", "m@example.invalid"); git(repo, "config", "user.name", "m"); git(repo, "add", "."); git(repo, "commit", "-qm", "f")
        return LocalReadAdapter(repo, "HEAD", self.base / "evidence", self.base)

    def test_adapter_signs_bundle_and_journal_when_configured(self):
        adapter = self._adapter()
        with self.key_env():
            result = adapter.read("run-sign", "README.md", 4096)
        self.assertEqual(result["outcome"], "delivered")
        bundle = Path(result["bundle_path"]); key = signing.load_key(self.key)
        self.assertEqual(signing.verify_file(bundle, key), "valid")
        journals = list((self.base / "evidence/_attempts").glob("*.jsonl"))
        self.assertEqual(len(journals), 1); self.assertEqual(signing.verify_file(journals[0], key), "valid")
        unsigned = adapter.read("run-plain", "README.md", 4096)
        self.assertEqual(unsigned["outcome"], "delivered"); self.assertEqual(signing.verify_file(Path(unsigned["bundle_path"]), key), "unsigned", "no key configured: unchanged behaviour")

    def test_configured_key_that_cannot_sign_delivers_nothing(self):
        adapter = self._adapter()
        with self.key_env(self.base / "nope.key"):
            result = adapter.read("run-nokey", "README.md", 4096)
        self.assertEqual(result["outcome"], "deny"); self.assertNotIn("content", result)
        self.assertIn(result["reason_code"], ("evidence_signing_unavailable", "attempt_evidence_failed"))
        self.assertEqual(list((self.base / "evidence").rglob("*.sig")), [])

    def test_a2a_record_is_signed_or_not_persisted(self):
        principal = {"sub": "agent-alpha", "scopes": ["workspace:read"], "act": [], "token_aud": "adf", "authn_method": "hs256", "expires_at": 4102444800}
        record = a2a.evidence_record(principal, "read_workspace_file", "deny", "invalid_scope")
        with self.key_env():
            a2a.persist_record(record, self.base / "evidence")
        path = self.base / "evidence/_a2a" / f"{record['record_id']}.json"
        self.assertEqual(signing.verify_file(path, signing.load_key(self.key)), "valid")
        other = a2a.evidence_record(principal, "read_workspace_file", "deny", "invalid_scope")
        with self.key_env(self.base / "nope.key"):
            self.assertRaises(signing.SigningUnavailable, a2a.persist_record, other, self.base / "evidence")
        self.assertFalse((self.base / "evidence/_a2a" / f"{other['record_id']}.json").exists(), "a record that cannot be signed is not left behind")

    def test_cli_verify_reports_authenticity_and_key_init(self):
        adapter = self._adapter()
        with self.key_env():
            path = adapter.read("run-cli", "README.md", 4096)["bundle_path"]
        def run(*argv):
            proc = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from integration.cli import main; raise SystemExit(main(sys.argv[2:]))", str(ROOT), *argv], capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(ROOT)})
            return proc.returncode, proc.stdout + proc.stderr
        self.assertEqual(run("verify", path)[0], 0); self.assertIn("authenticity=not_checked", run("verify", path)[1])
        code, out = run("verify", path, "--key", str(self.key)); self.assertEqual(code, 0); self.assertIn("authenticity=valid", out)
        wrong = self.base / "wrong.key"; signing.init_key(wrong)
        code, out = run("verify", path, "--key", str(wrong)); self.assertEqual(code, 1); self.assertIn("authenticity=invalid", out)
        new = self.base / "new.key"
        self.assertEqual(run("key", "init", str(new))[0], 0); self.assertEqual(oct(new.stat().st_mode & 0o777), oct(0o400))
        self.assertNotEqual(run("key", "init", str(new))[0], 0, "never overwrite a key")


if __name__ == "__main__": unittest.main(verbosity=2)
