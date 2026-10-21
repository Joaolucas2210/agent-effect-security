"""Negative-first checks for the read-only reference adapter and its Claude Code gate."""
import importlib.util
import asyncio
import copy
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
import integration.local_read_adapter as adapter_module
from integration.local_evidence_bundle import is_authorization, verify_offline
from integration.local_read_adapter import LocalReadAdapter
from runtime.local_read_runtime import LocalReadRuntime

_SPEC = importlib.util.spec_from_file_location("claude_code_read_gate", ROOT / "hooks/claude-code-read-gate.py")
gate = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(gate)
_CODEX_SPEC = importlib.util.spec_from_file_location("codex_bash_read_gate", ROOT / "hooks/codex-bash-read-gate.py")
codex_gate = importlib.util.module_from_spec(_CODEX_SPEC); _CODEX_SPEC.loader.exec_module(codex_gate)
SECRET, PUBLIC = "conteudo-secreto-do-arquivo", "allowed-public-content"


def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class LocalReadAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "source"; self.repo.mkdir(); self.repo = self.repo.resolve()
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "p0@example.invalid"); git(self.repo, "config", "user.name", "P0")
        (self.repo / "docs").mkdir(); (self.repo / "docs/readme.md").write_text(PUBLIC)
        (self.repo / "secrets").mkdir(); (self.repo / "secrets/token").write_text(SECRET)
        (self.repo / "big.txt").write_text("x" * 200)
        os.symlink("/etc/passwd", self.repo / "escape")
        git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "initial")
        self.evidence = Path(self.temp.name) / "evidence"
        self.adapter = LocalReadAdapter(self.repo, "HEAD", self.evidence, Path(self.temp.name))

    def read(self, path, run_id="run-p0", budget=64): return self.adapter.read(run_id, path, budget)

    def assert_no_leak(self, *values):
        text = json.dumps(values)
        for forbidden in (SECRET, str(self.repo), "adf-h3-01-"): self.assertNotIn(forbidden, text)

    def journals(self):
        return [json.loads(line) for path in sorted((self.evidence / "_attempts").glob("*.jsonl")) for line in path.read_text().splitlines()]

    def host_policy(self, run_id="run-host", budget=64):
        # The test host approves one exact path before any read intent exists.
        request = adapter_module.build_request({"snapshot_digest": "a" * 64}, run_id, "docs/readme.md", budget)
        config = {"schema_version": "1.0", **{key: request[key] for key in ("profiles", "policy", "context")}}
        target = Path(self.temp.name) / "host-policy.json"
        target.write_text(json.dumps(config))
        return target, adapter_module.digest(config), config

    def test_host_policy_is_pinned_and_never_expanded_by_the_intent(self):
        target, fingerprint, config = self.host_policy()
        adapter = LocalReadAdapter(self.repo, "HEAD", self.evidence, Path(self.temp.name), host_policy_path=target, host_policy_sha256=fingerprint)
        delivered = adapter.read("run-host", "docs/readme.md", 64)
        bundle = json.loads(Path(delivered["bundle_path"]).read_text())
        self.assertEqual(delivered["content"], PUBLIC)
        self.assertEqual((bundle["profile_sha256"], bundle["policy_sha256"]), (config["profiles"][0]["profile_sha256"], config["policy"]["policy_sha256"]))
        with patch.object(LocalReadRuntime, "read", side_effect=AssertionError("host denial must not read")):
            for run_id, path, budget, reason in (("run-host", "big.txt", 64, "scope_not_allowlisted"), ("other-run", "docs/readme.md", 64, "run_binding_mismatch"), ("run-host", "docs/readme.md", 65, "budget_exceeds_ceiling")):
                result = adapter.read(run_id, path, budget)
                self.assertEqual((result["outcome"], result["reason_code"]), ("deny", reason)); self.assertNotIn("content", result)
        target.write_text("{}")
        self.assertEqual(adapter.read("run-host", "docs/readme.md", 64)["content"], PUBLIC, "one adapter retains its host-approved artifacts")
        with patch.object(adapter_module.WorkspaceManager, "prepare", side_effect=AssertionError("changed policy must not prepare")):
            changed = LocalReadAdapter(self.repo, "HEAD", self.evidence, host_policy_path=target, host_policy_sha256=fingerprint).read("run-host", "docs/readme.md", 64)
        self.assertEqual(changed["reason_code"], "host_policy_invalid"); self.assertNotIn("content", changed)

    def test_invalid_host_policy_never_falls_back_to_demonstration(self):
        target, fingerprint, config = self.host_policy()
        cases = [(None, fingerprint), (target, None), (target, "0" * 64), (Path("relative.json"), fingerprint)]
        for key, value in (("schema_version", "2.0"), ("content", SECRET)):
            invalid = copy.deepcopy(config); invalid[key] = value
            broken = Path(self.temp.name) / (key + ".json"); broken.write_text(json.dumps(invalid))
            cases.append((broken, adapter_module.digest(invalid)))
        invalid = copy.deepcopy(config); invalid["policy"]["rules"][0]["max_output_bytes"] = 1000
        broken = Path(self.temp.name) / "bad-inner-hash.json"; broken.write_text(json.dumps(invalid))
        cases.append((broken, adapter_module.digest(invalid)))
        for key, field in (("profiles", "profile_sha256"), ("policy", "policy_sha256"), ("context", None)):
            invalid = copy.deepcopy(config)
            artifact = invalid[key][0] if key == "profiles" else invalid[key]
            artifact["unexpected"] = SECRET
            if field is not None: adapter_module._rehash(artifact, field)
            broken = Path(self.temp.name) / (key + "-bad-schema.json"); broken.write_text(json.dumps(invalid))
            cases.append((broken, adapter_module.digest(invalid)))
        with patch.object(adapter_module.WorkspaceManager, "prepare", side_effect=AssertionError("invalid policy must not prepare")):
            for path, pin in cases:
                result = LocalReadAdapter(self.repo, "HEAD", self.evidence, host_policy_path=path, host_policy_sha256=pin).read("run-host", "docs/readme.md", 64)
                self.assertEqual((result["outcome"], result["reason_code"]), ("deny", "host_policy_invalid")); self.assertNotIn("content", result)
        self.assert_no_leak(self.journals())
        self.assertEqual(self.read("docs/readme.md")["outcome"], "delivered", "no configuration preserves the reference demo")

    def test_both_gates_take_policy_only_from_the_host(self):
        target, fingerprint, _ = self.host_policy()
        env = {"ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_EVIDENCE_DIR": str(self.evidence), "ADF_MAX_OUTPUT_BYTES": "64", "ADF_READ_POLICY_FILE": str(target), "ADF_READ_POLICY_SHA256": fingerprint}
        for module, tool_name, input_key in ((gate, "Read", "file_path"), (codex_gate, "Bash", "command")):
            def payload(path):
                argument = str(self.repo / path)
                return {"hook_event_name": "PreToolUse", "tool_name": tool_name, "session_id": "run-host", "host_policy_path": "/invalid", "host_policy_sha256": "0" * 64, "tool_input": {input_key: "cat " + argument if tool_name == "Bash" else argument}}
            with patch.dict(os.environ, env, clear=True):
                allowed = module.gate(payload("docs/readme.md"))
                self.assertTrue(allowed == {} or allowed["hookSpecificOutput"]["permissionDecision"] == "allow")
                denied = module.gate(payload("big.txt"))["hookSpecificOutput"]
                self.assertEqual(denied["permissionDecision"], "deny"); self.assertIn("scope_not_allowlisted", denied["permissionDecisionReason"])
                injected = payload("docs/readme.md"); injected["tool_input"]["host_policy_path"] = str(target)
                self.assertIn("unexpected_tool_input", module.gate(injected)["hookSpecificOutput"]["permissionDecisionReason"])
            with patch.dict(os.environ, {**env, "ADF_READ_POLICY_SHA256": "0" * 64}, clear=True):
                denied = module.gate(payload("docs/readme.md"))["hookSpecificOutput"]
                self.assertEqual(denied["permissionDecision"], "deny"); self.assertIn("host_policy_invalid", denied["permissionDecisionReason"])

    def test_mcp_tool_delivers_snapshot_bytes_with_the_same_receipt_hash(self):
        from mcp import Client
        from integration.mcp_read_server import mcp
        target, fingerprint, _ = self.host_policy()
        env = {"ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_EVIDENCE_DIR": str(self.evidence), "ADF_TRUSTED_REVISION": "HEAD", "ADF_MAX_OUTPUT_BYTES": "64", "ADF_RUN_ID": "run-host", "ADF_READ_POLICY_FILE": str(target), "ADF_READ_POLICY_SHA256": fingerprint}
        (self.repo / "docs/readme.md").write_text("uncommitted-" + SECRET)

        async def exercise():
            async with Client(mcp) as client:
                delivered = await client.call_tool("read_snapshot", {"path": "docs/readme.md"})
                self.assertFalse(delivered.is_error)
                self.assertEqual(delivered.content[0].text, PUBLIC, "model-visible bytes come from the authorized snapshot")
                bundle_file, = (self.evidence / "run-host").glob("*.json")
                bundle = json.loads(bundle_file.read_text())
                self.assertEqual(hashlib.sha256(delivered.content[0].text.encode()).hexdigest(), bundle["receipt"]["content_sha256"])
                self.assertEqual(len(delivered.content[0].text.encode()), bundle["receipt"]["bytes_read"])
                denied = await client.call_tool("read_snapshot", {"path": "secrets/token"})
                self.assertTrue(denied.is_error)
                self.assertIn("scope_not_allowlisted", denied.content[0].text)
                self.assertNotIn(SECRET, denied.content[0].text)
                with patch("integration.mcp_read_server.verify_offline", return_value=False):
                    invalid = await client.call_tool("read_snapshot", {"path": "docs/readme.md"})
                self.assertTrue(invalid.is_error)
                self.assertIn("evidence_bundle_invalid", invalid.content[0].text)
                self.assertNotIn(PUBLIC, invalid.content[0].text)
        with patch.dict(os.environ, env, clear=True): asyncio.run(exercise())

        async def missing_host():
            async with Client(mcp) as client:
                result = await client.call_tool("read_snapshot", {"path": "docs/readme.md"})
                self.assertTrue(result.is_error)
                self.assertIn("host_configuration_invalid", result.content[0].text)
        for missing in ("ADF_TRUSTED_REVISION", "ADF_MAX_OUTPUT_BYTES", "ADF_READ_POLICY_FILE"):
            with self.subTest(missing=missing), patch.dict(os.environ, {key: value for key, value in env.items() if key != missing}, clear=True):
                asyncio.run(missing_host())

    def test_mcp_stdio_delivers_the_same_snapshot_text(self):
        from mcp import Client, StdioServerParameters
        target, fingerprint, _ = self.host_policy()
        env = {**os.environ, "ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_EVIDENCE_DIR": str(self.evidence), "ADF_TRUSTED_REVISION": "HEAD", "ADF_MAX_OUTPUT_BYTES": "64", "ADF_RUN_ID": "run-host", "ADF_READ_POLICY_FILE": str(target), "ADF_READ_POLICY_SHA256": fingerprint, "ADF_CAPTURE_TIMINGS": "1"}
        params = StdioServerParameters(command=str(Path(sys.executable).parent / "mcp"), args=["run", str(ROOT / "integration/mcp_read_server.py") + ":mcp", "--transport", "stdio"], cwd=str(ROOT.parent), env=env)

        async def exercise():
            async with Client(params) as client:
                tools = await client.list_tools()
                self.assertEqual([tool.name for tool in tools.tools], ["read_snapshot"])
                delivered = await client.call_tool("read_snapshot", {"path": "docs/readme.md"})
                self.assertFalse(delivered.is_error)
                self.assertEqual(delivered.content[0].text, PUBLIC)
                bundle_file, = (self.evidence / "run-host").glob("*.json")
                bundle = json.loads(bundle_file.read_text())
                self.assertEqual(hashlib.sha256(delivered.content[0].text.encode()).hexdigest(), bundle["receipt"]["content_sha256"])
        asyncio.run(exercise())

        from integration.attempt_timing import verify_timing
        timing_file, = (self.evidence / "_timings").glob("*.json")
        timing = json.loads(timing_file.read_text())
        self.assertTrue(verify_timing(timing))
        self.assertEqual(timing["run_id"], "run-host")
        self.assertTrue(all(value is not None for value in timing["durations_ms"].values()))

    def test_attempts_record_pre_admission_denials_without_raw_inputs(self):
        for run_id, path, budget in (("denied", "docs/../secrets/token", 64), ("bad-id/" + SECRET, "docs/readme.md", 64), ("bad-budget", "docs/readme.md", SECRET)):
            with patch.object(LocalReadRuntime, "read", side_effect=AssertionError("denied attempts must not read")):
                result = self.read(path, run_id, budget)
            self.assertEqual(result["outcome"], "deny")
        events = self.journals()
        self.assertEqual(len(events), 6, "every rejected adapter attempt needs start and completion")
        self.assertEqual({event["payload"]["reason_code"] for event in events if event["phase"] == "completed"}, {"invalid_referenced_contract", "invalid_run_id", "invalid_budget"})
        self.assert_no_leak(events)
        self.assertNotIn("secrets/token", json.dumps(events))
        self.assertFalse(list(self.evidence.rglob("*.json")), "denial journals are not fabricated bundles")

    def test_attempt_completion_records_cleanup_and_bundle_identity(self):
        from integration.adapter_attempt import verify_attempt
        result = self.read("docs/readme.md")
        events = self.journals()
        self.assertEqual(verify_attempt(events, adapter_module.schemas()["adapter_attempt_event"]), "complete")
        self.assertEqual(events[1]["payload"], {"outcome": "delivered", "reason_code": "read_delivered", "bundle_id": result["bundle_id"], "cleanup_outcome": "succeeded"})
        self.assertNotIn(PUBLIC, json.dumps(events)); self.assert_no_leak(events)
        with patch.object(adapter_module.WorkspaceManager, "cleanup", return_value=False):
            denied = self.read("docs/readme.md", "cleanup-failed")
        completed = next(event for event in self.journals() if event["run_id"] == "cleanup-failed" and event["phase"] == "completed")
        self.assertEqual(completed["payload"], {"outcome": "deny", "reason_code": "workspace_worktree_cleanup_failed", "bundle_id": denied["bundle_id"], "cleanup_outcome": "failed"})
        self.assertNotIn("content", denied)

    def test_attempt_persistence_failures_never_deliver_and_interruption_is_incomplete(self):
        from integration.adapter_attempt import AttemptJournal, verify_attempt
        with patch.object(AttemptJournal, "finish", side_effect=OSError(SECRET)):
            result = self.read("docs/readme.md", "finish-failed")
        self.assertEqual((result["outcome"], result["reason_code"]), ("deny", "attempt_evidence_failed")); self.assertNotIn("content", result)
        start = next(event for event in self.journals() if event["run_id"] == "finish-failed")
        schema = adapter_module.schemas()["adapter_attempt_event"]
        self.assertEqual(verify_attempt([start], schema), "incomplete")
        with patch.object(adapter_module, "persist_bundle", side_effect=OSError(SECRET)):
            result = self.read("docs/readme.md", "bundle-failed")
        end = next(event for event in self.journals() if event["run_id"] == "bundle-failed" and event["phase"] == "completed")
        self.assertEqual((end["payload"]["outcome"], end["payload"]["reason_code"], end["payload"]["cleanup_outcome"]), ("deny", "adapter_failed", "succeeded"))
        original_cleanup = adapter_module.WorkspaceManager.cleanup
        with patch.object(adapter_module, "compose", side_effect=KeyboardInterrupt), patch.object(adapter_module.WorkspaceManager, "cleanup", autospec=True, side_effect=original_cleanup) as cleanup:
            with self.assertRaises(KeyboardInterrupt): self.read("docs/readme.md", "interrupted")
            self.assertEqual(cleanup.call_count, 1)
        interrupted = [event for event in self.journals() if event["run_id"] == "interrupted"]
        self.assertEqual(verify_attempt(interrupted, schema), "incomplete"); self.assert_no_leak(self.journals())

    def test_attempt_contract_and_verifier_reject_tampering_duplicates_and_false_success(self):
        from integration.adapter_attempt import event_digest, verify_attempt
        from jsonschema import Draft7Validator
        self.read("docs/readme.md")
        events, schema = self.journals(), adapter_module.schemas()["adapter_attempt_event"]
        Draft7Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), {"schema_version", "canonicalization", "attempt_id", "adapter_id", "run_id", "phase", "timestamp", "previous_event_sha256", "event_sha256", "payload"})
        self.assertEqual(schema["properties"]["phase"]["enum"], ["started", "completed"])
        self.assertEqual(schema["properties"]["schema_version"], {"const": "1.0"})
        self.assertEqual(verify_attempt(events, schema), "complete")
        self.assertEqual(verify_attempt([], schema), "invalid")
        self.assertEqual(verify_attempt(events + [events[1]], schema), "invalid")
        self.assertEqual(verify_attempt(list(reversed(events)), schema), "invalid")
        self.assertEqual(verify_attempt(events, {"type": "invalid-type"}), "invalid")
        self.assertEqual(verify_attempt(events, {"$ref": "https://agent-flow.invalid/not-local"}), "invalid")
        for key, value in (("attempt_id", "f" * 32), ("run_id", "another-run"), ("previous_event_sha256", "0" * 64), ("schema_version", "2.0"), ("content", SECRET)):
            changed = copy.deepcopy(events); changed[1][key] = value
            changed[1]["event_sha256"] = event_digest(changed[1])
            self.assertEqual(verify_attempt(changed, schema), "invalid", key)
        for key, value in (("cleanup_outcome", "failed"), ("cleanup_outcome", "not_attempted"), ("bundle_id", None), ("reason_code", SECRET), ("reason_code", "adapter_failed"), ("content", SECRET)):
            changed = copy.deepcopy(events); changed[1]["payload"][key] = value
            changed[1]["event_sha256"] = event_digest(changed[1])
            self.assertEqual(verify_attempt(changed, schema), "invalid", key)
        changed = copy.deepcopy(events); changed[1]["payload"]["outcome"] = "deny"
        self.assertEqual(verify_attempt(changed, schema), "invalid", "unrehashed tampering")
        changed = copy.deepcopy(events); changed[1]["timestamp"] = "2000-01-01T00:00:00Z"
        self.assertTrue(Draft7Validator(schema).is_valid(changed[1]))
        self.assertEqual(verify_attempt(changed, schema), "invalid", "schema-valid tampering still requires digest verification")

    def test_attempt_storage_refuses_symlinks_collisions_and_replacement_before_effect(self):
        from integration.adapter_attempt import AttemptJournal
        schema = adapter_module.schemas()["adapter_attempt_event"]
        journal = AttemptJournal(self.evidence, "storage", schema)
        try:
            target = self.evidence / "_attempts" / journal._name
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
            with patch("integration.adapter_attempt.uuid.uuid4", return_value=SimpleNamespace(hex=journal._start["attempt_id"])):
                with self.assertRaises(FileExistsError): AttemptJournal(self.evidence, "storage", schema)
            outcome = adapter_module._result("deny", "invalid_scope")
            journal.finish(outcome)
            with self.assertRaises(ValueError): journal.finish(outcome)
        finally: journal.close()
        linked = Path(self.temp.name) / "linked-evidence"; os.symlink(self.evidence, linked)
        with patch.object(LocalReadRuntime, "read", side_effect=AssertionError("no effect without a journal")):
            result = LocalReadAdapter(self.repo, "HEAD", linked).read("storage", "docs/readme.md", 64)
        self.assertEqual(result["reason_code"], "attempt_evidence_failed"); self.assertNotIn("content", result)
        child_link = Path(self.temp.name) / "child-link"; child_link.mkdir()
        os.symlink(self.evidence / "_attempts", child_link / "_attempts")
        with patch.object(adapter_module.WorkspaceManager, "prepare") as prepare:
            result = LocalReadAdapter(self.repo, "HEAD", child_link).read("storage", "docs/readme.md", 64)
        self.assertEqual(result["reason_code"], "attempt_evidence_failed"); prepare.assert_not_called()
        replaced = AttemptJournal(self.evidence, "replacement", schema)
        try:
            target = self.evidence / "_attempts" / replaced._name
            target.rename(target.with_suffix(".original")); target.write_text("replacement")
            with self.assertRaises(OSError): replaced.finish(outcome)
            self.assertEqual(target.read_text(), "replacement")
        finally: replaced.close()

    def test_attempt_fsync_failure_preserves_only_the_start_and_never_delivers(self):
        from integration.adapter_attempt import verify_attempt
        with patch("integration.adapter_attempt.os.fsync", side_effect=[None, OSError(SECRET)]):
            result = self.read("docs/readme.md", "sync-failed")
        self.assertEqual((result["outcome"], result["reason_code"]), ("deny", "attempt_evidence_failed")); self.assertNotIn("content", result)
        self.assertEqual(verify_attempt(self.journals(), adapter_module.schemas()["adapter_attempt_event"]), "incomplete")
        with patch("integration.adapter_attempt.os.fsync", side_effect=OSError(SECRET)), patch.object(adapter_module.WorkspaceManager, "prepare") as prepare:
            result = self.read("docs/readme.md", "start-failed")
        self.assertEqual(result["reason_code"], "attempt_evidence_failed"); prepare.assert_not_called()
        self.assert_no_leak(self.journals())

    def test_failed_sync_and_rollback_never_deliver_but_completion_is_not_an_ack(self):
        from integration.adapter_attempt import verify_attempt
        with patch("integration.adapter_attempt.os.fsync", side_effect=[None, OSError(SECRET)]), patch("integration.adapter_attempt.os.ftruncate", side_effect=OSError(SECRET)):
            result = self.read("docs/readme.md", "rollback-failed")
        self.assertEqual((result["outcome"], result["reason_code"]), ("deny", "attempt_evidence_failed")); self.assertNotIn("content", result)
        events = self.journals()
        self.assertEqual(verify_attempt(events, adapter_module.schemas()["adapter_attempt_event"]), "complete")
        self.assertEqual(events[1]["payload"]["outcome"], "delivered", "this is the calculated result before persistence, not a harness acknowledgement")
        self.assert_no_leak(events)

    def test_happy_path_delivers_tainted_content_and_verifiable_bundle(self):
        result = self.read("docs/readme.md")
        self.assertEqual((result["outcome"], result["reason_code"], result["content"]), ("delivered", "read_delivered", PUBLIC))
        self.assertEqual(result["taint"], {"classification": "untrusted_workspace_file", "cannot_authorize": True})
        bundle_path = Path(result["bundle_path"]); self.assertEqual(bundle_path.parent, self.evidence / "run-p0")
        self.assertEqual(stat.S_IMODE(self.evidence.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(bundle_path.stat().st_mode), 0o600)
        bundle = json.loads(bundle_path.read_text())
        self.assertTrue(verify_offline(bundle, adapter_module.schemas())); self.assertFalse(is_authorization(bundle))
        self.assertEqual(bundle["bundle_id"], result["bundle_id"])
        self.assertNotIn(PUBLIC, bundle_path.read_text()); self.assert_no_leak(bundle)
        self.assertTrue(set(result) <= {"adapter_id", "outcome", "reason_code", "taint", "bundle_id", "bundle_path", "decision_latency_ms", "content"})

    def test_denies_never_reach_the_runtime(self):
        with patch.object(LocalReadRuntime, "read", side_effect=AssertionError("runtime must not run")):
            cases = {"/etc/passwd": "invalid_scope", "": "invalid_scope", "docs/readme.md\x00": "invalid_scope", "docs/../secrets/token": "invalid_referenced_contract", ".env": "invalid_referenced_contract", "docs//readme.md": "invalid_referenced_contract"}
            for path, code in cases.items():
                result = self.read(path); self.assertEqual((result["outcome"], result["reason_code"]), ("deny", code), path); self.assertNotIn("content", result)
            self.assertEqual(self.read("docs/readme.md", run_id="../x")["reason_code"], "invalid_run_id")
            self.assertEqual(self.read("docs/readme.md", budget="64")["reason_code"], "invalid_budget")
            self.assertFalse(list(self.evidence.rglob("*.json")), "contract-level denies produce no bundle")

    def test_sensitive_symlink_directory_and_oversize_are_denied_without_content(self):
        expected = {"secrets/token": "sensitive_path_denied", "escape": "safe_open_failed", "docs": "unsafe_file_type", "big.txt": "output_limit_exceeded", "missing.md": "safe_open_failed"}
        for path, code in expected.items():
            result = self.read(path)
            self.assertEqual((result["outcome"], result["reason_code"]), ("deny", code), path); self.assertNotIn("content", result)
            self.assertTrue(verify_offline(json.loads(Path(result["bundle_path"]).read_text()), adapter_module.schemas()))
            self.assert_no_leak(result)

    def test_binding_mismatch_denies_before_and_at_effect(self):
        original = adapter_module.build_request
        def wrong_run(*args, **kwargs): request = original(*args, **kwargs); request["context"]["resolved_run_config_ref"]["run_id"] = "other-run"; return request
        def wrong_snapshot(*args, **kwargs): request = original(*args, **kwargs); request["intent"]["task_ref"] = "0" * 64; return request
        with patch.object(adapter_module, "build_request", wrong_run): pdp = self.read("docs/readme.md")
        with patch.object(adapter_module, "build_request", wrong_snapshot), patch.object(LocalReadRuntime, "read", side_effect=AssertionError("no read on mismatch")): pep = self.read("docs/readme.md")
        self.assertEqual((pdp["outcome"], pdp["reason_code"]), ("deny", "run_binding_mismatch")); self.assertTrue(Path(pdp["bundle_path"]).is_file())
        self.assertEqual((pep["outcome"], pep["reason_code"]), ("deny", "task_ref_mismatch"))
        self.assertNotIn("content", pdp); self.assertNotIn("content", pep)

    def test_cleanup_failure_withdraws_content_and_workspace_failures_are_redacted(self):
        with patch.object(adapter_module.WorkspaceManager, "cleanup", return_value=False): result = self.read("docs/readme.md")
        self.assertEqual((result["outcome"], result["reason_code"]), ("deny", "workspace_worktree_cleanup_failed")); self.assertNotIn("content", result)
        broken = LocalReadAdapter(self.repo, "no-such-revision", self.evidence, Path(self.temp.name)).read("run-broken", "docs/readme.md", 64)
        self.assertEqual((broken["outcome"], broken["reason_code"]), ("deny", "workspace_revision_unavailable")); self.assert_no_leak(broken)
        self.assertFalse((self.evidence / "run-broken").exists())

    def test_consumed_decision_and_bundle_never_grant_a_second_read(self):
        captured = []
        original = adapter_module.PolicyEnforcementPoint.enforce_read
        def capture(pep, *args): captured.append(args); return original(pep, *args)
        with patch.object(adapter_module.PolicyEnforcementPoint, "enforce_read", capture): first = self.read("docs/readme.md")
        self.assertEqual(first["outcome"], "delivered"); self.assertEqual(len(captured), 1)
        decision, intent, profile, policy, context, descriptor = captured[0]
        # Replaying the consumed admission against a fresh, trusted PEP: the workspace is gone, runtime never runs.
        manager = adapter_module.WorkspaceManager(self.repo, "HEAD", Path(self.temp.name))
        with patch.object(LocalReadRuntime, "read", side_effect=AssertionError("replay must not read")):
            result, receipt = adapter_module.PolicyEnforcementPoint(manager, LocalReadRuntime(self.adapter._sensitive)).enforce_read(decision, intent, profile, policy, context, descriptor)
        self.assertEqual((result["outcome"], result["reason_code"]), ("deny", "workspace_binding_mismatch")); self.assertNotIn("content", result)
        # The persisted bundle is evidence only; a second read needs a fresh decision, workspace and bundle.
        bundle = json.loads(Path(first["bundle_path"]).read_text()); self.assertFalse(is_authorization(bundle))
        second = self.read("docs/readme.md")
        self.assertEqual(second["outcome"], "delivered"); self.assertNotEqual(second["bundle_id"], first["bundle_id"])
        self.assertNotEqual(json.loads(Path(second["bundle_path"]).read_text())["workspace_id"], bundle["workspace_id"])
        self.assertEqual(len(list((self.evidence / "run-p0").glob("*.json"))), 2, "bundles are never overwritten")

    def test_source_boundaries(self):
        for name in ("integration/local_read_adapter.py", "hooks/claude-code-read-gate.py"):
            source = (ROOT / name).read_text().lower()
            for forbidden in ("import subprocess", "from subprocess", "socket", "urllib", "http.client", "requests", "docker", "mcp", "shell", "sys.argv"):
                self.assertNotIn(forbidden, source, f"{name}: {forbidden}")
        self.assertNotIn("environ", (ROOT / "integration/local_read_adapter.py").read_text().lower())

    def test_gate_maps_payloads_and_fails_closed(self):
        def run(payload):
            with patch.dict(os.environ, {"ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_TRUSTED_REVISION": "HEAD", "ADF_EVIDENCE_DIR": str(self.evidence), "ADF_MAX_OUTPUT_BYTES": "64"}):
                return gate.gate(payload)["hookSpecificOutput"]
        base = {"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": "sess-1", "tool_input": {"file_path": str(self.repo / "docs/readme.md")}}
        allowed = run(base)
        self.assertEqual(allowed["permissionDecision"], "allow"); self.assertIn("delivered/read_delivered bundle=", allowed["permissionDecisionReason"]); self.assertNotIn(PUBLIC, json.dumps(allowed))
        denials = {
            "path_outside_trusted_root": {**base, "tool_input": {"file_path": "/etc/passwd"}},
            "deny/invalid_referenced_contract": {**base, "tool_input": {"file_path": str(self.repo / "docs/../secrets/token")}},
            "deny/sensitive_path_denied": {**base, "tool_input": {"file_path": str(self.repo / "secrets/token")}},
            "unexpected_tool_input": {**base, "tool_input": {"file_path": str(self.repo / "docs/readme.md"), "command": "cat"}},
            "unsupported_tool": {**base, "tool_name": "Bash"},
            "deny/invalid_run_id": {**base, "session_id": None},
            "path_outside_trusted_root (relative)": {**base, "tool_input": {"file_path": "docs/readme.md"}},
        }
        for code, payload in denials.items():
            output = run(payload); self.assertEqual(output["permissionDecision"], "deny", code); self.assertIn(code.split(" ")[0], output["permissionDecisionReason"]); self.assert_no_leak(output)
        process = subprocess.run([sys.executable, str(ROOT / "hooks/claude-code-read-gate.py")], input="not json", text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual((process.returncode, json.loads(process.stdout)["hookSpecificOutput"]["permissionDecision"]), (0, "deny")); self.assertIn("adapter_failed", process.stdout)

    def test_gate_host_settings_are_required_for_other_projects(self):
        base = {"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": "sess-host", "tool_input": {"file_path": str(self.repo / "docs/readme.md")}}
        bad_evidence = Path(self.temp.name) / "evidence-file"
        bad_evidence.write_text("not a directory")
        with patch.dict(os.environ, {"PATH": os.environ.get("PATH", ""), "CLAUDE_PROJECT_DIR": str(ROOT.parent)}, clear=True):
            self.assertEqual(gate._host_settings()[:3], (ROOT.parent, "HEAD", ROOT / "docs/observability/evidence"))
        for env in (
            {"CLAUDE_PROJECT_DIR": str(self.repo)},
            {"ADF_TRUSTED_REPOSITORY": "relative", "ADF_EVIDENCE_DIR": str(self.evidence)},
            {"ADF_TRUSTED_REPOSITORY": str(self.evidence), "ADF_EVIDENCE_DIR": str(self.evidence)},
            {"ADF_TRUSTED_REPOSITORY": str(self.repo / "big.txt"), "ADF_EVIDENCE_DIR": str(self.evidence)},
            {"ADF_TRUSTED_REPOSITORY": str(self.repo)},
            {"ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_EVIDENCE_DIR": "relative"},
            {"ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_EVIDENCE_DIR": str(bad_evidence)},
            {"ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_EVIDENCE_DIR": str(self.evidence), "ADF_MAX_OUTPUT_BYTES": "bad"},
            {"ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_EVIDENCE_DIR": str(self.evidence), "ADF_TRUSTED_REVISION": ""},
        ):
            with self.subTest(env=env), patch.dict(os.environ, {"PATH": os.environ.get("PATH", ""), **env}, clear=True):
                with patch.object(gate.LocalReadAdapter, "read", side_effect=AssertionError("no read with invalid host settings")):
                    result = gate.gate(base)["hookSpecificOutput"]
                self.assertEqual(result["permissionDecision"], "deny")
                self.assertIn("host_configuration_invalid", result["permissionDecisionReason"])

    def test_gate_uses_only_host_root_revision_evidence_and_budget(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": "sess-alt", "trusted_repository": str(ROOT.parent), "trusted_revision": "bad", "evidence_dir": str(ROOT), "tool_input": {"file_path": str(self.repo / "docs/readme.md")}}
        env = {"PATH": os.environ.get("PATH", ""), "ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_EVIDENCE_DIR": str(self.evidence), "ADF_MAX_OUTPUT_BYTES": "64"}
        with patch.dict(os.environ, env, clear=True):
            result = gate.gate(payload)["hookSpecificOutput"]
            self.assertEqual(result["permissionDecision"], "allow")
            self.assertTrue(list((self.evidence / "sess-alt").glob("*.json")))
            outside = {**payload, "tool_input": {"file_path": str(ROOT.parent / "README.md")}}
            self.assertEqual(gate.gate(outside)["hookSpecificOutput"]["permissionDecision"], "deny")
            injected = {**payload, "tool_input": {**payload["tool_input"], "trusted_repository": str(ROOT.parent)}}
            self.assertIn("unexpected_tool_input", gate.gate(injected)["hookSpecificOutput"]["permissionDecisionReason"])
        with patch.dict(os.environ, {**env, "ADF_TRUSTED_REVISION": "no-such-revision"}, clear=True):
            self.assertIn("workspace_revision_unavailable", gate.gate(payload)["hookSpecificOutput"]["permissionDecisionReason"])
        with patch.dict(os.environ, {**env, "ADF_MAX_OUTPUT_BYTES": "4"}, clear=True):
            self.assertIn("output_limit_exceeded", gate.gate(payload)["hookSpecificOutput"]["permissionDecisionReason"])


if __name__ == "__main__": unittest.main(verbosity=2)
