"""integration/cli.py: `adf` dispatches to the existing scripts unchanged, never blocks a tool, and verifies evidence offline."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import integration.a2a_gateway as a2a
import integration.cli as cli
from integration.local_read_adapter import LocalReadAdapter

ROOT = Path(__file__).resolve().parent.parent


def run(*argv, stdin="", env=None):
    out, err = io.StringIO(), io.StringIO()
    with patch.dict(os.environ, env or {}), patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try: code = cli.main(list(argv))
        except SystemExit as exit_:  # the scripts' own `raise SystemExit("adf: ...")` is exit 1 with that message
            code = exit_.code if isinstance(exit_.code, int) else 1; err.write(str(exit_.code))
    return code, out.getvalue(), err.getvalue()


def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


class AdfCliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()

    def test_usage_version_and_unknown_commands(self):
        self.assertEqual(run()[0], 2); self.assertEqual(run("bogus")[0], 2); self.assertEqual(run("--help")[0], 0)
        code, out, _ = run("version")
        self.assertEqual((code, out.strip()), (0, (ROOT.parent / "VERSION").read_text().strip()))
        process = subprocess.run([sys.executable, "-m", "integration.cli", "version"], capture_output=True, text=True, cwd=self.base)
        self.assertEqual((process.returncode, process.stdout.strip()), (0, out.strip()), "works from a neutral cwd")

    def test_projects_is_the_same_script(self):
        repo = self.base / "proj"; repo.mkdir(); git(repo, "init", "-q")
        env = {"ADF_HOME": str(self.base / "home")}
        self.assertEqual(run("projects", "enable", str(repo), env=env)[:2], (0, f"enabled: {repo}\n"))
        self.assertIn("[git-root]", run("projects", "list", env=env)[1])
        self.assertEqual(run("projects", "enable", "relative", env=env)[0], 1, "same canonical-path rules")
        self.assertEqual(run("projects", "reasons", env=env)[1].strip(), "no evidence yet")

    def test_hook_never_blocks_and_snippet_is_fail_safe(self):
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "/x"}})
        self.assertEqual(run("hook", stdin=payload, env={"ADF_HOME": str(self.base / "empty"), "CLAUDE_PROJECT_DIR": str(self.base)})[:2], (0, ""), "not enabled: no decision")
        with patch.object(cli, "_script", side_effect=RuntimeError("broken clone")):
            self.assertEqual(run("hook", stdin=payload)[:2], (0, ""), "a broken install is no decision, not a blocked tool")
        self.assertEqual(run("hook", "extra")[0], 2)
        for agent, matchers in (("claude", ["Read", "Bash"]), ("codex", ["^Bash$"])):
            code, out, _ = run("hook-snippet", agent)
            entries = json.loads(out)["hooks"]["PreToolUse"]
            self.assertEqual((code, [entry["matcher"] for entry in entries]), (0, matchers))
            self.assertTrue(all('|| exit 0; exec "$A" hook' in entry["hooks"][0]["command"] for entry in entries))
        self.assertEqual(run("hook-snippet", "cursor")[0], 2)

    def test_policy_build_and_a2a_mint_pass_through(self):
        target = self.base / "policy.json"
        code, out, _ = run("policy", "build", "--run-id", "s1", "--allow", "README.md", "--out", str(target))
        self.assertEqual(code, 0); self.assertIn("ADF_READ_POLICY_SHA256=", out); self.assertTrue(target.is_file())
        self.assertEqual(run("policy", "build", "--run-id", "s1", "--allow", ".env", "--out", str(self.base / "bad.json"))[0], 2)
        self.assertEqual(run("policy")[0], 2)
        code, out, _ = run("a2a", "mint", "agent-alpha", "workspace:read", env={"ADF_A2A_HS256_SECRET": "ab" * 32})
        self.assertEqual(code, 0); self.assertEqual(out.count("."), 2, "a JWT")
        self.assertEqual(run("a2a", "nope")[0], 2)

    def test_verify_bundles_and_records_offline(self):
        repo = self.base / "repo"; (repo / "config").mkdir(parents=True)
        (repo / "README.md").write_text("public"); (repo / "config/.env").write_text("SECRET")
        git(repo, "init", "-q"); git(repo, "config", "user.email", "c@example.invalid"); git(repo, "config", "user.name", "c"); git(repo, "add", "-f", "."); git(repo, "commit", "-qm", "f")
        evidence = self.base / "evidence"
        adapter = LocalReadAdapter(repo, "HEAD", evidence)
        allowed, denied = adapter.read("run-cli", "README.md", 64), adapter.read("run-cli", "config/.env", 64)
        self.assertEqual(run("verify", allowed["bundle_path"])[:2], (0, "verified  evidence_bundle  reason_code=admit_read\n"))
        self.assertEqual(run("verify", denied["bundle_path"])[1], "verified  evidence_bundle  reason_code=invalid_scope\n")
        tampered = json.loads(Path(denied["bundle_path"]).read_text()); tampered["reason_code"] = "admit_read"
        (self.base / "tampered.json").write_text(json.dumps(tampered))
        self.assertEqual(run("verify", str(self.base / "tampered.json"))[0], 1)
        principal = {"schema_version": "1.0", "sub": "agent-alpha", "scopes": ["workspace:read"], "act": [], "token_aud": "adf-a2a-local", "authn_method": "bearer_jwt_hs256", "expires_at": int(time.time()) + 300}
        bundle = json.loads(Path(denied["bundle_path"]).read_text())
        record = a2a.evidence_record(principal, "read_workspace_file", "deny", "invalid_scope", bundle["decision_id"], bundle["bundle_id"])
        a2a.persist_record(record, evidence)
        record_path = evidence / "_a2a" / f"{record['record_id']}.json"
        self.assertEqual(run("verify", str(record_path))[:2], (0, "verified  a2a_record  reason_code=invalid_scope\n"))
        orphan = a2a.evidence_record(principal, "read_workspace_file", "deny", "invalid_scope", "d" * 64, "e" * 64)
        a2a.persist_record(orphan, evidence)
        self.assertEqual(run("verify", str(evidence / "_a2a" / f"{orphan['record_id']}.json"))[0], 1, "a record whose bundle is missing never verifies")
        self.assertEqual(run("verify", str(self.base / "missing.json"))[0], 2)
        self.assertEqual(run("verify")[0], 2)


if __name__ == "__main__": unittest.main(verbosity=2)
