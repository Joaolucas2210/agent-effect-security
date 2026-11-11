"""Phase 2C (ARCH-09/R-16, ADR 0040 Proposed): pin TODAY's behaviour for the four open config issues.

These tests do not endorse the behaviour; they make any change to it a visible, reviewed diff. Each fix is a
proposal in ADR 0040 "Phase 2C notes". When a fix lands, the matching assertion flips in the same PR.
Synthetic env, scratch HOME/ADF_HOME, no real ~/.adf or ~/.claude, no evidence written outside a temp dir.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from integration import control_plane_pins, mcp_registry, read_gate_host  # noqa: E402
from integration.cli import read_policy_status  # noqa: E402
from integration.host_config import from_env  # noqa: E402
from integration.local_read_adapter import LocalReadAdapter  # noqa: E402

PIN = "a" * 64


def under(env):
    return mock.patch.dict(os.environ, env, clear=True)


def load(relative):
    spec = importlib.util.spec_from_file_location(relative.replace("/", "_").replace("-", "_").removesuffix(".py"), ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reason(decision):
    return decision["hookSpecificOutput"]["permissionDecisionReason"].removeprefix("adf: ") if decision else None


class OpenIssuesPinned(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()

    def test_oi1_trusted_repository_has_four_fallbacks(self):
        """OI-1: unset ADF_TRUSTED_REPOSITORY -> clone (read_gate_host), '/' (deny-gate bash_read),
        deny host_configuration_invalid (deny-gate write path), cwd (adf doctor's MCP check)."""
        with under({}):
            self.assertEqual(read_gate_host.host_settings()[0], read_gate_host.DEFAULT_REPOSITORY.resolve())  # 1. the ADF clone
        with under({"CLAUDE_PROJECT_DIR": str(self.base)}):
            self.assertIsNone(read_gate_host.host_settings())  # ...unless the client project is another dir
        deny_gate = load("hooks/adf-deny-gate.py")
        for command in ("cat README.md", "cat etc/x/.env", "cat /etc/x/.env", "cat a b"):
            with self.subTest(command=command):
                with under({}):
                    unset = reason(deny_gate.bash_read({"tool_input": {"command": command}}))
                with under({"ADF_TRUSTED_REPOSITORY": "/"}):
                    slash = reason(deny_gate.bash_read({"tool_input": {"command": command}}))
                self.assertEqual(unset, slash)  # 2. bash_read treats unset exactly as root "/"
        for env in ({}, {"ADF_TRUSTED_REPOSITORY": ""}, {"ADF_TRUSTED_REPOSITORY": "rel"}):
            with self.subTest(env=env), under(env):
                self.assertEqual(reason(deny_gate._decide({"tool_name": "Write", "tool_input": {"file_path": "x"}})), "host_configuration_invalid")  # 3. deny
        cli = (ROOT / "integration/cli.py").read_text(encoding="utf-8")
        self.assertIn('_doctor_mcp(os.environ.get("ADF_TRUSTED_REPOSITORY") or os.getcwd()', cli)  # 4. cwd (doctor is not run here: it reads ~/.adf)
        self.assertIn('os.environ.get("ADF_TRUSTED_REPOSITORY") or "/"', (ROOT / "integration/deny_gate.py").read_text(encoding="utf-8"))

    def test_oi2_inherited_evidence_dir_from_another_project_wins(self):
        """OI-2: adf-read-hook `setdefault`s ADF_EVIDENCE_DIR, so an export left over from project B sends project
        A's evidence to B's directory; an inherited empty ADF_TRUSTED_REVISION also survives (and later denies)."""
        repo, home = self.base / "project-a", self.base / "adf-home"
        repo.mkdir(); home.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (home / "enabled-projects").write_text(f"{repo}\n", encoding="utf-8")
        hook = load("hooks/adf-read-hook.py")
        seen = {}
        payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": str(repo / "README.md")}})
        foreign = str(self.base / "adf-home/evidence/project-b-00000000/2026-01-01")
        for inherited, expect_foreign in (({}, False), ({"ADF_EVIDENCE_DIR": foreign, "ADF_TRUSTED_REVISION": ""}, True)):
            with self.subTest(inherited=inherited), under({"ADF_HOME": str(home), "CLAUDE_PROJECT_DIR": str(repo), **inherited}), \
                    mock.patch.object(hook, "_tampered", return_value=[]), mock.patch.object(hook, "_gate", side_effect=lambda payload: seen.update(os.environ) or {}):
                hook.decide(payload)
                own = str(home / "evidence" / hook.project_id(str(repo)))
                if expect_foreign:
                    self.assertEqual((seen["ADF_EVIDENCE_DIR"], seen["ADF_TRUSTED_REVISION"]), (foreign, ""))
                    self.assertIsNone(read_gate_host.host_settings())  # empty revision -> host_settings None -> the edge denies
                else:
                    self.assertTrue(seen["ADF_EVIDENCE_DIR"].startswith(own + "/"))
                    self.assertEqual(seen["ADF_TRUSTED_REVISION"], "HEAD")
                self.assertEqual(seen["ADF_TRUSTED_REPOSITORY"], os.path.realpath(repo))  # the root alone is overridden

    def test_oi3_shell_vs_registered_precedence_diverges(self):
        """OI-3: an EMPTY shell value falls through to the registered hook command in control_plane_pins.host_env
        (`or`), but wins in adf doctor's policy line (`in`)."""
        home = self.base / "home"
        (home / ".claude").mkdir(parents=True)
        command = f"export ADF_READ_POLICY_FILE=/reg/policy.json; export ADF_READ_POLICY_SHA256={PIN}; adf hook"
        (home / ".claude/settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"command": command}]}]}}), encoding="utf-8")
        registered = control_plane_pins.registered_env(str(home))
        with under({"ADF_READ_POLICY_FILE": "", "ADF_READ_POLICY_SHA256": ""}):
            self.assertEqual(control_plane_pins.host_env("ADF_READ_POLICY_FILE", str(home)), "/reg/policy.json")  # pins: registered fills ""
            doctor_lookup = lambda name: os.environ[name] if name in os.environ else registered.get(name)  # noqa: E731 (cli.py, verbatim)
            self.assertEqual(read_policy_status(doctor_lookup), ("invalid", "file path is not absolute"))  # doctor: "" wins
        with under({}):
            self.assertEqual(control_plane_pins.host_env("ADF_READ_POLICY_FILE", str(home)), "/reg/policy.json")  # unset: both agree
        self.assertIn("os.environ[name] if name in os.environ else registered.get(name)", (ROOT / "integration/cli.py").read_text(encoding="utf-8"))
        self.assertIn("return os.environ.get(name) or registered_env(home).get(name)", (ROOT / "integration/control_plane_pins.py").read_text(encoding="utf-8"))

    def test_oi4_empty_string_is_absent_for_some_readers_and_invalid_for_others(self):
        """OI-4: "" = absent for MCP registry, evidence key, ADF_HOME, OTel flush; "" = configured+invalid for the
        read policy pair, JWKS and ADF_TRUSTED_REVISION."""
        with under({"ADF_MCP_REGISTRY_FILE": "", "ADF_MCP_REGISTRY_SHA256": ""}):
            self.assertIsNone(mcp_registry.configured())  # absent
        absent = from_env({"ADF_EVIDENCE_KEY_FILE": "", "ADF_HOME": "", "ADF_OTEL_FLUSH_MS": ""})
        self.assertEqual((absent.evidence.evidence_key_file, absent.run.adf_home, absent.otel.flush_seconds), (None, None, 0.3))
        self.assertEqual(read_policy_status(lambda name: ""), ("invalid", "file path is not absolute"))  # invalid
        (self.base / "ev").mkdir()
        adapter = LocalReadAdapter(str(self.base), "HEAD", str(self.base / "ev"), host_policy_path="", host_policy_sha256="")
        self.assertTrue(adapter._host_policy_invalid)  # the adapter denies every read with host_policy_invalid
        self.assertFalse(LocalReadAdapter(str(self.base), "HEAD", str(self.base / "ev"))._host_policy_invalid)  # both None = demo
        self.assertEqual(from_env({"ADF_A2A_JWKS_FILE": ""}).a2a.auth_mode, "rs256")  # "" selects RS256 and then fails closed
        repo = self.base / "repo"; repo.mkdir()
        with under({"ADF_TRUSTED_REPOSITORY": str(repo), "ADF_EVIDENCE_DIR": str(self.base / "ev"), "ADF_TRUSTED_REVISION": ""}):
            self.assertIsNone(read_gate_host.host_settings())  # "" revision is invalid, not "HEAD"


if __name__ == "__main__":
    unittest.main(verbosity=1)
