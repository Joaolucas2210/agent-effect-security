"""Independent H3-01 contract, PEP, workspace and confined-read tests."""
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft7Validator


ROOT = Path(__file__).resolve().parent.parent
from tools.pdp import decide
from runtime.local_read_runtime import LocalReadRuntime, sensitive_path, verify_receipt
from runtime.pep import PolicyEnforcementPoint
from runtime import workspace_manager
from runtime.workspace_manager import SNAPSHOT_DIGEST_VERSION, WorkspaceManager, snapshot_digest


RUNTIME = ROOT / "runtime/v1"
TOOLS = ROOT / "tools/v1"
SCHEMAS = {"RuntimeWorkspaceDescriptor": "runtime-workspace-descriptor", "ReadResult": "read-result", "RuntimeAuditReceipt": "runtime-audit-receipt", "SensitivePathPolicyV1": "sensitive-path-policy-v1"}
H2_SCHEMAS = {key: json.loads((TOOLS / "schemas" / name).read_text()) for key, name in {"tool_profile": "tool-profile.schema.json", "tool_call_intent": "tool-call-intent.schema.json", "policy_bundle": "policy-bundle.schema.json", "policy_context": "policy-context.schema.json", "admission_decision": "admission-decision.schema.json", "list_files_input": "list-files-input.schema.json"}.items()}


def load(path): return json.loads(path.read_text())
def digest(value): return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
def rehash(value, field): value[field] = digest({key: item for key, item in value.items() if key != field})


class CountingRuntime(LocalReadRuntime):
    def __init__(self, policy): super().__init__(policy); self.calls = 0
    def read(self, *args): self.calls += 1; return super().read(*args)


