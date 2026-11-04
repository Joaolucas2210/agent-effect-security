"""ADR 0031 follow-up: `adf mcp probe --write` records when each server was last probed; `adf doctor` reports the
age and fails on `never` or `stale` (default 30 days, `ADF_MCP_PROBE_MAX_AGE_DAYS`). Skipped is never green.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from integration import mcp_registry  # noqa: E402


def stamp(days_ago): return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class McpProbeAgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve(); self.user_home = base / "home"; self.home = self.user_home / ".adf"; self.home.mkdir(parents=True)
        self.definition = {"command": "npx", "args": ["x"], "env_keys": []}
        self.registry_file = self.home / "mcp-registry.json"

    def registry(self, **servers):
        return {"schema_version": "1.0", "servers": servers}

    def test_registry_accepts_probed_at_only_as_utc_timestamp(self):
        mcp_registry.validate(self.registry(a={"tools": ["x"], "definition": self.definition, "tools_sha256": "0" * 64, "probed_at": stamp(1)}))
        for bad in ("yesterday", "2026-11-04", "2026-11-04T10:00:00+02:00", 5):
            with self.subTest(bad): self.assertRaises(mcp_registry.RegistryInvalid, mcp_registry.validate, self.registry(a={"tools": ["x"], "definition": self.definition, "probed_at": bad}))
        with self.assertRaises(mcp_registry.RegistryInvalid):  # probed_at without a definition makes no sense
            mcp_registry.validate(self.registry(a={"tools": ["x"], "probed_at": stamp(1)}))

    def test_probe_status_never_fresh_stale(self):
        reg = self.registry(never={"tools": ["x"], "definition": self.definition}, fresh={"tools": ["x"], "definition": self.definition, "tools_sha256": "0" * 64, "probed_at": stamp(3)},
                            stale={"tools": ["x"], "definition": self.definition, "tools_sha256": "0" * 64, "probed_at": stamp(45)}, plain={"tools": ["x"]})
        status = mcp_registry.probe_status(reg, max_age_days=30)
        self.assertEqual(status["never"], {"status": "never"})
        self.assertEqual((status["fresh"]["status"], status["fresh"]["age_days"]), ("fresh", 3))
        self.assertEqual((status["stale"]["status"], status["stale"]["age_days"]), ("stale", 45))
        self.assertNotIn("plain", status, "no definition: nothing to probe")
        self.assertEqual(mcp_registry.probe_status(reg, max_age_days=60)["stale"]["status"], "fresh", "the threshold is the host's")
        future = self.registry(a={"tools": ["x"], "definition": self.definition, "tools_sha256": "0" * 64, "probed_at": (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")})
        self.assertEqual(mcp_registry.probe_status(future, max_age_days=30)["a"]["status"], "stale", "a clock ahead of now is not evidence of a recent probe")

    def test_record_probe_sets_timestamp_only_for_probed_servers(self):
        reg = self.registry(a={"tools": ["x"], "definition": self.definition}, b={"tools": ["y"], "definition": self.definition}, c={"tools": ["z"]})
        report = {"a": {"status": "unpinned", "tools_sha256": "1" * 64}, "b": {"status": "unreachable"}, "c": {"status": "no_definition"}}
        out = mcp_registry.record_probe(reg, report, now="2026-11-04T12:00:00Z")
        self.assertEqual((out["servers"]["a"]["tools_sha256"], out["servers"]["a"]["probed_at"]), ("1" * 64, "2026-11-04T12:00:00Z"))
        self.assertNotIn("probed_at", out["servers"]["b"], "unreachable is not a probe"); self.assertNotIn("probed_at", out["servers"]["c"])
        mcp_registry.validate(out)

    def test_cli_probe_write_records_the_time_and_doctor_reports_age(self):
        server = {"command": str(Path(sys.executable).parent / "mcp"), "args": ["run", str(ROOT / "integration/mcp_read_server.py") + ":mcp", "--transport", "stdio"], "env_keys": []}
        self.registry_file.write_text(json.dumps(self.registry(adf={"tools": ["read_snapshot"], "definition": server})))
        def run(*argv, **env):
            proc = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from integration.cli import main; raise SystemExit(main(sys.argv[2:]))", str(ROOT), *argv], capture_output=True, text=True, cwd=str(ROOT.parent), env={**os.environ, "HOME": str(self.user_home), "ADF_HOME": str(self.home), "ADF_TRUSTED_REPOSITORY": str(ROOT.parent), **env})
            return proc.returncode, proc.stdout + proc.stderr
        def pinned():
            return {"ADF_MCP_REGISTRY_FILE": str(self.registry_file), "ADF_MCP_REGISTRY_SHA256": mcp_registry.pin(json.loads(self.registry_file.read_text()))}
        self.assertEqual(run("doctor", "--pin")[0], 0)
        code, out = run("doctor", **pinned()); self.assertEqual(code, 1, out); self.assertIn("probe=never", out)
        self.assertEqual(run("mcp", "probe", str(self.registry_file), "--write")[0], 0)
        self.assertRegex(json.loads(self.registry_file.read_text())["servers"]["adf"]["probed_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertIn("control_plane_tampered", run("doctor", **pinned())[1], "the registry file is pinned by ADR 0027: --write changes it, the human re-pins")
        self.assertEqual(run("doctor", "--pin", **pinned())[0], 0)
        code, out = run("doctor", **pinned()); self.assertEqual(code, 0, out); self.assertIn("probe=fresh(0d)", out)
        aged = json.loads(self.registry_file.read_text()); aged["servers"]["adf"]["probed_at"] = stamp(45); self.registry_file.write_text(json.dumps(aged))
        self.assertEqual(run("doctor", "--pin", **pinned())[0], 0)
        code, out = run("doctor", **pinned()); self.assertEqual(code, 1, out); self.assertIn("probe=stale(45d)", out)
        code, out = run("doctor", **pinned(), ADF_MCP_PROBE_MAX_AGE_DAYS="60"); self.assertEqual(code, 0, out); self.assertIn("probe=fresh(45d)", out)
        code, out = run("doctor", **pinned(), ADF_MCP_PROBE_MAX_AGE_DAYS="many"); self.assertEqual(code, 1, out); self.assertIn("ADF_MCP_PROBE_MAX_AGE_DAYS", out, "a bad threshold is a finding, not a default")


if __name__ == "__main__": unittest.main(verbosity=2)
