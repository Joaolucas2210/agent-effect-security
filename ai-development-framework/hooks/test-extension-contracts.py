"""ADR 0039 (Proposed): the `PolicySource` seam changes nothing by default and cannot weaken a decision.

Equivalence: the default source, an explicit `HostPolicyFile` and the legacy keyword pair give the same outcome,
reason code and bundle shape. Failure injection: a source that raises or returns anything off-contract denies every
read with `host_policy_invalid`, before any workspace is prepared. No bypass: the PDP and PEP still run, the
sensitive-path rule still denies, the R-09 `gate_only` check still runs, persistence and signing failures keep their
existing deny codes. Selection is by explicit constructor argument only.
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
import integration.local_evidence_bundle as bundle_module  # noqa: E402
import integration.local_read_adapter as adapter_module  # noqa: E402
from integration import evidence_signing as signing  # noqa: E402
from integration.extensions import HostPolicyFile, PolicySource  # noqa: E402
from integration.local_read_adapter import LocalReadAdapter, load_host_policy  # noqa: E402

PUBLIC, SECRET = "allowed-public-content", "conteudo-secreto"
SENSITIVE_REASON = "invalid_scope"  # today's code for a root dotfile under any grant (ADR 0036)
_VOLATILE = {"bundle_id", "bundle_sha256", "created_at", "timestamp", "workspace_id", "snapshot_digest", "receipt_id", "receipt_sha256", "decision_id", "decision_sha256", "intent_id", "content_sha256", "read_result_digest"}


def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def shape(value):
    """Bundle structure with run-specific values masked: keys, types and every stable value."""
    if isinstance(value, dict): return {key: ("<volatile>" if key in _VOLATILE else shape(item)) for key, item in value.items()}
    if isinstance(value, list): return [shape(item) for item in value]
    return value


class Loaded:
    """A test PolicySource returning a fixed (config, pin)."""
    def __init__(self, value): self.value = value
    def load(self): return self.value


class Raising:
    def load(self): raise RuntimeError(SECRET)


class ExtensionContractsTest(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(); self.repo = self.base / "repo"; self.repo.mkdir()
        (self.repo / "docs").mkdir(); (self.repo / "docs/readme.md").write_text(PUBLIC); (self.repo / ".env").write_text(SECRET); (self.repo / "big.txt").write_text("x" * 200)
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "e@example.invalid"); git(self.repo, "config", "user.name", "e"); git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "f")
        self.schemas = adapter_module.schemas()
        self.count = 0

    def policy(self, path="docs/readme.md", run_id="run-host", budget=64):
        request = adapter_module.build_request({"snapshot_digest": "a" * 64}, run_id, path, budget)
        config = {"schema_version": "1.0", **{key: request[key] for key in ("profiles", "policy", "context")}}
        target = self.base / f"policy-{path.replace('/', '_')}.json"; target.write_text(json.dumps(config))
        return target, adapter_module.digest(config), config

    def adapter(self, **kwargs):
        self.count += 1
        return LocalReadAdapter(self.repo, "HEAD", self.base / f"evidence-{self.count}", self.base, **kwargs)

    def observe(self, adapter, path, run_id="run-host", **kwargs):
        result = adapter.read(run_id, path, 64, **kwargs)
        bundle = json.loads(Path(result["bundle_path"]).read_text()) if result["bundle_path"] else None
        return result["outcome"], result["reason_code"], result.get("content"), shape(bundle)

    def assert_denied_before_workspace(self, adapter):
        with patch.object(adapter_module.WorkspaceManager, "prepare", side_effect=AssertionError("an invalid policy must not prepare")):
            result = adapter.read("run-host", "docs/readme.md", 64)
        self.assertEqual((result["outcome"], result["reason_code"], result["bundle_path"]), ("deny", "host_policy_invalid", None))
        self.assertNotIn(SECRET, json.dumps(result))

    # Equivalence ------------------------------------------------------------------------------------------------

    def test_default_explicit_and_legacy_policy_wiring_are_equivalent(self):
        target, pin, _ = self.policy()
        sensitive_target, sensitive_pin, _ = self.policy(".env")
        for path, policy_path, policy_pin in (("docs/readme.md", target, pin), ("big.txt", target, pin), (".env", sensitive_target, sensitive_pin)):
            legacy = self.observe(self.adapter(host_policy_path=str(policy_path), host_policy_sha256=policy_pin), path)
            explicit = self.observe(self.adapter(policy_source=HostPolicyFile(str(policy_path), policy_pin)), path)
            injected = self.observe(self.adapter(policy_source=Loaded((json.loads(policy_path.read_text()), policy_pin))), path)
            self.assertEqual(legacy, explicit, path); self.assertEqual(legacy, injected, path)
        demo_default, demo_explicit = self.observe(self.adapter(), "docs/readme.md"), self.observe(self.adapter(policy_source=HostPolicyFile()), "docs/readme.md")
        self.assertEqual(demo_default, demo_explicit); self.assertEqual(demo_default[:3], ("delivered", demo_default[1], PUBLIC))

    def test_outcomes_match_the_documented_reason_codes(self):
        target, pin, _ = self.policy(); sensitive_target, sensitive_pin, _ = self.policy(".env")
        allowed = self.observe(self.adapter(policy_source=HostPolicyFile(str(target), pin)), "docs/readme.md")
        self.assertEqual(allowed[0], "delivered"); self.assertEqual(allowed[2], PUBLIC)
        self.assertEqual(self.observe(self.adapter(policy_source=HostPolicyFile(str(target), pin)), "big.txt")[:3], ("deny", "scope_not_allowlisted", None))
        sensitive = self.observe(self.adapter(policy_source=HostPolicyFile(str(sensitive_target), sensitive_pin)), ".env")
        self.assertEqual(sensitive[0], "deny"); self.assertIsNone(sensitive[2], "a pinned grant never overrides the sensitive-path rule")

    def test_load_host_policy_keeps_its_errors_and_output(self):
        target, pin, config = self.policy()
        self.assertEqual(load_host_policy(str(target), pin, self.schemas), config)
        for path, value in ((str(target), None), (None, pin), ("relative.json", pin), (str(target), "0" * 64), (str(target), "Z" * 64)):
            with self.assertRaises(ValueError) as caught: load_host_policy(path, value, self.schemas)
            self.assertEqual(caught.exception.args, ("host_policy_invalid",))
        with self.assertRaises(FileNotFoundError): load_host_policy(str(self.base / "missing.json"), pin, self.schemas)
        self.assertIsNone(HostPolicyFile().load(), "both absent selects the reference demo")

    # Failure injection ------------------------------------------------------------------------------------------

    def test_any_off_contract_source_denies_every_read_before_a_workspace_exists(self):
        target, pin, config = self.policy()
        tampered = copy.deepcopy(config); tampered["policy"]["rules"][0]["max_output_bytes"] = 1 << 20
        rehashed = copy.deepcopy(tampered); adapter_module._rehash(rehashed["policy"], "policy_sha256")
        sources = [Raising(), Loaded("not-a-pair"), Loaded((config,)), Loaded((config, pin, "extra")), Loaded((config, "0" * 64)), Loaded((config, None)),
                   Loaded((tampered, adapter_module.digest(tampered))), Loaded((rehashed, pin)), Loaded(([], adapter_module.digest([]))),
                   HostPolicyFile(str(target), None), HostPolicyFile(None, pin), HostPolicyFile("relative.json", pin), HostPolicyFile(str(self.base / "missing.json"), pin)]
        for source in sources:
            with self.subTest(source=type(source).__name__): self.assert_denied_before_workspace(self.adapter(policy_source=source))

    def test_a_source_plus_the_legacy_pair_is_ambiguous_and_denies(self):
        target, pin, config = self.policy()
        self.assert_denied_before_workspace(self.adapter(policy_source=Loaded((config, pin)), host_policy_path=str(target), host_policy_sha256=pin))
        self.assert_denied_before_workspace(self.adapter(policy_source=HostPolicyFile(), host_policy_sha256=pin))

    def test_a_source_cannot_mutate_the_policy_after_it_was_checked(self):
        _, pin, config = self.policy()
        source = Loaded((config, pin)); adapter = self.adapter(policy_source=source)
        config["policy"]["rules"][0]["allowed_scopes"] = [{"kind": "filesystem", "path": "big.txt"}]
        self.assertEqual(adapter.read("run-host", "big.txt", 64)["reason_code"], "scope_not_allowlisted")
        self.assertEqual(adapter.read("run-host", "docs/readme.md", 64)["content"], PUBLIC)

    def test_source_is_consulted_once_at_construction(self):
        _, pin, config = self.policy()
        class Counting(Loaded):
            calls = 0
            def load(self): Counting.calls += 1; return super().load()
        adapter = self.adapter(policy_source=Counting((config, pin)))
        for _ in range(2): adapter.read("run-host", "docs/readme.md", 64)
        self.assertEqual(Counting.calls, 1)

    def test_persistence_failure_keeps_its_deny_with_an_injected_source(self):
        _, pin, config = self.policy()
        with patch.object(adapter_module, "persist_bundle", side_effect=OSError(SECRET)):
            result = self.adapter(policy_source=Loaded((config, pin))).read("run-host", "docs/readme.md", 64)
        self.assertEqual((result["outcome"], result["reason_code"]), ("deny", "adapter_failed")); self.assertNotIn("content", result)
        with patch.object(adapter_module, "persist_bundle", side_effect=signing.SigningUnavailable("x")):
            result = self.adapter(policy_source=Loaded((config, pin))).read("run-host", "docs/readme.md", 64)
        self.assertEqual((result["outcome"], result["reason_code"]), ("deny", "evidence_signing_unavailable")); self.assertNotIn("content", result)

    def test_signing_failure_and_success_are_unchanged_with_an_injected_source(self):
        _, pin, config = self.policy()
        bad_key = self.base / "bad.key"; bad_key.write_bytes(b"short"); os.chmod(bad_key, 0o400)
        with patch.dict(os.environ, {"ADF_EVIDENCE_KEY_FILE": str(bad_key)}):
            result = self.adapter(policy_source=Loaded((config, pin))).read("run-host", "docs/readme.md", 64)
        self.assertEqual(result["outcome"], "deny"); self.assertIn(result["reason_code"], ("evidence_signing_unavailable", "attempt_evidence_failed")); self.assertNotIn("content", result)
        key = signing.init_key(self.base / "good.key")
        with patch.dict(os.environ, {"ADF_EVIDENCE_KEY_FILE": str(key)}):
            result = self.adapter(policy_source=Loaded((config, pin))).read("run-host", "docs/readme.md", 64)
        self.assertEqual(signing.verify_file(result["bundle_path"], signing.load_key(key)), "valid")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ADF_EVIDENCE_KEY_FILE", None)
            plain = self.adapter(policy_source=Loaded((config, pin))).read("run-host", "docs/readme.md", 64)
        self.assertEqual(signing.verify_file(plain["bundle_path"], signing.load_key(key)), "unsigned", "no seam marks unsigned evidence as signed")

    # No bypass --------------------------------------------------------------------------------------------------

    def test_pdp_and_pep_still_decide_and_revalidate_with_an_injected_source(self):
        _, pin, config = self.policy()
        original_enforce = adapter_module.PolicyEnforcementPoint.enforce_read
        with patch.object(bundle_module, "decide", wraps=bundle_module.decide) as decide, patch.object(adapter_module.PolicyEnforcementPoint, "enforce_read", autospec=True, side_effect=original_enforce) as enforce:
            adapter = self.adapter(policy_source=Loaded((config, pin)))
            self.assertEqual(adapter.read("run-host", "docs/readme.md", 64)["outcome"], "delivered")
            self.assertEqual((decide.call_count, enforce.call_count), (1, 1))
            self.assertEqual(adapter.read("run-host", "big.txt", 64)["reason_code"], "scope_not_allowlisted")
            self.assertEqual((decide.call_count, enforce.call_count), (2, 1), "a PDP deny never reaches the PEP")

    def test_sensitive_path_rule_holds_under_a_pinned_grant_from_a_source(self):
        _, pin, config = self.policy(".env")
        result = self.adapter(policy_source=Loaded((config, pin))).read("run-host", ".env", 64)
        self.assertEqual((result["outcome"], result["reason_code"]), ("deny", SENSITIVE_REASON)); self.assertNotIn("content", result); self.assertNotIn(SECRET, json.dumps(result))

    def test_r09_gate_only_check_still_runs_first(self):
        _, pin, config = self.policy("docs/readme.md")
        (self.repo / "docs/readme.md").unlink(); os.symlink(self.repo / ".env", self.repo / "docs/readme.md")
        adapter = self.adapter(policy_source=Loaded((config, pin)))
        with patch.object(adapter_module.WorkspaceManager, "prepare", side_effect=AssertionError("R-09 denies before any workspace")):
            result = adapter.read("run-host", "docs/readme.md", 64, delivery_mode="gate_only")
        self.assertEqual((result["outcome"], result["reason_code"], result["bundle_path"]), ("deny", "unsafe_file_type", None))

    # Selection --------------------------------------------------------------------------------------------------

    def test_selection_is_by_explicit_argument_only(self):
        target, pin, _ = self.policy()
        with patch.dict(os.environ, {"ADF_READ_POLICY_FILE": str(target), "ADF_READ_POLICY_SHA256": "0" * 64}):
            self.assertEqual(self.observe(self.adapter(), "docs/readme.md")[0], "delivered", "the adapter reads no policy env; hooks pass it explicitly")
        source = (ROOT / "integration/extensions.py").read_text()
        for forbidden in ("os.environ", "getenv", "importlib", "entry_points", "__import__", "pkg_resources", "register"):
            self.assertNotIn(forbidden, source)
        source: PolicySource = HostPolicyFile()  # structural Protocol: nothing to register
        self.assertIsNone(source.load())


if __name__ == "__main__": unittest.main(verbosity=2)
