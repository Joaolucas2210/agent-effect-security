"""Phase 2B (ARCH-09/R-16): integration/host_config.py is a pure, typed view of the ADF_* environment.

Each product variable is checked against the reader that consumes it today, with the same synthetic env
(os.environ patched, cleared, restored). Consumers are not rewired here; this proves the config is a drop-in.
"""
import os
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from integration import evidence_signing, mcp_registry, otel_export, read_gate_host  # noqa: E402
from integration.cli import read_policy_status  # noqa: E402
from integration.host_config import Secret, from_env, hook_environ  # noqa: E402

SECRET_HEX = "ab" * 32
SECRETS = {"ADF_A2A_HS256_SECRET": SECRET_HEX, "ADF_OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Basic%20c2stbGVhaw",
           "ADF_OTEL_EXPORTER_OTLP_ENDPOINT": "https://user:pw-leak@collector.example"}


def under(env):
    return mock.patch.dict(os.environ, env, clear=True)


def migrated_host_settings(cfg):
    """What read_gate_host.host_settings becomes once it reads HostConfig: syntax from the config, I/O stays."""
    run, configured = cfg.run, cfg.run.trusted_repository
    if configured is None and run.claude_project_dir is not None and Path(run.claude_project_dir).resolve() != read_gate_host.DEFAULT_REPOSITORY:
        return None
    root = Path(configured) if configured is not None else read_gate_host.DEFAULT_REPOSITORY
    value = cfg.evidence.evidence_dir
    evidence = Path(value) if value is not None else read_gate_host.DEFAULT_EVIDENCE_DIR if configured is None else None
    if not root.is_absolute() or not root.is_dir() or evidence is None or not evidence.is_absolute() or (evidence.exists() and not evidence.is_dir()):
        return None
    if not run.revision_valid or run.max_output_bytes is None:
        return None
    return root.resolve(), run.trusted_revision, evidence.resolve(), run.max_output_bytes


class HostConfigTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        (self.base / "repo").mkdir(); (self.base / "file").write_text("x")

    def test_absence_gives_defaults(self):
        cfg = from_env({})
        self.assertEqual((cfg.run.trusted_repository, cfg.run.trusted_revision, cfg.run.max_output_bytes, cfg.run.run_id, cfg.run.adf_home), (None, "HEAD", 1 << 20, None, None))
        self.assertEqual((cfg.policy.read_policy_state, cfg.policy.mcp_registry_state, cfg.policy.mcp_probe_max_age_days), ("demo", "absent", 30))
        self.assertEqual((cfg.evidence.evidence_dir, cfg.evidence.evidence_key_file, cfg.evidence.capture_timings), (None, None, False))
        self.assertEqual((cfg.a2a.url, cfg.a2a.token_file, cfg.a2a.port, cfg.a2a.issuer, cfg.a2a.audience, cfg.a2a.confirm_skills, cfg.a2a.auth_mode), ("", "", 8765, "adf-test-idp", "adf-a2a-local", frozenset(), "hs256"))
        self.assertEqual((cfg.otel.enabled, cfg.otel.endpoint.reveal(), cfg.otel.headers.reveal(), cfg.otel.flush_seconds, cfg.otel.service_name), (False, "http://127.0.0.1:4318", "", 0.3, "adf-control-plane"))

    def test_host_settings_equivalence(self):
        repo, file = str(self.base / "repo"), str(self.base / "file")
        cases = [{}, {"ADF_TRUSTED_REPOSITORY": repo}, {"ADF_TRUSTED_REPOSITORY": repo, "ADF_EVIDENCE_DIR": str(self.base / "ev")},
                 {"ADF_TRUSTED_REPOSITORY": "rel", "ADF_EVIDENCE_DIR": "/abs"}, {"ADF_TRUSTED_REPOSITORY": repo, "ADF_EVIDENCE_DIR": "rel"},
                 {"ADF_TRUSTED_REPOSITORY": repo, "ADF_EVIDENCE_DIR": file}, {"ADF_TRUSTED_REPOSITORY": "", "ADF_EVIDENCE_DIR": "/abs"},
                 {"CLAUDE_PROJECT_DIR": repo}, {"CLAUDE_PROJECT_DIR": str(read_gate_host.DEFAULT_REPOSITORY)}]
        for budget in ("", "0", "-1", "abc", "1.5", "٣", " 7", "007", "4096"):
            cases.append({"ADF_TRUSTED_REPOSITORY": repo, "ADF_EVIDENCE_DIR": str(self.base / "ev"), "ADF_MAX_OUTPUT_BYTES": budget})
        for revision in ("", "-x", "main"):  # NUL cannot reach a real environ; revision_valid covers it below
            cases.append({"ADF_TRUSTED_REPOSITORY": repo, "ADF_EVIDENCE_DIR": str(self.base / "ev"), "ADF_TRUSTED_REVISION": revision})
        for env in cases:
            with self.subTest(env=env), under(env):
                self.assertEqual(migrated_host_settings(from_env(env)), read_gate_host.host_settings())
        self.assertFalse(from_env({"ADF_TRUSTED_REVISION": "a\x00b"}).run.revision_valid)

    def test_read_policy_pair_equivalence(self):
        for env in ({}, {"ADF_READ_POLICY_FILE": "/p"}, {"ADF_READ_POLICY_SHA256": "a" * 64}, {"ADF_READ_POLICY_FILE": "", "ADF_READ_POLICY_SHA256": ""},
                    {"ADF_READ_POLICY_FILE": "rel", "ADF_READ_POLICY_SHA256": "a" * 64}):
            with self.subTest(env=env), under(env):
                cfg, today = from_env(env), read_gate_host.host_policy_settings()
                self.assertEqual((cfg.policy.read_policy_file, cfg.policy.read_policy_sha256), (today["host_policy_path"], today["host_policy_sha256"]))
                status, detail = read_policy_status(env.get)
                expected = "demo" if status == "demo" else "partial" if str(detail).startswith("partial") else "configured"
                self.assertEqual(cfg.policy.read_policy_state, expected)

    def test_mcp_registry_equivalence(self):
        for env in ({}, {"ADF_MCP_REGISTRY_FILE": ""}, {"ADF_MCP_REGISTRY_FILE": "/r"}, {"ADF_MCP_REGISTRY_SHA256": "b"}, {"ADF_MCP_REGISTRY_FILE": "/r", "ADF_MCP_REGISTRY_SHA256": "b"}):
            with self.subTest(env=env), under(env):
                try:
                    today = "absent" if mcp_registry.configured() is None else "configured"
                except mcp_registry.RegistryInvalid:
                    today = "partial"
                self.assertEqual(from_env(env).policy.mcp_registry_state, today)

    def test_lazy_failures_match_today(self):
        """cli.py:257 int(), a2a_gateway.py:518 int(), :494 bytes.fromhex(os.environ[...])."""
        for raw in ("x", "", "1.5"):
            cfg = from_env({"ADF_MCP_PROBE_MAX_AGE_DAYS": raw, "ADF_A2A_PORT": raw})
            self.assertRaises(ValueError, lambda: cfg.policy.mcp_probe_max_age_days)
            self.assertRaises(ValueError, lambda: cfg.a2a.port)
        self.assertEqual(from_env({"ADF_MCP_PROBE_MAX_AGE_DAYS": "-1"}).policy.mcp_probe_max_age_days, -1)  # doctor rejects < 0 itself
        self.assertRaises(KeyError, from_env({}).a2a.hs256_key)
        self.assertRaises(ValueError, from_env({"ADF_A2A_HS256_SECRET": "zz"}).a2a.hs256_key)
        self.assertEqual(from_env({"ADF_A2A_HS256_SECRET": SECRET_HEX}).a2a.hs256_key(), bytes.fromhex(SECRET_HEX))
        for env in ({"ADF_A2A_JWKS_FILE": "/j"}, {"ADF_A2A_JWKS_SHA256": ""}):
            self.assertEqual(from_env(env).a2a.auth_mode, "rs256")  # partial JWKS fails closed in load_jwks, never HS256

    def test_evidence_and_otel_equivalence(self):
        for env in ({}, {"ADF_EVIDENCE_KEY_FILE": ""}, {"ADF_EVIDENCE_KEY_FILE": "rel"}, {"ADF_EVIDENCE_KEY_FILE": "/k"},
                    {"ADF_OTEL_FLUSH_MS": "5000"}, {"ADF_OTEL_FLUSH_MS": "-3"}, {"ADF_OTEL_FLUSH_MS": "0"}, {"ADF_OTEL_FLUSH_MS": "x"}):
            with self.subTest(env=env), under(env):
                cfg = from_env(env)
                self.assertEqual(cfg.evidence.evidence_key_file, None if evidence_signing.key_path() is None else str(evidence_signing.key_path()))
                self.assertEqual(cfg.otel.flush_seconds, otel_export._flush_seconds())
        for raw, enabled in (("1", True), ("true", False), ("", False), (" 1", False)):
            self.assertEqual((from_env({"ADF_OTEL_ENABLED": raw}).otel.enabled, from_env({"ADF_CAPTURE_TIMINGS": raw}).evidence.capture_timings), (enabled, enabled))
        self.assertEqual(from_env({"ADF_A2A_CONFIRM_SKILLS": ",a,,b,"}).a2a.confirm_skills, frozenset({"a", "b"}))
        self.assertEqual(from_env({"ADF_OTEL_EXPORTER_OTLP_ENDPOINT": "http://h:1//"}).otel.endpoint.reveal(), "http://h:1")
        self.assertIsNone(from_env({"ADF_HOME": ""}).run.adf_home)  # `ADF_HOME or ~/.adf` in every reader

    def test_hook_precedence(self):
        """integration/read_hook.py:122-127: root is host-derived and overrides; the rest is setdefault (inherited wins, even empty)."""
        env = {"ADF_TRUSTED_REPOSITORY": "/stale", "ADF_TRUSTED_REVISION": "", "ADF_EVIDENCE_DIR": "/mine"}
        out = hook_environ(env, "/repo", "/home/.adf/evidence/p/d")
        self.assertEqual(out, {"ADF_TRUSTED_REPOSITORY": "/repo", "ADF_TRUSTED_REVISION": "", "ADF_MAX_OUTPUT_BYTES": str(1 << 20), "ADF_EVIDENCE_DIR": "/mine"})
        self.assertEqual(env["ADF_TRUSTED_REPOSITORY"], "/stale")  # input untouched
        simulated = dict(env); simulated["ADF_TRUSTED_REPOSITORY"] = "/repo"
        for key, value in (("ADF_TRUSTED_REVISION", "HEAD"), ("ADF_MAX_OUTPUT_BYTES", str(1 << 20)), ("ADF_EVIDENCE_DIR", "/home/.adf/evidence/p/d")):
            simulated.setdefault(key, value)
        self.assertEqual(out, simulated)

    def test_redaction(self):
        cfg = from_env({**SECRETS, "ADF_EVIDENCE_KEY_FILE": "/k"})
        for text in (repr(cfg), str(cfg), repr(cfg.redacted()), str(cfg.a2a), f"{cfg.otel}"):
            for leak in (SECRET_HEX, "c2stbGVhaw", "pw-leak"):
                self.assertNotIn(leak, text)
        self.assertEqual(cfg.redacted()["a2a"]["hs256_secret"], "<redacted>")
        self.assertIsNone(from_env({}).redacted()["a2a"]["hs256_secret"])
        self.assertNotEqual(Secret("v"), "v")
        self.assertNotIn(SECRET_HEX, repr(asdict(cfg)))

    def test_immutability_and_purity(self):
        env = {"ADF_HOME": "/h"}
        before = dict(os.environ)
        cfg = from_env(env)
        self.assertEqual(dict(os.environ), before)
        with self.assertRaises(FrozenInstanceError):
            cfg.run.adf_home = "/x"
        with self.assertRaises(AttributeError):
            cfg.otel.headers._value = "x"
        self.assertIsInstance(cfg.a2a.confirm_skills, frozenset)


if __name__ == "__main__":
    unittest.main(verbosity=1)
