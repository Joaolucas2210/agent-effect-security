"""Negative-first checks for the A2A edge (ADRs 0013/0014): AuthN, scopes, PDP, PEP, evidence."""
import base64
import contextlib
import copy
import hashlib
import hmac
import io
import json
import os
import secrets
import stat
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft7Validator

import integration.a2a_gateway as a2a
import integration.local_read_adapter as adapter_module
import runtime.pep as pep_module
from runtime.local_read_runtime import LocalReadRuntime
from runtime.pep import PolicyEnforcementPoint
from tools.pdp import decide


ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "integration/v1/schemas"
ISSUER, AUDIENCE, APPROVED = "https://idp.test.invalid", "adf-a2a-local", "docs/readme.md"
PUBLIC, SECRET = "allowed-public-content", "conteudo-secreto-do-arquivo"


def b64(raw): return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def forge(header, claims, secret):
    signing = f"{b64(json.dumps(header).encode())}.{b64(json.dumps(claims).encode())}"
    return f"{signing}.{b64(hmac.new(secret, signing.encode(), hashlib.sha256).digest())}"


def send(skill="read_workspace_file", path=APPROVED, **extra):
    data = {"skill": skill, "arguments": {"path": path}}
    body = {"jsonrpc": "2.0", "id": "r1", "method": "message/send", "params": {"message": {"kind": "message", "role": "user", "messageId": "m1", "parts": [{"kind": "data", "data": data}]}}}
    body.update(extra)
    return json.dumps(body).encode()