class RuntimeReadTest(unittest.TestCase):
    declared = {"contracts", "oracle_meta", "valid_read", "deny", "approval", "invalid_contracts", "binding_mismatches", "workspace_mismatches", "workspace_failures", "two_runs", "cleanup", "path_inputs", "symlink", "file_types", "socket", "device", "sensitive", "limit", "alternate_command", "receipt", "source_boundaries", "snapshot", "compatibility"}
    executed, skipped, failed = set(), set(), set()

    @classmethod
    def setUpClass(cls):
        cls.policy = load(RUNTIME / "policies/sensitive-path-policy-v1.json")
        cls.runtime_schemas = {name: load(RUNTIME / "schemas" / f"{stem}.schema.json") for name, stem in SCHEMAS.items()}
        cls.oracle = load(RUNTIME / "tests/normative-oracles.json")
        for schema in [*cls.runtime_schemas.values(), *H2_SCHEMAS.values()]: Draft7Validator.check_schema(schema)

    @classmethod
    def tearDownClass(cls):
        missing = cls.declared - cls.executed - cls.skipped - cls.failed
        print(f"matrix declared: {len(cls.declared)}\nmatrix executed: {len(cls.executed)}\nmissing: {len(missing)}\nskipped: {len(cls.skipped)}\nfailed: {len(cls.failed)}")

    def mark(self, name): self.executed.add(name)

    def assert_workspace_failure(self, code, action):
        with self.assertRaises(RuntimeError) as raised: action()
        self.assertEqual(str(raised.exception), code)
        for value in ("/tmp/segredo", "--argv=token", "stderr-confidencial"):
            self.assertNotIn(value, str(raised.exception))

    def temporary_repository(self):
        temp = tempfile.TemporaryDirectory()
        repository = Path(temp.name) / "source"
        repository.mkdir(); self.git(repository, "init", "-q")
        self.git(repository, "config", "user.email", "h3@example.invalid"); self.git(repository, "config", "user.name", "H3")
        target = repository / "docs/readme.md"; target.parent.mkdir(); target.write_text("allowed")
        self.git(repository, "add", "."); self.git(repository, "commit", "-qm", "initial")
        return temp, repository

    @staticmethod
    def git(repository, *args): return subprocess.run(["git", "-C", str(repository), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def admission(self, descriptor, path="docs/readme.md", budget=64):
        profile = load(TOOLS / "examples/tool-profile/valid/read-worktree.json")
        policy = load(TOOLS / "examples/policy-bundle/valid/read-worktree.json")
        context = load(TOOLS / "examples/policy-context/valid/read-worktree.json")
        intent = load(TOOLS / "examples/tool-call-intent/valid/read-worktree.json")
        scope = {"kind": "filesystem", "path": path}
        profile["operations"][0].update(supported_scopes=[scope], max_risk={"level": "low", "max_output_bytes": budget})
        rehash(profile, "profile_sha256")
        policy["rules"][0].update(profile_sha256=profile["profile_sha256"], allowed_scopes=[scope], max_output_bytes=budget)
        rehash(policy, "policy_sha256")
        for key in ("organizational_constraints", "repository_constraints", "mode_constraints"):
            context[key].update(allowed_scopes=[scope], max_output_bytes=budget)
        context["resolved_run_config_ref"]["run_id"] = "run-h3-01"
        context["policy_ref"] = {"policy_id": policy["policy_id"], "policy_sha256": policy["policy_sha256"]}
        intent.update(run_id="run-h3-01", task_ref=descriptor["snapshot_digest"], resource_scope=scope, arguments={"path": path}, requested_budget={"max_output_bytes": budget}, policy_context_ref=copy.deepcopy(context["policy_ref"]))
        intent["tool_ref"]["profile_sha256"] = profile["profile_sha256"]
        decision = decide(intent, [profile], policy, context, H2_SCHEMAS)
        self.assertEqual(decision["outcome"], "admit_read", decision)
        return decision, intent, profile, policy, context

    def environment(self, repository):
        manager = WorkspaceManager(repository, "HEAD", Path(repository).parent)
        descriptor = manager.prepare("run-h3-01")
        runtime = CountingRuntime(self.policy)
        return manager, descriptor, runtime, PolicyEnforcementPoint(manager, runtime)

    def assert_result(self, result, receipt):
        Draft7Validator(self.runtime_schemas["ReadResult"]).validate(result)
        Draft7Validator(self.runtime_schemas["RuntimeAuditReceipt"]).validate(receipt)

    def test_contracts_fixtures_and_oracle(self):
        self.mark("contracts")
        self.assertEqual(self.oracle["coverage_status"], "complete")
        self.assertTrue((ROOT.parent / self.oracle["source"]["adr"]).is_file())
        for name, stem in SCHEMAS.items():
            validator = Draft7Validator(self.runtime_schemas[name])
            valid = next((RUNTIME / "examples" / stem / "valid").glob("*.json")); invalid = next((RUNTIME / "examples" / stem / "invalid").glob("*.json"))
            self.assertTrue(validator.is_valid(load(valid)), name); self.assertFalse(validator.is_valid(load(invalid)), name)
            for check in self.oracle["contracts"][name]["checks"]:
                current = self.runtime_schemas[name]
                for part in check["pointer"].strip("/").split("/"): current = current[part]
                if "expected" in check: self.assertEqual(current, check["expected"])
                else: self.assertTrue(all(item not in current for item in check["excludes"]))
        sensitive = self.oracle["contracts"]["SensitivePathPolicyV1"]
        self.assertEqual(self.policy, load(RUNTIME / sensitive["policy_file"]))
        self.assertTrue(set(sensitive["required_components"]).issubset(self.policy["deny_components"]))
        self.assertTrue(set(sensitive["required_prefixes"]).issubset(self.policy["deny_component_prefixes"]))
        self.assertTrue(set(sensitive["required_suffixes"]).issubset(self.policy["deny_component_suffixes"]))

    def test_static_oracle_detects_in_memory_relaxation(self):
        self.mark("oracle_meta")
        descriptor = copy.deepcopy(self.runtime_schemas["RuntimeWorkspaceDescriptor"]); descriptor["additionalProperties"] = True
        result = copy.deepcopy(self.runtime_schemas["ReadResult"]); result["required"].remove("taint")
        receipt = copy.deepcopy(self.runtime_schemas["RuntimeAuditReceipt"]); receipt["properties"]["content"] = {"type": "string"}
        self.assertNotEqual(descriptor["additionalProperties"], self.oracle["contracts"]["RuntimeWorkspaceDescriptor"]["checks"][0]["expected"])
        self.assertNotEqual(result["required"], self.oracle["contracts"]["ReadResult"]["checks"][1]["expected"])
        self.assertIn("content", receipt["properties"])

    def test_valid_admit_read_is_tainted_and_redacted(self):
        self.mark("valid_read")
        temp, repository = self.temporary_repository()
        try:
            manager, descriptor, runtime, pep = self.environment(repository); decision, intent, profile, policy, context = self.admission(descriptor)
            result, receipt = pep.enforce_read(decision, intent, profile, policy, context, descriptor)
            self.assert_result(result, receipt); self.assertEqual(result["content"], "allowed"); self.assertEqual(result["taint"]["classification"], "untrusted_workspace_file")
            self.assertNotIn("canonical_root", receipt); self.assertNotIn("allowed", json.dumps(receipt)); self.assertTrue(verify_receipt(receipt)); self.assertEqual(runtime.calls, 1)
            self.assertTrue(manager.cleanup(descriptor["workspace_id"]))
        finally: temp.cleanup()

    def test_deny_and_approval_never_open(self):
        self.mark("deny"); self.mark("approval")
        temp, repository = self.temporary_repository()
        try:
            manager, descriptor, runtime, pep = self.environment(repository); decision, intent, profile, policy, context = self.admission(descriptor)
            for outcome in ("deny", "approval_required"):
                rejected = copy.deepcopy(decision); rejected["outcome"] = outcome
                result, receipt = pep.enforce_read(rejected, intent, profile, policy, context, descriptor)
                self.assertEqual(result["outcome"], "deny"); self.assertEqual(runtime.calls, 0); self.assertIsNotNone(receipt)
            receipt_input = load(RUNTIME / "examples/runtime-audit-receipt/valid/delivered.json")
            result, _ = pep.enforce_read(receipt_input, intent, profile, policy, context, descriptor)
            self.assertEqual(result["outcome"], "deny"); self.assertEqual(runtime.calls, 0)
            manager.cleanup(descriptor["workspace_id"])
        finally: temp.cleanup()

    def test_invalid_contracts_never_open(self):
        self.mark("invalid_contracts")
        temp, repository = self.temporary_repository()
        try:
            manager, descriptor, runtime, pep = self.environment(repository); decision, intent, profile, policy, context = self.admission(descriptor)
            for field in H2_SCHEMAS["admission_decision"]["required"]:
                invalid = copy.deepcopy(decision); del invalid[field]
                result, receipt = pep.enforce_read(invalid, intent, profile, policy, context, descriptor)
                self.assertEqual(result["outcome"], "deny", field); self.assertEqual(runtime.calls, 0, field); self.assertIsNone(receipt, field)
            unknown = copy.deepcopy(decision); unknown["unknown"] = True
            result, receipt = pep.enforce_read(unknown, intent, profile, policy, context, descriptor)
            self.assertEqual(result["outcome"], "deny"); self.assertEqual(runtime.calls, 0); self.assertIsNone(receipt)
            denied = copy.deepcopy(decision); denied["outcome"] = "deny"
            result, _ = pep.enforce_read(denied, intent, profile, policy, context, descriptor)
            self.assertEqual(result["outcome"], "deny"); self.assertEqual(runtime.calls, 0)
            weakened = copy.deepcopy(H2_SCHEMAS["admission_decision"]); weakened["required"].remove("decision_id")
            missing_id = copy.deepcopy(decision); del missing_id["decision_id"]
            self.assertTrue(Draft7Validator(weakened).is_valid(missing_id))
            result, _ = pep.enforce_read(missing_id, intent, profile, policy, context, descriptor)
            self.assertEqual(result["outcome"], "deny"); self.assertEqual(runtime.calls, 0)
            for name, value in (("intent", intent), ("profile", profile), ("policy", policy), ("context", context), ("descriptor", descriptor)):
                invalid_inputs = [copy.deepcopy(item) for item in (decision, intent, profile, policy, context, descriptor)]
                {"intent": invalid_inputs[1], "profile": invalid_inputs[2], "policy": invalid_inputs[3], "context": invalid_inputs[4], "descriptor": invalid_inputs[5]}[name]["unknown"] = True
                result, _ = pep.enforce_read(*invalid_inputs)
                self.assertEqual(result["outcome"], "deny", name); self.assertEqual(runtime.calls, 0, name)
            manager.cleanup(descriptor["workspace_id"])
        finally: temp.cleanup()

    def test_all_revalidated_bindings_deny_without_open(self):
        self.mark("binding_mismatches")
        temp, repository = self.temporary_repository()
        try:
            mutations = {
                "decision": lambda d, i, p, b, c, w: d.update(intent_digest="0" * 64),
                "intent": lambda d, i, p, b, c, w: i.update(run_id="other"),
                "profile": lambda d, i, p, b, c, w: p.update(provider_version="other"),
                "policy": lambda d, i, p, b, c, w: b.update(policy_id="other"),
                "operation": lambda d, i, p, b, c, w: i.update(operation_id="other"),
                "scope": lambda d, i, p, b, c, w: i.update(resource_scope={"kind": "filesystem", "path": "docs/other.md"}, arguments={"path": "docs/other.md"}),
                "budget": lambda d, i, p, b, c, w: i.update(requested_budget={"max_output_bytes": 1}),
                "task_ref": lambda d, i, p, b, c, w: i.update(task_ref="0" * 64),
                "snapshot": lambda d, i, p, b, c, w: w.update(snapshot_digest="0" * 64),
            }
            for mutate in mutations.values():
                manager, descriptor, runtime, pep = self.environment(repository); decision, intent, profile, policy, context = self.admission(descriptor)
                mutate(decision, intent, profile, policy, context, descriptor)
                result, _ = pep.enforce_read(decision, intent, profile, policy, context, descriptor)
                self.assertEqual(result["outcome"], "deny"); self.assertEqual(runtime.calls, 0); manager.cleanup(descriptor["workspace_id"])
        finally: temp.cleanup()

    def test_descriptor_ownership_lifecycle_and_root_are_bound(self):
        self.mark("workspace_mismatches")
        temp, repository = self.temporary_repository()
        try:
            for mutate in (lambda w: w.clear(), lambda w: w.update(canonical_root="/not-trusted"), lambda w: w.update(ownership="agent_owned"), lambda w: w.update(lifecycle="pending_cleanup")):
                manager, descriptor, runtime, pep = self.environment(repository); decision, intent, profile, policy, context = self.admission(descriptor)
                mutate(descriptor); result, _ = pep.enforce_read(decision, intent, profile, policy, context, descriptor)
                self.assertEqual(result["outcome"], "deny"); self.assertEqual(runtime.calls, 0)
        finally: temp.cleanup()

    def test_two_runs_are_distinct_and_preserve_original_checkout(self):
        self.mark("two_runs")
        temp, repository = self.temporary_repository()
        try:
            manager = WorkspaceManager(repository, "HEAD", Path(repository).parent); first, second = manager.prepare("run-h3-01"), manager.prepare("run-h3-01")
            self.assertNotEqual(first["workspace_id"], second["workspace_id"]); self.assertNotEqual(first["canonical_root"], second["canonical_root"]); self.assertEqual(self.git(repository, "status", "--porcelain").stdout, "")
            self.assertTrue(manager.cleanup(first["workspace_id"])); self.assertTrue(manager.cleanup(second["workspace_id"]))
        finally: temp.cleanup()

    def test_cleanup_is_idempotent_and_path_safe(self):
        self.mark("cleanup")
        temp, repository = self.temporary_repository()
        try:
            manager, descriptor, _, _ = self.environment(repository); self.assertFalse(manager.cleanup("unknown"))
            record = manager._records[descriptor["workspace_id"]]; original = record["canonical_root"]; record["canonical_root"] = str(repository.resolve())
            self.assertFalse(manager.cleanup(descriptor["workspace_id"])); self.assertTrue(repository.is_dir())
            record["canonical_root"] = original; self.assertTrue(manager.cleanup(descriptor["workspace_id"])); self.assertTrue(manager.cleanup(descriptor["workspace_id"]))
        finally: temp.cleanup()

    def test_workspace_failures_are_stable_and_redacted(self):
        self.mark("workspace_failures")
        secret = "/tmp/segredo --argv=token stderr-confidencial"
        error = subprocess.CalledProcessError(1, ["git", secret], stderr=secret.encode())
        completed = lambda output: subprocess.CompletedProcess([], 0, stdout=output, stderr=b"")
        temp, repository = self.temporary_repository()
        try:
            parent = Path(repository).parent
            self.assert_workspace_failure("workspace_repository_invalid", lambda: WorkspaceManager(parent / "missing", "HEAD", parent))
            self.assert_workspace_failure("workspace_configuration_invalid", lambda: WorkspaceManager(repository, "HEAD", parent / "missing"))
            self.assert_workspace_failure("workspace_run_id_invalid", lambda: WorkspaceManager(repository, "HEAD", parent).prepare("invalid id"))
            with patch.object(workspace_manager.subprocess, "run", side_effect=FileNotFoundError(secret)):
                self.assert_workspace_failure("workspace_git_unavailable", lambda: WorkspaceManager(repository, "HEAD", parent).prepare("run-h3-01"))
            with patch.object(workspace_manager.subprocess, "run", side_effect=error):
                self.assert_workspace_failure("workspace_revision_unavailable", lambda: WorkspaceManager(repository, "HEAD", parent).prepare("run-h3-01"))
            with patch.object(workspace_manager.subprocess, "run", side_effect=[completed(b"a" * 40), error]):
                self.assert_workspace_failure("workspace_snapshot_enumeration_failed", lambda: WorkspaceManager(repository, "HEAD", parent).prepare("run-h3-01"))
            tree = b"100644 blob " + b"b" * 40 + b"\tdocs/readme.md\0"
            with patch.object(workspace_manager.subprocess, "run", side_effect=[completed(b"a" * 40), completed(tree), error]):
                self.assert_workspace_failure("workspace_worktree_prepare_failed", lambda: WorkspaceManager(repository, "HEAD", parent).prepare("run-h3-01"))
            manager, descriptor, _, _ = self.environment(repository)
            try:
                with patch.object(workspace_manager.subprocess, "run", side_effect=error):
                    self.assert_workspace_failure("workspace_worktree_cleanup_failed", lambda: manager.cleanup(descriptor["workspace_id"]))
            finally:
                manager.cleanup(descriptor["workspace_id"])
            manager, descriptor, _, _ = self.environment(repository)
            try:
                with patch.object(workspace_manager.subprocess, "run", side_effect=[completed(b""), error]):
                    self.assert_workspace_failure("workspace_worktree_prune_failed", lambda: manager.cleanup(descriptor["workspace_id"]))
            finally:
                manager.cleanup(descriptor["workspace_id"])
        finally: temp.cleanup()

    def test_bad_paths_and_alternate_command_do_not_read(self):
        self.mark("path_inputs"); self.mark("alternate_command")
        descriptor = load(RUNTIME / "examples/runtime-workspace-descriptor/valid/minimum.json")
        runtime = LocalReadRuntime(self.policy)
        for path in ("../escape", "/absolute", "x\x00y", "", "docs//x"):
            self.assertEqual(runtime.read(descriptor, path, 64)["outcome"], "deny")
        temp, repository = self.temporary_repository()
        try:
            manager, workspace, counted, pep = self.environment(repository); decision, intent, profile, policy, context = self.admission(workspace)
            intent["arguments"] = {"path": "docs/readme.md", "command": "cat docs/readme.md"}
            result, _ = pep.enforce_read(decision, intent, profile, policy, context, workspace)
            self.assertEqual(result["outcome"], "deny"); self.assertEqual(counted.calls, 0); manager.cleanup(workspace["workspace_id"])
        finally: temp.cleanup()

    def test_symlink_and_nonregular_files_are_denied(self):
        self.mark("symlink"); self.mark("file_types")
        temp, repository = self.temporary_repository()
        try:
            manager, descriptor, runtime, _ = self.environment(repository); root = Path(descriptor["canonical_root"])
            os.symlink("/etc/passwd", root / "escape"); (root / "directory").mkdir(); os.mkfifo(root / "fifo")
            unix = socket.socket(socket.AF_UNIX)
            try:
                unix.bind(str(root / "socket")); socket_paths = ("escape", "directory", "fifo", "socket"); self.mark("socket")
            except PermissionError:
                unix.close(); unix = None; self.skipped.add("socket"); socket_paths = ("escape", "directory", "fifo")
            try:
                for path in socket_paths:
                    self.assertEqual(runtime.read(descriptor, path, 64)["outcome"], "deny")
                try:
                    os.mknod(root / "device", stat.S_IFCHR | 0o600, os.makedev(1, 3))
                except (AttributeError, PermissionError, OSError):
                    self.skipped.add("device")
                else:
                    self.assertEqual(runtime.read(descriptor, "device", 64)["outcome"], "deny"); self.mark("device")
            finally:
                if unix is not None: unix.close()
            manager.cleanup(descriptor["workspace_id"])
        finally: temp.cleanup()

    def test_sensitive_policy_and_output_limit_deny_without_content(self):
        self.mark("sensitive"); self.mark("limit")
        for path in (".env", ".env.local", "docs/.env.local", ".git/config", "secrets/key", "docs/secrets/key", "credentials/key", "docs/credentials/key", "id_rsa", "cert.pem", "cert.key"):
            self.assertTrue(sensitive_path(path, self.policy), path)
        temp, repository = self.temporary_repository()
        try:
            manager, descriptor, runtime, _ = self.environment(repository); root = Path(descriptor["canonical_root"]); (root / ".env").write_text("secret"); (root / "large.txt").write_text("too-large")
            for path, budget, code in ((".env", 64, "sensitive_path_denied"), ("large.txt", 1, "output_limit_exceeded")):
                result = runtime.read(descriptor, path, budget); self.assertEqual((result["outcome"], result["reason_code"]), ("deny", code)); self.assertNotIn("content", result)
            manager.cleanup(descriptor["workspace_id"])
        finally: temp.cleanup()

    def test_receipt_verification_is_pure_and_not_authorization(self):
        self.mark("receipt")
        temp, repository = self.temporary_repository()
        try:
            manager, descriptor, _, pep = self.environment(repository); decision, intent, profile, policy, context = self.admission(descriptor)
            result, receipt = pep.enforce_read(decision, intent, profile, policy, context, descriptor); self.assertTrue(verify_receipt(receipt)); self.assertFalse(verify_receipt({**receipt, "content": "forbidden"}))
            for field in self.runtime_schemas["RuntimeAuditReceipt"]["required"]:
                invalid = copy.deepcopy(receipt); del invalid[field]
                self.assertFalse(verify_receipt(invalid), field)
            invalid = copy.deepcopy(receipt); invalid["unknown"] = True; self.assertFalse(verify_receipt(invalid))
            invalid = copy.deepcopy(receipt); invalid["timestamp"] = "not-a-timestamp"; invalid["receipt_id"] = digest({key: value for key, value in invalid.items() if key != "receipt_id"}); self.assertFalse(verify_receipt(invalid))
            invalid = copy.deepcopy(receipt); invalid["effective_scope"]["path"] = "/absolute"; invalid["receipt_id"] = digest({key: value for key, value in invalid.items() if key != "receipt_id"}); self.assertFalse(verify_receipt(invalid))
            self.assertNotIn(descriptor["canonical_root"], json.dumps(receipt)); self.assertNotIn(result["content"], json.dumps(receipt)); manager.cleanup(descriptor["workspace_id"])
        finally: temp.cleanup()

    def test_source_boundaries_and_snapshot_algorithm(self):
        self.mark("source_boundaries"); self.mark("snapshot"); self.mark("compatibility")
        for name in ("pep.py", "local_read_runtime.py"):
            source = (ROOT / "runtime" / name).read_text().lower()
            for forbidden in ("import subprocess", "import socket", "urllib", "http.client", "mcp", "docker", "getenv", "environ", "os.system"):
                self.assertNotIn(forbidden, source, name)
        manager_source = (ROOT / "runtime/workspace_manager.py").read_text()
        self.assertIn("subprocess.run", manager_source); self.assertNotIn("shell=", manager_source)
        runtime_source = (ROOT / "runtime/local_read_runtime.py").read_text(); self.assertIn("os.fstat", runtime_source); self.assertIn("stat.S_ISREG", runtime_source)
        temp, repository = self.temporary_repository()
        try:
            commit, expected = snapshot_digest(repository, "HEAD"); manager, descriptor, _, _ = self.environment(repository)
            self.assertEqual(descriptor["task_ref"], expected); self.assertEqual(descriptor["snapshot_digest"], expected); self.assertNotEqual(commit, expected); self.assertEqual(SNAPSHOT_DIGEST_VERSION, "git-tree-items-v1"); manager.cleanup(descriptor["workspace_id"])
        finally: temp.cleanup()


if __name__ == "__main__": unittest.main(verbosity=2)
