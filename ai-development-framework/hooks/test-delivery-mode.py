"""ADR 0029: a bundle says whether ADF delivered the bytes (`mediated`) or only decided (`gate_only`).

Schema 1.1 is additive: 1.0 bundles stay valid and verify unchanged; a 1.1 bundle without the field, a 1.0
bundle with it, or an unknown mode is invalid. Hooks are gate_only; the MCP stdio server and A2A are mediated.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from integration import a2a_gateway as a2a  # noqa: E402
from integration import mcp_read_server  # noqa: E402
from integration import read_gate_host  # noqa: E402
from integration.local_evidence_bundle import _bundle_payload, digest, verify_offline  # noqa: E402
from integration.local_read_adapter import LocalReadAdapter, schemas  # noqa: E402

HOOK = ROOT / "hooks/adf-read-hook.py"


def git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


def reseal(bundle):
    bundle["bundle_id"] = digest(_bundle_payload(bundle)); bundle["verification"]["bundle_sha256"] = digest(_bundle_payload(bundle, include_id=True))
    return bundle


class DeliveryModeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(); self.repo = self.base / "repo"; self.repo.mkdir()
        (self.repo / "README.md").write_text("public")
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "m@example.invalid"); git(self.repo, "config", "user.name", "m"); git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "f")
        self.schemas = schemas()

    def adapter(self): return LocalReadAdapter(self.repo, "HEAD", self.base / "evidence", self.base)

    def bundle(self, **kwargs):
        result = self.adapter().read("run-dm", "README.md", 4096, **kwargs)
        self.assertEqual(result["outcome"], "delivered", result)
        return json.loads(Path(result["bundle_path"]).read_text())

    def test_default_stays_schema_1_0_without_the_field(self):
        bundle = self.bundle()
        self.assertEqual(bundle["schema_version"], "1.0"); self.assertNotIn("delivery_mode", bundle); self.assertTrue(verify_offline(bundle, self.schemas))

    def test_explicit_mode_yields_1_1_and_every_inconsistency_is_invalid(self):
        for mode in ("gate_only", "mediated"):
            bundle = self.bundle(delivery_mode=mode)
            self.assertEqual((bundle["schema_version"], bundle["delivery_mode"]), ("1.1", mode)); self.assertTrue(verify_offline(bundle, self.schemas))
        without = reseal({k: v for k, v in copy.deepcopy(bundle).items() if k != "delivery_mode"}); self.assertFalse(verify_offline(without, self.schemas), "1.1 requires the field")
        downgraded = reseal({**copy.deepcopy(bundle), "schema_version": "1.0"}); self.assertFalse(verify_offline(downgraded, self.schemas), "1.0 never carries the field")
        unknown = reseal({**copy.deepcopy(bundle), "delivery_mode": "native"}); self.assertFalse(verify_offline(unknown, self.schemas))
        flipped = {**copy.deepcopy(bundle), "delivery_mode": "gate_only" if bundle["delivery_mode"] == "mediated" else "mediated"}; self.assertFalse(verify_offline(flipped, self.schemas), "the field is under the digest")
        self.assertRaises(ValueError, self.adapter().read, "run-bad", "README.md", 4096, delivery_mode="native")

    def test_deny_bundles_carry_the_mode_too(self):
        result = self.adapter().read("run-deny", "config/.env", 4096, delivery_mode="gate_only")
        self.assertEqual(result["outcome"], "deny")
        bundle = json.loads(Path(result["bundle_path"]).read_text()); self.assertEqual(bundle["delivery_mode"], "gate_only"); self.assertTrue(verify_offline(bundle, self.schemas))

    def test_claude_hook_is_gate_only(self):
        home = self.base / "adf-home"; home.mkdir(); (home / "enabled-projects").write_text(f"{self.repo}\n")
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": "sess-dm", "tool_input": {"file_path": str(self.repo / "README.md")}}
        env = {"PATH": os.environ["PATH"], "HOME": str(self.base), "ADF_HOME": str(home), "CLAUDE_PROJECT_DIR": str(self.repo)}
        proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=120)
        self.assertIn('"allow"', proc.stdout, proc.stderr)
        bundles = [p for p in (home / "evidence").rglob("*.json") if "_attempts" not in p.parts]
        self.assertEqual(len(bundles), 1); self.assertEqual(json.loads(bundles[0].read_text())["delivery_mode"], "gate_only")

    def test_mediated_edges_declare_it(self):
        seen = []
        def fake_read(self_, run_id, path, budget, **kwargs): seen.append(kwargs.get("delivery_mode")); return {"outcome": "deny", "reason_code": "invalid_scope", "bundle_id": None, "bundle_path": None, "taint": {}, "decision_latency_ms": 0, "adapter_id": "x"}
        with patch.object(LocalReadAdapter, "read", fake_read):
            read_gate_host.read_adapter(LocalReadAdapter(self.repo, "HEAD", self.base / "e", self.base), "r", "README.md", 10, self.base / "e", delivery_mode="mediated")
            with patch.dict(os.environ, {"ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_TRUSTED_REVISION": "HEAD", "ADF_EVIDENCE_DIR": str(self.base / "e"), "ADF_MAX_OUTPUT_BYTES": "10", "ADF_RUN_ID": "r1", "ADF_READ_POLICY_FILE": "/x", "ADF_READ_POLICY_SHA256": "0" * 64}):
                try: mcp_read_server.read_snapshot("README.md")
                except Exception: pass
        self.assertEqual(seen[:1], ["mediated"], "read_adapter forwards the mode")
        self.assertIn("mediated", seen[1:], "the MCP stdio tool declares mediated delivery")
        source = (ROOT / "integration/a2a_gateway.py").read_text()
        self.assertIn('delivery_mode="mediated"', source, "the A2A edge returns bytes, so it must declare mediated")

    def test_cli_verify_and_project_reasons_show_the_mode(self):
        bundle_path = self.adapter().read("run-cli", "README.md", 4096, delivery_mode="mediated")["bundle_path"]
        proc = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from integration.cli import main; raise SystemExit(main(sys.argv[2:]))", str(ROOT), "verify", bundle_path], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr); self.assertIn("delivery_mode=mediated", proc.stdout)


if __name__ == "__main__": unittest.main(verbosity=2)