class A2AGatewayTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.repo = (Path(self.temp.name) / "source"); self.repo.mkdir(); self.repo = self.repo.resolve()
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "a2a@example.invalid"); git(self.repo, "config", "user.name", "A2A")
        (self.repo / "docs").mkdir(); (self.repo / "docs/readme.md").write_text(PUBLIC); (self.repo / "docs/other.md").write_text(SECRET)
        git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "initial")
        self.evidence = Path(self.temp.name) / "evidence"
        self.secret = secrets.token_bytes(32)
        # The test host pins one approved path before any A2A request exists (ADR 0011).
        request = adapter_module.build_request({"snapshot_digest": "a" * 64}, "run-a2a", APPROVED, 64)
        config = {"schema_version": "1.0", **{key: request[key] for key in ("profiles", "policy", "context")}}
        self.policy = Path(self.temp.name) / "host-policy.json"; self.policy.write_text(json.dumps(config))
        self.fingerprint = adapter_module.digest(config)
        self.schemas = adapter_module.schemas()
        self.gateway = self.make()

    def make(self, **overrides):
        options = {"validator": a2a.HS256TokenValidator(self.secret, ISSUER, AUDIENCE), "trusted_repository": self.repo, "trusted_revision": "HEAD", "evidence_dir": self.evidence, "host_policy_path": str(self.policy), "host_policy_sha256": self.fingerprint, "max_output_bytes": 64, "port": 8765, "workspace_parent": Path(self.temp.name)}
        options.update(overrides)
        return a2a.A2AGateway(**options)

    def claims(self, **overrides):
        claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": "agent-alpha", "exp": int(time.time()) + 300, "scope": "workspace:read"}
        claims.update(overrides)
        return {key: value for key, value in claims.items() if value is not None}

    def token(self, **overrides): return a2a.mint_hs256(self.claims(**overrides), self.secret)

    def principal(self, **overrides):
        return {"schema_version": "1.0", "sub": "agent-alpha", "scopes": ["workspace:read"], "act": [], "token_aud": AUDIENCE, "authn_method": "bearer_jwt_hs256", "expires_at": int(time.time()) + 300, **overrides}

    def call(self, body=None, token="default", gateway=None):
        token = self.token() if token == "default" else token
        header = None if token is None else f"Bearer {token}"
        return (gateway or self.gateway).handle(header, send() if body is None else body)

    def reason(self, status, payload): return status, payload["error"]["data"]["reason_code"]

    def records(self): return [json.loads(path.read_text()) for path in sorted((self.evidence / "_a2a").glob("*.json"))] if (self.evidence / "_a2a").exists() else []

    def bundle(self, bundle_id): return json.loads(next(self.evidence.glob(f"*/{bundle_id}.json")).read_text())

    def assert_denied_before_adapter(self, expected_status, expected_reason, **kwargs):
        with patch.object(adapter_module.LocalReadAdapter, "read", side_effect=AssertionError("adapter must not run")), \
             patch.object(adapter_module, "decide", side_effect=AssertionError("PDP must not run")):
            self.assertEqual(self.reason(*self.call(**kwargs)), (expected_status, expected_reason))

    # Layer 1: AuthN lives in the transport and fails closed before PDP, PEP and evidence.
    def test_authn_failures_never_reach_the_pdp(self):
        other = secrets.token_bytes(32)
        cases = {
            "auth_missing": None,
            "token_malformed": "not-a-jwt",
            "token_signature_invalid": a2a.mint_hs256(self.claims(), other),
            "token_alg_rejected": forge({"alg": "none", "typ": "JWT"}, self.claims(), self.secret),
            "token_expired": self.token(exp=int(time.time()) - 1),
            "token_audience_invalid": self.token(aud="some-other-agent"),
            "token_issuer_invalid": self.token(iss="https://evil.invalid"),
            "token_claims_invalid": self.token(sub=None),
            "token_not_yet_valid": self.token(nbf=int(time.time()) + 600),
            "token_lifetime_exceeded": self.token(exp=int(time.time()) + a2a.MAX_TOKEN_LIFETIME_SECONDS + 60),
        }
        for reason, token in cases.items():
            with self.subTest(reason=reason):
                self.assert_denied_before_adapter(401, reason, token=token)
        self.assert_denied_before_adapter(401, "token_audience_invalid", token=self.token(aud=[AUDIENCE, "next-agent"]))
        self.assert_denied_before_adapter(401, "token_claims_invalid", token=self.token(scope="ok " + "x" * 80))
        self.assertEqual(self.reason(*self.gateway.handle("Basic dXNlcjpwYXNz", send())), (401, "auth_missing"))
        self.assertEqual(self.records(), [])  # no identity, no record; only the credential-free log line

    def test_credentials_in_the_json_rpc_body_are_rejected(self):
        token = self.token()
        leaks = [send(path=f"{token}"), send(authorization=f"Bearer {token}"), send(path="docs/x", token="abc")]
        for body in leaks:
            with self.subTest(body=body[:40]):
                self.assert_denied_before_adapter(400, "credential_in_payload", body=body)

    # Layer 2: per-skill scopes gate entry, and only the PDP admits.
    def test_unknown_skill_and_insufficient_scope_deny_before_the_pdp_with_a_record(self):
        self.assert_denied_before_adapter(403, "unknown_skill", body=send(skill="peticionar"))
        self.assert_denied_before_adapter(403, "insufficient_scope", token=self.token(scope="workspace:write"))
        self.assert_denied_before_adapter(403, "insufficient_scope", token=self.token(scope=None))
        self.assert_denied_before_adapter(403, "insufficient_scope", token=self.token(scope="workspace:readx"))
        records = self.records()
        self.assertEqual(sorted(item["reason_code"] for item in records), ["insufficient_scope"] * 3 + ["unknown_skill"])
        for record in records:
            self.assertTrue(a2a.verify_record(record, None, self.schemas))
            self.assertEqual((record["outcome"], record["decision_id"], record["bundle_id"]), ("deny", None, None))

    def test_scope_present_but_pdp_domain_policy_denies_without_reading(self):
        with patch.object(LocalReadRuntime, "read", side_effect=AssertionError("no read on deny")):
            status, payload = self.call(send(path="docs/other.md"))
        result = payload["result"]
        self.assertEqual((status, result["outcome"], result["reason_code"], result["effect"]), (200, "deny", "scope_not_allowlisted", "none"))
        self.assertNotIn("content", result); self.assertNotIn(SECRET, json.dumps(payload))
        [record] = self.records()
        self.assertTrue(a2a.verify_record(record, self.bundle(record["bundle_id"]), self.schemas))

    # A2A-3: admit goes through PEP + confined read; evidence is persisted and verifiable.
    def test_happy_path_reads_through_the_pep_and_persists_verifiable_evidence(self):
        token = self.token(act={"sub": "agent-beta", "act": {"sub": "user-carol"}})
        status, payload = self.call(token=token)
        result = payload["result"]
        self.assertEqual((status, result["outcome"], result["effect"], result["content"]), (200, "delivered", "read", PUBLIC))
        self.assertEqual(result["taint"], {"classification": "untrusted_workspace_file", "cannot_authorize": True})
        [record] = self.records()
        bundle = self.bundle(record["bundle_id"])
        self.assertTrue(a2a.verify_record(record, bundle, self.schemas))
        self.assertEqual(result["audit"], {"sub": "agent-alpha", "act": ["agent-beta", "user-carol"], "skill": "read_workspace_file", "outcome": "delivered", "reason_code": result["reason_code"], "decision_id": bundle["decision_id"], "bundle_id": bundle["bundle_id"], "record_id": record["record_id"]})
        self.assertEqual(record["principal"], {"schema_version": "1.0", "sub": "agent-alpha", "scopes": ["workspace:read"], "act": ["agent-beta", "user-carol"], "token_aud": AUDIENCE, "authn_method": "bearer_jwt_hs256", "expires_at": record["principal"]["expires_at"]})
        path = next((self.evidence / "_a2a").glob("*.json"))
        self.assertEqual((stat.S_IMODE(path.stat().st_mode), stat.S_IMODE(path.parent.stat().st_mode)), (0o600, 0o700))
        evidence_text = "".join(item.read_text() for item in self.evidence.rglob("*") if item.is_file())
        for leaked in (token, token.split(".")[1], token.split(".")[2], PUBLIC):
            self.assertNotIn(leaked, evidence_text)
        tampered = copy.deepcopy(record); tampered["principal"]["sub"] = "agent-mallory"
        self.assertFalse(a2a.verify_record(tampered, bundle, self.schemas))
        self.assertFalse(a2a.verify_record(record, None, self.schemas))
        self.assertFalse(adapter_module.verify_offline({**bundle, "decision_id": "f" * 64}, self.schemas))

    def test_pep_binding_mismatch_denies_without_reading(self):
        original = PolicyEnforcementPoint.enforce_read

        def tamper(pep, decision, intent, *rest, **kwargs):
            intent = copy.deepcopy(intent); intent["arguments"] = {"path": "docs/other.md"}; intent["resource_scope"] = {"kind": "filesystem", "path": "docs/other.md"}
            return original(pep, decision, intent, *rest, **kwargs)

        with patch.object(PolicyEnforcementPoint, "enforce_read", tamper), patch.object(LocalReadRuntime, "read", side_effect=AssertionError("no read")):
            status, payload = self.call()
        self.assertEqual(payload["result"]["outcome"], "deny"); self.assertNotIn("content", payload["result"])
        self.assertNotIn(SECRET, json.dumps(payload))

    def test_principal_is_revalidated_at_effect_time(self):
        later = type("Clock", (), {"time": staticmethod(lambda: time.time() + 3600)})
        with patch.object(pep_module, "time", later), patch.object(LocalReadRuntime, "read", side_effect=AssertionError("no read")):
            status, payload = self.call()
        self.assertEqual((payload["result"]["outcome"], payload["result"]["reason_code"]), ("deny", "principal_expired"))
        [record] = self.records()
        self.assertTrue(a2a.verify_record(record, self.bundle(record["bundle_id"]), self.schemas))

    # ADR 0016: auth-required when the credential lapses mid-task; resume = fresh admission, once.
    def expire_mid_task(self, token=None):
        later = type("Clock", (), {"time": staticmethod(lambda: time.time() + 3600)})
        with patch.object(pep_module, "time", later), patch.object(LocalReadRuntime, "read", side_effect=AssertionError("no read")):
            return self.call(token=token or self.token())[1]["result"]

    def resume(self, task_id, token=None, path=APPROVED):
        body = json.loads(send(path=path)); body["params"]["message"]["taskId"] = task_id
        return self.call(json.dumps(body).encode(), token=token or self.token())

    def test_lapsed_credential_yields_auth_required_and_resume_needs_a_new_admission(self):
        paused = self.expire_mid_task()
        task = paused["task"]
        self.assertEqual((paused["outcome"], paused["effect"], paused["reason_code"], task["status"]["state"]), ("deny", "none", "principal_expired", "auth-required"))
        self.assertNotIn("content", paused); self.assertRegex(task["id"], r"^[a-f0-9]{32}$")
        with patch.object(adapter_module, "decide", wraps=adapter_module.decide) as pdp:
            status, payload = self.resume(task["id"])
        result = payload["result"]
        self.assertEqual((status, result["outcome"], result["content"], result["task"]), (200, "delivered", PUBLIC, {"kind": "task", "id": task["id"], "status": {"state": "completed"}}))
        self.assertEqual(pdp.call_count, 1)  # the resumed task is decided again by the PDP
        records = self.records()
        self.assertEqual(sorted((item["reason_code"], item.get("task_id")) for item in records), [("principal_expired", task["id"]), ("read_delivered", task["id"])])
        for record in records:
            self.assertTrue(a2a.verify_record(record, self.bundle(record["bundle_id"]), self.schemas))
        self.assertEqual(self.reason(*self.resume(task["id"])), (409, "task_not_found"))  # consumed exactly once

    def test_resume_is_bound_to_the_same_subject_skill_and_path(self):
        task_id = self.expire_mid_task()["task"]["id"]
        with patch.object(adapter_module.LocalReadAdapter, "read", side_effect=AssertionError("a mismatch never reaches the adapter")):
            self.assertEqual(self.reason(*self.resume(task_id, token=self.token(sub="agent-mallory"))), (409, "task_principal_mismatch"))
            self.assertEqual(self.reason(*self.resume(task_id, path="docs/other.md")), (409, "task_binding_mismatch"))
            self.assertEqual(self.reason(*self.resume(task_id, token=self.token(scope="other:read"))), (403, "insufficient_scope"))
        self.assertEqual(self.resume(task_id)[1]["result"]["outcome"], "delivered")  # owner can still resume
        mismatch = [item for item in self.records() if item["reason_code"] in {"task_principal_mismatch", "task_binding_mismatch"}]
        self.assertEqual(len(mismatch), 2); self.assertTrue(all(item["task_id"] == task_id and item["bundle_id"] is None for item in mismatch))

    def test_expired_unknown_or_malformed_tasks_fail_closed(self):
        with patch.object(a2a, "TASK_TTL_SECONDS", -1):
            task_id = self.expire_mid_task()["task"]["id"]
        with patch.object(adapter_module.LocalReadAdapter, "read", side_effect=AssertionError("adapter must not run")):
            self.assertEqual(self.reason(*self.resume(task_id)), (409, "task_expired"))
            self.assertEqual(self.reason(*self.resume(task_id)), (409, "task_not_found"))
            self.assertEqual(self.reason(*self.resume("0" * 32)), (409, "task_not_found"))
            self.assertEqual(self.reason(*self.resume("not-a-task")), (400, "invalid_request"))

    def test_resume_that_is_denied_reports_a_failed_task(self):
        task_id = self.expire_mid_task()["task"]["id"]
        (self.repo / "docs/readme.md").write_text("x" * 200); git(self.repo, "commit", "-qam", "grow past the budget")
        result = self.resume(task_id)[1]["result"]
        self.assertEqual((result["outcome"], result["task"]["status"]["state"]), ("deny", "failed")); self.assertNotIn("content", result)

    def test_task_is_bound_to_the_actor_chain_and_the_store_is_capped(self):
        # Review #7: another delegated actor for the same sub cannot consume the owner's task.
        task_id = self.expire_mid_task()["task"]["id"]
        self.assertEqual(self.reason(*self.resume(task_id, token=self.token(act={"sub": "agent-beta"}))), (409, "task_principal_mismatch"))
        self.assertEqual(self.resume(task_id)[1]["result"]["outcome"], "delivered")
        # Review #6: a full store degrades to a plain deny (no task), never to an effect.
        with patch.object(a2a, "MAX_OPEN_TASKS", 0):
            paused = self.expire_mid_task()
        self.assertEqual((paused["outcome"], paused["reason_code"], "task" in paused), ("deny", "principal_expired", False))

    def test_pre_claim_denies_keep_the_task_correlation(self):
        # Review #8: a resume denied before the claim still records which task it targeted.
        task_id = self.expire_mid_task()["task"]["id"]
        self.assertEqual(self.reason(*self.resume(task_id, token=self.token(scope="other:read"))), (403, "insufficient_scope"))
        [record] = [item for item in self.records() if item["reason_code"] == "insufficient_scope"]
        self.assertEqual(record["task_id"], task_id)
        self.assertTrue(a2a.verify_record(record, None, self.schemas))

    def test_expired_tasks_are_purged_when_new_ones_open(self):
        with patch.object(a2a, "TASK_TTL_SECONDS", -1):
            stale = self.expire_mid_task()["task"]["id"]
        self.expire_mid_task()
        self.assertEqual(self.reason(*self.resume(stale)), (409, "task_not_found"))
        self.assertEqual(len(self.gateway._tasks), 1)

    def test_resume_that_lapses_again_opens_a_new_task(self):
        first = self.expire_mid_task()["task"]["id"]
        later = type("Clock", (), {"time": staticmethod(lambda: time.time() + 3600)})
        with patch.object(pep_module, "time", later):
            again = self.resume(first)[1]["result"]
        self.assertEqual(again["task"]["status"]["state"], "auth-required"); self.assertNotEqual(again["task"]["id"], first)
        self.assertEqual(self.reason(*self.resume(first)), (409, "task_not_found"))
        self.assertEqual(self.resume(again["task"]["id"])[1]["result"]["outcome"], "delivered")

    # ADR 0018: a host-flagged skill pauses at input-required; only a direct human confirmation resumes.
    def confirm_gateway(self): return self.make(confirm_skills=frozenset({"read_workspace_file"}))

    def human(self, **overrides): return self.token(scope=f"workspace:read {a2a.CONFIRM_SCOPE}", **overrides)

    def test_input_required_pauses_without_pdp_or_effect(self):
        self.gateway = self.confirm_gateway()
        with patch.object(adapter_module.LocalReadAdapter, "read", side_effect=AssertionError("no effect before confirmation")), \
             patch.object(adapter_module, "decide", side_effect=AssertionError("PDP must not run")):
            status, payload = self.call(token=self.human())  # even a human-held token must confirm separately
        paused = payload["result"]
        self.assertEqual((status, paused["outcome"], paused["effect"], paused["reason_code"], paused["task"]["status"]["state"]), (200, "deny", "none", "input_required", "input-required"))
        self.assertNotIn("content", paused)
        [record] = self.records()
        self.assertEqual((record["reason_code"], record["task_id"], record["bundle_id"]), ("input_required", paused["task"]["id"], None))
        self.assertTrue(a2a.verify_record(record, None, self.schemas))

    def test_human_confirmation_resumes_with_exactly_one_new_admission(self):
        self.gateway = self.confirm_gateway()
        task_id = self.call()[1]["result"]["task"]["id"]  # an agent asks; the human confirms
        with patch.object(adapter_module, "decide", wraps=adapter_module.decide) as pdp:
            status, payload = self.resume(task_id, token=self.human())
        result = payload["result"]
        self.assertEqual((status, result["outcome"], result["content"], result["task"]["status"]["state"]), (200, "delivered", PUBLIC, "completed"))
        self.assertEqual(pdp.call_count, 1)
        self.assertEqual(result["audit"]["confirmation"], "human_confirmed")
        [confirmed] = [item for item in self.records() if item.get("confirmation")]
        self.assertEqual((confirmed["reason_code"], confirmed["task_id"]), ("read_delivered", task_id))
        self.assertTrue(a2a.verify_record(confirmed, self.bundle(confirmed["bundle_id"]), self.schemas))
        with patch.object(adapter_module.LocalReadAdapter, "read", side_effect=AssertionError("replay must not read")):
            self.assertEqual(self.reason(*self.resume(task_id, token=self.human())), (409, "task_not_found"))

    def test_pause_and_confirmation_records_carry_the_same_effect_binding(self):
        self.gateway = self.confirm_gateway()
        paused = self.call()[1]["result"]
        expected = a2a.effect_binding(self.principal(), "read_workspace_file", APPROVED)
        self.assertEqual(paused["audit"]["effect_binding"], expected)  # the client shows this before asking for the human token
        self.assertEqual(self.reason(*self.resume(paused["task"]["id"], token=self.human(), path="docs/other.md")), (409, "task_binding_mismatch"))
        confirmed = self.resume(paused["task"]["id"], token=self.human())[1]["result"]
        self.assertEqual(confirmed["audit"]["effect_binding"], expected)
        by_reason = {record["reason_code"]: record for record in self.records()}
        self.assertEqual((by_reason["input_required"]["effect_binding"], by_reason["read_delivered"]["effect_binding"]), (expected, expected))
        self.assertEqual(by_reason["task_binding_mismatch"]["effect_binding"], a2a.effect_binding(self.principal(), "read_workspace_file", "docs/other.md"), "the deny records what was attempted")
        self.assertTrue(all(a2a.verify_record(record, self.bundle(record["bundle_id"]) if record["bundle_id"] else None, self.schemas) for record in self.records()))
        stripped = {key: value for key, value in by_reason["read_delivered"].items() if key != "effect_binding"}
        stripped["record_id"] = a2a.digest({key: value for key, value in stripped.items() if key != "record_id"})
        self.assertFalse(a2a.verify_record(stripped, self.bundle(stripped["bundle_id"]), self.schemas), "a confirmed record without its binding never verifies")

    def test_invalid_confirmations_never_reach_the_adapter_and_keep_the_task(self):
        self.gateway = self.confirm_gateway()
        task_id = self.call()[1]["result"]["task"]["id"]
        with patch.object(adapter_module.LocalReadAdapter, "read", side_effect=AssertionError("adapter must not run")):
            self.assertEqual(self.reason(*self.resume(task_id)), (403, "human_confirmation_required"))  # the agent cannot self-confirm
            self.assertEqual(self.reason(*self.resume(task_id, token=self.human(act={"sub": "agent-beta"}))), (403, "scope_escalation_denied"))  # confirm is never delegable
            self.assertEqual(self.reason(*self.resume(task_id, token=self.human(sub="human-mallory"))), (409, "task_principal_mismatch"))
            self.assertEqual(self.reason(*self.resume(task_id, token=self.human(), path="docs/other.md")), (409, "task_binding_mismatch"))
            # Defense in depth: even if a host made confirm delegable, a delegated token never confirms.
            with patch.object(a2a, "DELEGABLE_SCOPES", a2a.DELEGABLE_SCOPES | {a2a.CONFIRM_SCOPE}):
                self.assertEqual(self.reason(*self.resume(task_id, token=self.human(act={"sub": "agent-beta"}))), (403, "human_confirmation_required"))
        self.assertEqual(self.resume(task_id, token=self.human())[1]["result"]["outcome"], "delivered")  # still claimable by its owner

    def test_stale_or_wrong_kind_tasks_never_confirm(self):
        self.gateway = self.confirm_gateway()
        with patch.object(a2a, "TASK_TTL_SECONDS", -1):
            stale = self.call()[1]["result"]["task"]["id"]
        self.assertEqual(self.reason(*self.resume(stale, token=self.human())), (409, "task_expired"))
        # A flagged skill pauses before the PEP, so a mid-task lapse cannot even open an auth-required task.
        self.assertEqual(self.expire_mid_task()["task"]["status"]["state"], "input-required")
        with patch.object(a2a, "MAX_OPEN_TASKS", 0), patch.object(adapter_module.LocalReadAdapter, "read", side_effect=AssertionError("no effect")):
            full = self.call()[1]["result"]
        self.assertEqual((full["outcome"], full["reason_code"], "task" in full), ("deny", "input_required", False))

    def test_auth_required_resume_of_a_flagged_skill_still_needs_confirmation(self):
        task_id = self.expire_mid_task()["task"]["id"]  # opened before the host flagged the skill
        flagged = self.confirm_gateway(); flagged._tasks = self.gateway._tasks; self.gateway = flagged
        with patch.object(adapter_module.LocalReadAdapter, "read", side_effect=AssertionError("no effect without confirmation")):
            again = self.resume(task_id)[1]["result"]
        self.assertEqual((again["reason_code"], again["task"]["status"]["state"]), ("input_required", "input-required"))
        self.assertNotEqual(again["task"]["id"], task_id)

    def test_consumed_decision_never_authorizes_a_second_effect(self):
        original, seen = PolicyEnforcementPoint.enforce_read, []

        def capture(pep, *args, **kwargs):
            seen.append((pep, args, kwargs)); return original(pep, *args, **kwargs)

        with patch.object(PolicyEnforcementPoint, "enforce_read", capture):
            self.assertEqual(self.call()[1]["result"]["outcome"], "delivered")
        pep, args, kwargs = seen[0]
        with patch.object(LocalReadRuntime, "read", side_effect=AssertionError("replay must not read")):
            result, _ = original(pep, *args, **kwargs)
        self.assertEqual((result["outcome"], result["reason_code"]), ("deny", "workspace_binding_mismatch"))
        with patch.object(LocalReadRuntime, "read", side_effect=AssertionError("no read")):
            result, _ = original(pep, *args, principal={**kwargs["principal"], "rogue": True})
        self.assertEqual((result["outcome"], result["reason_code"]), ("deny", "invalid_principal"))

    def test_record_must_match_its_bundle_and_carry_a_valid_principal(self):
        audit = self.call()[1]["result"]["audit"]
        bundle, principal = self.bundle(audit["bundle_id"]), self.principal()
        self.assertTrue(a2a.verify_record(a2a.evidence_record(principal, "read_workspace_file", "delivered", "read_delivered", bundle["decision_id"], bundle["bundle_id"]), bundle, self.schemas))
        self.assertFalse(a2a.verify_record(a2a.evidence_record(principal, "read_workspace_file", "delivered", "read_delivered", "f" * 64, bundle["bundle_id"]), bundle, self.schemas))
        self.assertFalse(a2a.verify_record(a2a.evidence_record({**principal, "token": "x"}, "read_workspace_file", "delivered", "read_delivered", bundle["decision_id"], bundle["bundle_id"]), bundle, self.schemas))
        with patch.object(a2a, "verify_offline", return_value=False):
            status, payload = self.call()
        self.assertEqual(self.reason(status, payload), (500, "a2a_evidence_failed")); self.assertNotIn(PUBLIC, json.dumps(payload))

    def test_replayed_decision_or_bundle_in_the_body_never_authorizes(self):
        audit = self.call()[1]["result"]["audit"]
        for extra in ({"decision_id": audit["decision_id"]}, {"bundle_id": audit["bundle_id"]}, {"admission": {"outcome": "admit_read"}}):
            self.assert_denied_before_adapter(400, "invalid_request", body=send(**extra))
        self.assert_denied_before_adapter(401, "auth_missing", token=None)

    # ADR 0014: CallerPrincipal is closed, optional for the PDP and never opens an effect.
    def test_caller_principal_schema_is_closed(self):
        validator = Draft7Validator(self.schemas["caller_principal"])
        self.assertTrue(validator.is_valid(self.principal()))
        for bad in ({**self.principal(), "token": "x"}, {**self.principal(), "act": [f"h{i}" for i in range(9)]}, {**self.principal(), "authn_method": "none"}):
            self.assertFalse(validator.is_valid(bad))

    def test_pdp_principal_presence_does_not_change_or_open_decisions(self):
        request = adapter_module.build_request({"snapshot_digest": "a" * 64}, "run-a2a", APPROVED, 64, host_policy=adapter_module.load_host_policy(str(self.policy), self.fingerprint, self.schemas))
        args = (request["intent"], request["profiles"], request["policy"], request["context"], self.schemas)
        self.assertEqual(decide(*args), decide(*args, principal=self.principal()))
        self.assertEqual(decide(*args)["outcome"], "admit_read")
        self.assertEqual(decide(*args, principal={**self.principal(), "rogue": 1})["stable_reason_code"], "invalid_principal")
        other = copy.deepcopy(request); other["intent"]["arguments"] = {"path": "docs/other.md"}; other["intent"]["resource_scope"] = {"kind": "filesystem", "path": "docs/other.md"}
        widened = self.principal(scopes=["workspace:read", "workspace:write", "admin:write"])
        self.assertEqual(decide(other["intent"], *args[1:], principal=widened)["outcome"], "deny")

    # ADR 0015: delegation chain is closed, acyclic and bounded; scopes never grow; no passthrough.
    def chain(self, *subs):
        act = None
        for sub in reversed(subs):
            act = {"sub": sub, **({"act": act} if act else {})}
        return act

    def test_malformed_cyclic_or_oversized_act_chains_are_rejected_before_the_pdp(self):
        cases = {
            "oversized": self.chain(*[f"hop-{index}" for index in range(a2a.MAX_ACT_DEPTH + 1)]),
            "open_shape": {"sub": "agent-beta", "iss": "https://elsewhere.invalid"},
            "not_an_object": "agent-beta",
            "bad_sub": {"sub": "agent beta"},
            "missing_sub": {"act": {"sub": "agent-beta"}},
            "self_delegation": {"sub": "agent-alpha"},
            "cycle": self.chain("agent-beta", "agent-gamma", "agent-beta"),
        }
        for name, act in cases.items():
            with self.subTest(name=name):
                self.assert_denied_before_adapter(401, "delegation_chain_invalid", token=self.token(act=act))
        self.assertEqual(self.records(), [])

    def test_valid_chains_up_to_max_depth_still_read_and_are_evidenced(self):
        for depth in (1, 3, a2a.MAX_ACT_DEPTH):
            subs = [f"hop-{index}" for index in range(depth)]
            with self.subTest(depth=depth):
                result = self.call(token=self.token(act=self.chain(*subs)))[1]["result"]
                self.assertEqual((result["outcome"], result["content"], result["audit"]["act"]), ("delivered", PUBLIC, subs))
        for record in self.records():
            self.assertTrue(a2a.verify_record(record, self.bundle(record["bundle_id"]), self.schemas))
        self.assertEqual(sorted(len(record["principal"]["act"]) for record in self.records()), [1, 3, a2a.MAX_ACT_DEPTH])

    def test_delegated_token_above_the_delegation_ceiling_is_denied_and_recorded(self):
        escalated = self.token(scope="workspace:read workspace:write", act={"sub": "agent-beta"})
        self.assert_denied_before_adapter(403, "scope_escalation_denied", token=escalated)
        [record] = self.records()
        self.assertEqual((record["reason_code"], record["principal"]["act"], record["principal"]["scopes"]), ("scope_escalation_denied", ["agent-beta"], ["workspace:read", "workspace:write"]))
        self.assertTrue(a2a.verify_record(record, None, self.schemas))
        # A direct (non-delegated) caller is bounded by skill scope + PDP, not by the delegation ceiling.
        self.assertEqual(self.call(token=self.token(scope="workspace:read workspace:write"))[1]["result"]["outcome"], "delivered")

    def test_exchange_narrows_scopes_retargets_aud_and_appends_the_actor(self):
        hop_b = a2a.HS256TokenValidator(self.secret, ISSUER, "agent-b")
        user_for_b = a2a.mint_hs256(self.claims(aud="agent-b", sub="user-carol", scope="workspace:read workspace:write"), self.secret)
        # Passthrough: the user's token for B is useless at this gateway.
        self.assert_denied_before_adapter(401, "token_audience_invalid", token=user_for_b)
        derived = a2a.exchange_hs256(hop_b, user_for_b, "agent-b", ["workspace:read"], AUDIENCE, self.secret)
        claims = a2a.HS256TokenValidator(self.secret, ISSUER, AUDIENCE).validate(derived)
        self.assertEqual((claims["scope"], claims["act"], claims["sub"]), ("workspace:read", {"sub": "agent-b"}, "user-carol"))
        self.assertLessEqual(claims["exp"], self.claims()["exp"])
        result = self.call(token=derived)[1]["result"]
        self.assertEqual((result["outcome"], result["audit"]["sub"], result["audit"]["act"]), ("delivered", "user-carol", ["agent-b"]))
        # Second hop narrows again and keeps the chain, current actor first.
        onward = a2a.exchange_hs256(a2a.HS256TokenValidator(self.secret, ISSUER, AUDIENCE), derived, "agent-c", [], "agent-d", self.secret, ttl=60)
        onward_claims = a2a.HS256TokenValidator(self.secret, ISSUER, "agent-d").validate(onward)
        self.assertEqual((onward_claims["act"], onward_claims.get("scope")), ({"sub": "agent-c", "act": {"sub": "agent-b"}}, ""))
        self.assertLessEqual(onward_claims["exp"], claims["exp"])
        for requested, reason in ((["workspace:read", "admin:write"], "scope_escalation_denied"),):
            with self.assertRaises(PermissionError) as raised:
                a2a.exchange_hs256(hop_b, user_for_b, "agent-b", requested, AUDIENCE, self.secret)
            self.assertEqual(raised.exception.args[0], reason)
        with self.assertRaises(PermissionError) as raised:
            a2a.exchange_hs256(a2a.HS256TokenValidator(self.secret, ISSUER, AUDIENCE), derived, "user-carol", ["workspace:read"], "agent-d", self.secret)
        self.assertEqual(raised.exception.args[0], "delegation_chain_invalid")
        for subject, reason in ((derived, "token_audience_invalid"), (a2a.mint_hs256(self.claims(aud="agent-b"), secrets.token_bytes(32)), "token_signature_invalid")):
            with self.assertRaises(PermissionError) as raised:  # the subject token is fully validated before any derivation
                a2a.exchange_hs256(hop_b, subject, "agent-x", ["workspace:read"], "agent-d", self.secret)
            self.assertEqual(raised.exception.args[0], reason)
        parent_exp = int(time.time()) + 30
        short_lived = a2a.mint_hs256(self.claims(aud="agent-b", exp=parent_exp), self.secret)
        derived_exp = a2a.HS256TokenValidator(self.secret, ISSUER, AUDIENCE).validate(a2a.exchange_hs256(hop_b, short_lived, "agent-b", ["workspace:read"], AUDIENCE, self.secret, ttl=3600))["exp"]
        self.assertEqual(derived_exp, parent_exp)  # never outlives the parent
        # ADR 0019: a derivation that would push the chain past MAX_ACT_DEPTH is refused before signing.
        chain = None
        for level in range(a2a.MAX_ACT_DEPTH):
            chain = {"sub": f"agent-{level}", **({"act": chain} if chain else {})}
        deep = a2a.mint_hs256(self.claims(aud="agent-b", sub="user-carol", act=chain), self.secret)
        with self.assertRaises(PermissionError) as raised:
            a2a.exchange_hs256(hop_b, deep, "agent-b", ["workspace:read"], AUDIENCE, self.secret)
        self.assertEqual(raised.exception.args[0], "delegation_chain_invalid")

    def test_server_never_binds_beyond_loopback(self):
        # ADR 0013 / A2A-8a: TLS and any public listener live in a proxy in front, never in this process.
        for host in ("0.0.0.0", "::", "localhost", "192.168.0.10", ""):
            with self.assertRaises(ValueError) as raised:
                a2a.make_server(self.gateway, host, 0)
            self.assertEqual(raised.exception.args[0], "loopback_only")

    def test_no_downstream_token_affordance_in_the_request(self):
        token = self.token()
        for field in ("subject_token", "actor_token", "downstream_token", "access_token"):
            self.assert_denied_before_adapter(400, "credential_in_payload", body=send(**{field: token}))
        data_extra = json.loads(send()); data_extra["params"]["message"]["parts"][0]["data"]["forward_to"] = "agent-d"
        self.assert_denied_before_adapter(400, "invalid_request", body=json.dumps(data_extra).encode())

    def test_missing_or_tampered_host_policy_fails_closed_without_demo_grants(self):
        for gateway in (self.make(host_policy_path=None, host_policy_sha256=None), self.make(host_policy_sha256="b" * 64), self.make(max_output_bytes=-1)):
            with self.subTest():
                with patch.object(adapter_module.LocalReadAdapter, "read", side_effect=AssertionError("adapter must not run")):
                    self.assertEqual(self.reason(*self.call(gateway=gateway)), (503, "host_policy_invalid"))

    def test_evidence_failure_never_delivers_content(self):
        with patch.object(a2a, "persist_record", side_effect=OSError("disk full")):
            status, payload = self.call()
        self.assertEqual(self.reason(status, payload), (500, "a2a_evidence_failed"))
        self.assertNotIn(PUBLIC, json.dumps(payload))

    def test_weak_secret_is_refused(self):
        with self.assertRaises(ValueError): a2a.HS256TokenValidator(b"short", ISSUER, AUDIENCE)

    # A2A-1: closed Agent Card, public vs authenticated.
    def test_public_and_extended_cards_match_the_closed_schema(self):
        validator = Draft7Validator(json.loads((SCHEMAS / "a2a-agent-card.schema.json").read_text()))
        public = self.gateway.card()
        self.assertEqual(list(validator.iter_errors(public)), [])
        self.assertEqual(public["skills"], [])
        status, payload = self.call(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "agent/getAuthenticatedExtendedCard"}).encode())
        self.assertEqual(status, 200)
        extended = payload["result"]
        self.assertEqual(list(validator.iter_errors(extended)), [])
        self.assertEqual([(skill["id"], skill["security"]) for skill in extended["skills"]], [(skill, [{"bearer": [scope]}]) for skill, scope in a2a.SKILL_SCOPES.items()])
        extended["rogue"] = True
        self.assertFalse(validator.is_valid(extended))
        status, payload = self.call(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "agent/getAuthenticatedExtendedCard"}).encode(), token=None)
        self.assertEqual(self.reason(status, payload), (401, "auth_missing"))

    def test_card_is_not_an_authority(self):
        # Mutating the announced card cannot widen what the gateway admits.
        with patch.object(a2a, "agent_card", lambda port, authenticated: {"skills": [{"id": "peticionar", "security": []}]}):
            self.assert_denied_before_adapter(403, "unknown_skill", body=send(skill="peticionar"))

    def test_malformed_requests(self):
        for body in (b"{", b"[]", json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tasks/cancel"}).encode()):
            with self.subTest(body=body):
                status, payload = self.call(body)
                self.assertEqual(status, 400); self.assertIn(payload["error"]["data"]["reason_code"], {"parse_error", "invalid_request"})
                self.assertIn(payload["error"]["code"], {-32700, -32600})

    # Transport: loopback only, no credential in logs, pilot curls.
    def test_http_transport_is_loopback_and_logs_no_credentials(self):
        with self.assertRaises(ValueError): a2a.make_server(self.gateway, "0.0.0.0", 0)
        server = a2a.make_server(self.gateway, "127.0.0.1", 0)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start(); self.addCleanup(server.shutdown)
        base, token, log = f"http://127.0.0.1:{server.server_address[1]}", self.token(), io.StringIO()

        def http(method, path, body=None, auth=None, length=None):
            # An oversized body is declared, not sent: the server must refuse from the header alone.
            extra = {**({"Authorization": auth} if auth else {}), **({"Content-Length": str(length)} if length else {})}
            request = urllib.request.Request(base + path, data=body, method=method, headers={"Content-Type": "application/json", **extra})
            try:
                with urllib.request.urlopen(request, timeout=10) as response: return response.status, json.loads(response.read()), dict(response.headers)
            except urllib.error.HTTPError as error: return error.code, json.loads(error.read()), dict(error.headers)

        with contextlib.redirect_stderr(log):
            status, card, _ = http("GET", a2a.CARD_PATH)
            self.assertEqual((status, card["skills"]), (200, []))
            status, payload, headers = http("POST", "/", send())
            self.assertEqual((status, payload["error"]["data"]["reason_code"]), (401, "auth_missing"))
            self.assertTrue(headers.get("WWW-Authenticate", "").startswith("Bearer"))
            status, payload, _ = http("POST", f"/?access_token={token}", send(), f"Bearer {token}")
            self.assertEqual(status, 404)
            status, payload, _ = http("POST", "/", send(), f"Bearer {token}")
            self.assertEqual((status, payload["result"]["outcome"], payload["result"]["content"]), (200, "delivered", PUBLIC))
            status, payload, headers = http("POST", "/", send(), f"Bearer {self.token(scope='other:read')}")
            self.assertEqual((status, headers.get("WWW-Authenticate")), (403, 'Bearer realm="adf-a2a", error="insufficient_scope"'))
            self.assertEqual(http("POST", "/", b"{}", f"Bearer {token}", a2a.MAX_BODY_BYTES + 1)[0], 413)
        self.assertIn("a2a POST", log.getvalue())
        for secret in (token, token.split(".")[1], "access_token"):
            self.assertNotIn(secret, log.getvalue())


def _probable_prime(bits, rng):
    while True:
        candidate = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if all(candidate % small for small in (3, 5, 7, 11, 13, 17, 19, 23, 29, 31)) and all(_miller_rabin(candidate, rng.randrange(2, candidate - 1)) for _ in range(24)):
            return candidate


def _miller_rabin(n, base):
    d, r = n - 1, 0
    while d % 2 == 0:
        d, r = d // 2, r + 1
    x = pow(base, d, n)
    if x in (1, n - 1):
        return True
    for _ in range(r - 1):
        x = pow(x, 2, n)
        if x == n - 1:
            return True
    return False


def rsa_key(bits=2048):
    rng = secrets.SystemRandom()
    while True:
        p, q = _probable_prime(bits // 2, rng), _probable_prime(bits // 2, rng)
        n, phi = p * q, (p - 1) * (q - 1)
        if p != q and n.bit_length() == bits and phi % 65537:
            return n, 65537, pow(65537, -1, phi)


def _b64decode_test(segment): return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def b64int(value): return b64(value.to_bytes((value.bit_length() + 7) // 8, "big"))


def sign_rs256(claims, key, kid="k1", header=None):
    n, _, d = key
    signing = f"{b64(json.dumps(header or {'alg': 'RS256', 'typ': 'JWT', 'kid': kid}).encode())}.{b64(json.dumps(claims).encode())}"
    size = (n.bit_length() + 7) // 8
    encoded = b"\x00\x01" + b"\xff" * (size - 3 - 19 - 32) + b"\x00" + a2a._SHA256_DIGEST_INFO + hashlib.sha256(signing.encode()).digest()
    return f"{signing}.{b64(pow(int.from_bytes(encoded, 'big'), d, n).to_bytes(size, 'big'))}"


class RS256JwksValidatorTest(unittest.TestCase):
    """ADR 0017: asymmetric validation over a host-pinned JWKS; the gateway holds no signing key."""
    @classmethod
    def setUpClass(cls):
        cls.key, cls.other = rsa_key(), rsa_key()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)

    def jwks(self, *entries):
        path = Path(self.temp.name) / f"jwks-{secrets.token_hex(4)}.json"
        path.write_text(json.dumps({"keys": list(entries) or [self.entry()]}))
        return str(path), hashlib.sha256(path.read_bytes()).hexdigest()

    def entry(self, key=None, kid="k1", **extra):
        n, e, _ = key or self.key
        return {"kty": "RSA", "kid": kid, "n": b64int(n), "e": b64int(e), "alg": "RS256", "use": "sig", **extra}

    def validator(self, *entries): return a2a.RS256JwksValidator(*self.jwks(*entries), ISSUER, AUDIENCE)

    def claims(self, **extra): return {"iss": ISSUER, "aud": AUDIENCE, "sub": "agent-alpha", "exp": int(time.time()) + 300, "scope": "workspace:read", **extra}

    def reason(self, validator, token):
        with self.assertRaises(PermissionError) as raised:
            validator.validate(token)
        return raised.exception.args[0]

    def test_valid_token_and_claim_rules_are_shared_with_the_pilot(self):
        validator = self.validator()
        self.assertEqual(validator.validate(sign_rs256(self.claims(), self.key))["sub"], "agent-alpha")
        self.assertEqual(self.reason(validator, sign_rs256(self.claims(aud="other"), self.key)), "token_audience_invalid")
        self.assertEqual(self.reason(validator, sign_rs256(self.claims(exp=int(time.time()) - 1), self.key)), "token_expired")

    def test_signature_key_and_algorithm_failures(self):
        validator, token = self.validator(), sign_rs256(self.claims(), self.key)
        header, payload, signature = token.split(".")
        forged_payload = b64(json.dumps(self.claims(scope="workspace:write")).encode())
        oversized = b64(bytes([255]) * 256)  # same length as n but numerically >= n
        cases = {
            "token_signature_invalid": [sign_rs256(self.claims(), self.other), f"{header}.{forged_payload}.{signature}", f"{header}.{payload}.{signature[:-4]}", f"{header}.{payload}.{oversized}"],
            "token_key_unknown": [sign_rs256(self.claims(), self.key, kid="k2"), sign_rs256(self.claims(), self.key, header={"alg": "RS256", "typ": "JWT"})],
            "token_alg_rejected": [sign_rs256(self.claims(), self.key, header={"alg": "none", "kid": "k1"}), sign_rs256(self.claims(), self.key, header={"alg": "RS512", "kid": "k1"})],
        }
        for reason, tokens in cases.items():
            for item in tokens:
                with self.subTest(reason=reason):
                    self.assertEqual(self.reason(validator, item), reason)
        # Malleability (RFC 8017 §8.2.2): a leading zero byte or s + n is the same integer mod n, still rejected.
        raw = _b64decode_test(signature); n = self.key[0]
        for variant in (b"\x00" + raw, (int.from_bytes(raw, "big") + n).to_bytes(len(raw) + 1, "big").lstrip(b"\x00").rjust(len(raw), b"\x00")):
            self.assertEqual(self.reason(validator, f"{header}.{payload}.{b64(variant)}"), "token_signature_invalid")
        self.assertTrue(a2a.rs256_verify(n, 65537, f"{header}.{payload}".encode(), raw))
        # HS256 signed with the public modulus as secret (alg confusion) never verifies.
        confused = forge({"alg": "HS256", "kid": "k1"}, self.claims(), self.entry()["n"].encode())
        self.assertEqual(self.reason(validator, confused), "token_alg_rejected")

    def test_jwks_is_pinned_closed_and_strong(self):
        path, pin = self.jwks()
        weak = rsa_key(1024)
        bad = [
            (path, "0" * 64), (Path(path).name, pin), (None, None), (path, None),
            self.jwks(self.entry(x5c=["cert"])), self.jwks(self.entry(alg="RS512")), self.jwks(self.entry(use="enc")),
            self.jwks(self.entry(key=weak)), self.jwks({**self.entry(), "e": b64int(3)}), self.jwks(self.entry(), self.entry(key=self.other)),
            self.jwks(self.entry(kty="EC")), self.jwks(self.entry(kid="bad kid")),
        ]
        for jwks_path, jwks_pin in bad:
            with self.subTest(path=jwks_path):
                with self.assertRaises(ValueError) as raised:
                    a2a.RS256JwksValidator(jwks_path, jwks_pin, ISSUER, AUDIENCE)
                self.assertEqual(raised.exception.args[0], "jwks_invalid")
        empty = Path(self.temp.name) / "empty.json"; empty.write_text('{"keys": []}')
        with self.assertRaises(ValueError): a2a.RS256JwksValidator(str(empty), hashlib.sha256(empty.read_bytes()).hexdigest(), ISSUER, AUDIENCE)
        rotated = self.validator(self.entry(), self.entry(key=self.other, kid="k2"))
        self.assertEqual(rotated.validate(sign_rs256(self.claims(), self.other, kid="k2"))["sub"], "agent-alpha")
        self.assertEqual(self.reason(rotated, sign_rs256(self.claims(), self.other, kid="k1")), "token_signature_invalid")

    def test_verify_refuses_moduli_too_small_for_pkcs1_padding(self):
        while True:
            small = rsa_key(448)  # 56-byte modulus: only 2 bytes of 0xff padding (< 8 required)
            token = sign_rs256(self.claims(), small)
            header, payload, signature = token.split(".")
            if int.from_bytes(_b64decode_test(signature), "big") < small[0]:
                break
        self.assertFalse(a2a.rs256_verify(small[0], small[1], f"{header}.{payload}".encode(), _b64decode_test(signature)))

    def test_signature_integer_must_be_below_the_modulus(self):
        key = rsa_key(2044)  # 256-byte encoding with headroom, so s + n still fits in `size` bytes
        header, payload, signature = sign_rs256(self.claims(), key).split(".")
        raw, message = _b64decode_test(signature), f"{header}.{payload}".encode()
        self.assertTrue(a2a.rs256_verify(key[0], key[1], message, raw))
        shifted = (int.from_bytes(raw, "big") + key[0]).to_bytes(len(raw), "big")
        self.assertFalse(a2a.rs256_verify(key[0], key[1], message, shifted))

    def test_relative_jwks_path_is_refused_even_when_it_exists(self):
        path, pin = self.jwks()
        relative = os.path.relpath(path)
        self.assertTrue(Path(relative).exists())
        with self.assertRaises(ValueError): a2a.RS256JwksValidator(relative, pin, ISSUER, AUDIENCE)

    def test_degenerate_or_oversized_moduli_are_refused(self):
        # Review #1: n = 2**2048 makes forgery trivial; even/small-factor/huge moduli never load.
        n = self.key[0]
        for modulus in (2 ** 2048, n * 3 if (n * 3).bit_length() <= 8192 else n - 1, (n | 1) * 997, n ** 5):  # n**5: odd, no small factor, > 8192 bits
            with self.subTest(bits=modulus.bit_length()):
                with self.assertRaises(ValueError):
                    a2a.RS256JwksValidator(*self.jwks({**self.entry(), "n": b64int(modulus)}), ISSUER, AUDIENCE)

    def test_non_canonical_base64_and_crit_headers_are_rejected(self):
        # Review #3/#4: one spelling per token; unknown critical extensions are refused.
        validator = self.validator()
        header, payload, signature = sign_rs256(self.claims(), self.key).split(".")
        for variant in (signature + "=", signature.replace("-", "+").replace("_", "/") if ("-" in signature or "_" in signature) else signature + "+"):
            self.assertEqual(self.reason(validator, f"{header}.{payload}.{variant}"), "token_malformed")
        self.assertEqual(self.reason(validator, sign_rs256(self.claims(), self.key, header={"alg": "RS256", "kid": "k1", "crit": ["exp"]})), "token_alg_rejected")

    def test_deeply_nested_json_fails_closed_with_a_response(self):
        # Review #2: RecursionError in header, body or JWKS becomes a stable deny, never a dropped connection.
        validator = self.validator()
        self.assertEqual(self.reason(validator, f"{b64(b'[' * 40000)}.e30.AA"), "token_malformed")
        nested = Path(self.temp.name) / "nested.json"; nested.write_bytes(b'{"keys":' + b"[" * 40000 + b"]" * 40000 + b"}")
        with self.assertRaises(ValueError):
            a2a.RS256JwksValidator(str(nested), hashlib.sha256(nested.read_bytes()).hexdigest(), ISSUER, AUDIENCE)
        base = A2AGatewayTest("test_weak_secret_is_refused"); base.setUp(); self.addCleanup(base.temp.cleanup)
        status, payload = base.gateway.handle(f"Bearer {base.token()}", b'{"a":' * 900 + b"1" + b"}" * 900)
        self.assertEqual((status, payload["error"]["data"]["reason_code"]), (400, "invalid_request"))
        status, payload = base.gateway.handle(f"Bearer {base.token()}", b"[" * 40000 + b"]" * 40000)
        self.assertEqual(status, 400)

    def test_openssl_signature_verifies_as_an_independent_oracle(self):
        if subprocess.run(["sh", "-c", "command -v openssl"], stdout=subprocess.DEVNULL).returncode:
            self.skipTest("openssl unavailable: independent RS256 oracle skipped")
        directory = Path(self.temp.name)
        subprocess.run(["openssl", "genrsa", "-out", str(directory / "key.pem"), "2048"], check=True, capture_output=True)
        modulus = subprocess.run(["openssl", "rsa", "-in", str(directory / "key.pem"), "-noout", "-modulus"], check=True, capture_output=True, text=True).stdout.strip().split("=", 1)[1]
        entry = {"kty": "RSA", "kid": "ossl", "n": b64int(int(modulus, 16)), "e": b64int(65537)}
        signing = f"{b64(json.dumps({'alg': 'RS256', 'kid': 'ossl'}).encode())}.{b64(json.dumps(self.claims()).encode())}"
        (directory / "signing").write_bytes(signing.encode())
        signature = subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(directory / "key.pem"), str(directory / "signing")], check=True, capture_output=True).stdout
        self.assertEqual(self.validator(entry).validate(f"{signing}.{b64(signature)}")["sub"], "agent-alpha")

    def test_gateway_reads_with_rs256_and_records_the_method(self):
        base = A2AGatewayTest("test_weak_secret_is_refused"); base.setUp(); self.addCleanup(base.temp.cleanup)
        gateway = base.make(validator=self.validator())
        status, payload = gateway.handle(f"Bearer {sign_rs256(self.claims(), self.key)}", send())
        self.assertEqual((status, payload["result"]["outcome"]), (200, "delivered"))
        [record] = base.records()
        self.assertEqual(record["principal"]["authn_method"], "bearer_jwt_rs256")
        self.assertTrue(a2a.verify_record(record, base.bundle(record["bundle_id"]), base.schemas))
        self.assertEqual(gateway.handle(f"Bearer {a2a.mint_hs256(self.claims(), secrets.token_bytes(32))}", send())[1]["error"]["data"]["reason_code"], "token_alg_rejected")

    def test_host_validator_selection_fails_closed_on_partial_jwks_config(self):
        path, pin = self.jwks()
        with patch.dict("os.environ", {"ADF_A2A_JWKS_FILE": path, "ADF_A2A_JWKS_SHA256": pin}, clear=False):
            self.assertIsInstance(a2a.host_validator(ISSUER, AUDIENCE), a2a.RS256JwksValidator)
        with patch.dict("os.environ", {"ADF_A2A_JWKS_FILE": path, "ADF_A2A_HS256_SECRET": "ab" * 32}, clear=False):
            with self.assertRaises(ValueError): a2a.host_validator(ISSUER, AUDIENCE)
        with patch.dict("os.environ", {"ADF_A2A_HS256_SECRET": "ab" * 32}, clear=True):
            self.assertIsInstance(a2a.host_validator(ISSUER, AUDIENCE), a2a.HS256TokenValidator)


class MintCliTest(unittest.TestCase):
    def mint(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"ADF_A2A_HS256_SECRET": secrets.token_hex(32)}), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = a2a._main(["mint", "agent-alpha", "workspace:read", *argv])
        token = out.getvalue().strip()
        exp = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "==")).get("exp") if token else None
        return code, exp, err.getvalue()

    def test_pilot_mint_defaults_to_one_hour_and_caps_the_ttl(self):
        now = int(time.time())
        code, exp, _ = self.mint(); self.assertEqual(code, 0); self.assertTrue(now + 3590 <= exp <= now + 3610)
        code, exp, _ = self.mint("--ttl", "7200"); self.assertEqual(code, 0); self.assertTrue(now + 7190 <= exp <= now + 7210)
        for bad in (("--ttl", "0"), ("--ttl", "86401"), ("--ttl", "-5"), ("--ttl", "1h"), ("--exp", "60")):
            with self.subTest(argv=bad):
                code, exp, err = self.mint(*bad); self.assertEqual((code, exp), (2, None)); self.assertIn("usage", err)


if __name__ == "__main__":
    unittest.main()
