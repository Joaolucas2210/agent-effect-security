"""ADR 0039 (Proposed) at the A2A edge: the gateway reads its pinned host policy once, through a `PolicySource`.

Equivalence: the default (file + pin), an explicit `HostPolicyFile` and an in-memory source give the same HTTP
status, JSON-RPC result, reason code and A2A evidence record. Fail closed: a source that raises, returns `None` (the
reference demo selector) or anything off-contract (bad pin, pin divergence, schema-invalid, wrong envelope) makes
every read 503 `host_policy_invalid` before any adapter exists; the edge never serves demo grants. Lifecycle: the
source is consulted once, at construction; there is no reload, so a policy edited on disk after startup changes
nothing until a restart, exactly as before the wiring. No bypass: the gateway check and the adapter re-check each
deny on their own.
"""
import json
import secrets
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import integration.a2a_gateway as a2a  # noqa: E402
import integration.local_read_adapter as adapter_module  # noqa: E402
from integration.extensions import HostPolicyFile  # noqa: E402

ISSUER, AUDIENCE, APPROVED = "https://idp.test.invalid", "adf-a2a-local", "docs/readme.md"
PUBLIC, SECRET = "allowed-public-content", "conteudo-secreto-do-arquivo"
_VOLATILE = {"record_id", "nonce", "created_at", "decision_id", "bundle_id", "task_id", "expires_at"}


def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def mask(value):
    if isinstance(value, dict): return {key: ("<volatile>" if key in _VOLATILE else {**mask(item), "id": "<volatile>"} if key == "task" else mask(item)) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [mask(item) for item in value]
    return value


def send(skill="read_workspace_file", path=APPROVED):
    data = {"skill": skill, "arguments": {"path": path}}
    return json.dumps({"jsonrpc": "2.0", "id": "r1", "method": "message/send", "params": {"message": {"kind": "message", "role": "user", "messageId": "m1", "parts": [{"kind": "data", "data": data}]}}}).encode()


class Loaded:
    def __init__(self, value): self.value, self.calls = value, 0
    def load(self): self.calls += 1; return self.value


class Raising:
    def load(self): raise RuntimeError(SECRET)


class A2APolicySourceTest(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(); self.repo = self.base / "source"; self.repo.mkdir()
        (self.repo / "docs").mkdir(); (self.repo / "docs/readme.md").write_text(PUBLIC); (self.repo / "docs/other.md").write_text(SECRET); (self.repo / ".env").write_text(SECRET)
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "a2a@example.invalid"); git(self.repo, "config", "user.name", "A2A"); git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "initial")
        self.secret, self.schemas, self.count = secrets.token_bytes(32), adapter_module.schemas(), 0
        self.config = self.build(APPROVED)
        self.policy = self.base / "host-policy.json"; self.policy.write_text(json.dumps(self.config))
        self.pin = adapter_module.digest(self.config)

    def build(self, path, run_id="run-a2a"):
        request = adapter_module.build_request({"snapshot_digest": "a" * 64}, run_id, path, 64)
        return {"schema_version": "1.0", **{key: request[key] for key in ("profiles", "policy", "context")}}

    def make(self, **overrides):
        self.count += 1
        options = {"validator": a2a.HS256TokenValidator(self.secret, ISSUER, AUDIENCE), "trusted_repository": self.repo, "trusted_revision": "HEAD", "evidence_dir": self.base / f"evidence-{self.count}", "host_policy_path": str(self.policy), "host_policy_sha256": self.pin, "max_output_bytes": 64, "port": 8765, "workspace_parent": self.base}
        options.update(overrides)
        return a2a.A2AGateway(**options)

    def source(self, value):
        return self.make(host_policy_path=None, host_policy_sha256=None, policy_source=value)

    def call(self, gateway, body=None):
        token = a2a.mint_hs256({"iss": ISSUER, "aud": AUDIENCE, "sub": "agent-alpha", "exp": int(time.time()) + 300, "scope": "workspace:read"}, self.secret)
        return gateway.handle(f"Bearer {token}", body or send())

    def records(self, gateway):
        directory = gateway._evidence / "_a2a"
        return sorted((mask(json.loads(path.read_text())) for path in directory.glob("*.json")), key=json.dumps) if directory.exists() else []

    def observe(self, gateway, *bodies):
        responses = [mask(self.call(gateway, body)) for body in bodies]
        return responses, self.records(gateway)

    def assert_refused(self, gateway):
        with patch.object(adapter_module.LocalReadAdapter, "read", side_effect=AssertionError("adapter must not run")):
            status, payload = self.call(gateway)
        self.assertIsNone(gateway._adapter, "an invalid policy builds no adapter")
        self.assertEqual((status, payload["error"]["data"]["reason_code"]), (503, "host_policy_invalid"))
        self.assertNotIn(SECRET, json.dumps(payload)); self.assertNotIn(PUBLIC, json.dumps(payload))
        self.assertEqual([record["reason_code"] for record in self.records(gateway)], ["host_policy_invalid"])
        self.assertEqual([path.name for path in gateway._evidence.iterdir()], ["_a2a"], "no bundle: nothing was decided")

    def repinned(self, mutate):
        config = json.loads(json.dumps(self.config)); mutate(config)
        return config, adapter_module.digest(config)

    # Equivalence ------------------------------------------------------------------------------------------------

    def test_default_explicit_file_and_in_memory_sources_are_equivalent(self):
        bodies = (send(), send(path="docs/other.md"), send(path=".env"), send(skill="unknown"))
        default = self.observe(self.make(), *bodies)
        explicit = self.observe(self.source(HostPolicyFile(str(self.policy), self.pin)), *bodies)
        in_memory = self.observe(self.source(Loaded((json.loads(self.policy.read_text()), self.pin))), *bodies)
        self.assertEqual(default, explicit); self.assertEqual(default, in_memory)
        responses = [(status, payload.get("result", {}).get("reason_code") or payload["error"]["data"]["reason_code"]) for status, payload in default[0]]
        self.assertEqual([status for status, _ in responses], [200, 200, 200, 403])
        self.assertEqual(default[0][0][1]["result"]["content"], PUBLIC)
        self.assertEqual(responses[1][1], "scope_not_allowlisted")
        self.assertEqual(responses[3][1], "unknown_skill")

    def test_confirmation_pause_and_resume_are_unchanged_with_a_source(self):
        paused = [mask(self.call(gateway)) for gateway in (self.make(confirm_skills={"read_workspace_file"}), self.make(host_policy_path=None, host_policy_sha256=None, confirm_skills={"read_workspace_file"}, policy_source=Loaded((self.config, self.pin))))]
        self.assertEqual(paused[0], paused[1])
        self.assertEqual(paused[0][1]["result"]["reason_code"], "input_required")

    def test_the_policy_file_is_read_once(self):
        original, calls = HostPolicyFile.read, []
        def counting(source): calls.append(source.path); return original(source)
        with patch.object(HostPolicyFile, "read", counting):
            gateway = self.make()
        self.assertEqual(calls, [str(self.policy)], "one load; the adapter gets the checked policy, not the file again")
        self.assertEqual(self.call(gateway)[1]["result"]["content"], PUBLIC)

    # Fail closed ------------------------------------------------------------------------------------------------

    def test_a_source_returning_none_is_refused_never_the_demo(self):
        with patch.object(adapter_module.LocalReadAdapter, "__init__", side_effect=AssertionError("no adapter, so no demo grants")):
            gateways = (self.source(Loaded(None)), self.source(HostPolicyFile()), self.make(host_policy_path=None, host_policy_sha256=None))
        for gateway in gateways:
            with self.subTest(): self.assert_refused(gateway)

    def test_invalid_or_unavailable_sources_are_refused_at_startup(self):
        other_config, other_pin = self.repinned(lambda config: config["context"]["resolved_run_config_ref"].update(run_id="run-other"))
        cases = {
            "raises": Raising(),
            "not_a_tuple": Loaded(self.config),
            "wrong_arity": Loaded((self.config, self.pin, "extra")),
            "config_not_a_dict": Loaded(([self.config], self.pin)),
            "pin_missing": Loaded((self.config, None)),
            "pin_malformed": Loaded((self.config, self.pin.upper())),
            "pin_divergence": Loaded((self.config, other_pin)),
            "tampered_after_pin": Loaded((other_config, self.pin)),
            "inner_digest_tampered_and_repinned": Loaded(self.repinned(lambda config: config["policy"].update(policy_id="forged-policy"))),
            "schema_invalid_and_repinned": Loaded(self.repinned(lambda config: config["context"].pop("policy_ref"))),
            "two_profiles_and_repinned": Loaded(self.repinned(lambda config: config["profiles"].append(config["profiles"][0]))),
            "extra_envelope_key_and_repinned": Loaded(self.repinned(lambda config: config.update(grants=["docs/other.md"]))),
            "wrong_schema_version_and_repinned": Loaded(self.repinned(lambda config: config.update(schema_version="2.0"))),
            "file_source_missing_file": HostPolicyFile(str(self.base / "absent.json"), self.pin),
            "file_source_relative_path": HostPolicyFile("host-policy.json", self.pin),
            "file_source_partial_pair": HostPolicyFile(str(self.policy), None),
        }
        for name, source in cases.items():
            with self.subTest(case=name):
                self.assert_refused(self.source(source))

    def test_a_source_together_with_the_file_pair_is_ambiguous_and_refused(self):
        self.assert_refused(self.make(policy_source=Loaded((self.config, self.pin))))
        self.assert_refused(self.make(host_policy_sha256=None, policy_source=Loaded((self.config, self.pin))))

    def test_an_invalid_budget_still_refuses_with_a_valid_source(self):
        self.assert_refused(self.make(host_policy_path=None, host_policy_sha256=None, max_output_bytes=-1, policy_source=Loaded((self.config, self.pin))))

    def test_both_checks_deny_on_their_own(self):
        bad = Loaded((self.config, adapter_module.digest({"other": 1})))
        with patch.object(a2a, "check_host_policy", lambda config, pin, schemas: config):  # gateway check removed: the adapter re-check still denies
            status, payload = self.call(self.source(bad))
        self.assertEqual((status, payload["result"]["outcome"], payload["result"]["reason_code"]), (200, "deny", "host_policy_invalid"))
        self.assertNotIn(PUBLIC, json.dumps(payload))
        with patch.object(adapter_module, "check_host_policy", lambda config, pin, schemas: config):  # adapter check removed: the gateway still refuses
            self.assert_refused(self.source(bad))

    # Lifecycle: loaded once, no reload --------------------------------------------------------------------------

    def test_the_source_is_consulted_once_and_never_at_request_time(self):
        source = Loaded((self.config, self.pin))
        gateway = self.source(source)
        for _ in range(3): self.assertEqual(self.call(gateway)[1]["result"]["content"], PUBLIC)
        source.value = None  # a source that would now refuse is not asked again
        self.assertEqual(self.call(gateway)[1]["result"]["content"], PUBLIC)
        self.assertEqual(source.calls, 1)

    def test_a_source_cannot_change_the_policy_after_it_was_checked(self):
        config = json.loads(json.dumps(self.config))
        gateway = self.source(Loaded((config, self.pin)))
        widened = self.build("docs/other.md", run_id="run-widened"); config.clear(); config.update(widened)  # grant and run id both swapped
        self.assertEqual(self.call(gateway, send(path="docs/other.md"))[1]["result"]["reason_code"], "scope_not_allowlisted")
        self.assertEqual(self.call(gateway)[1]["result"]["content"], PUBLIC)

    def test_a_policy_edited_on_disk_after_startup_changes_nothing_until_restart(self):
        gateway = self.make()
        widened = self.build("docs/other.md"); self.policy.write_text(json.dumps(widened))
        self.assertEqual(self.call(gateway)[1]["result"]["content"], PUBLIC)
        other = self.call(gateway, send(path="docs/other.md"))[1]["result"]
        self.assertEqual((other["outcome"], other["reason_code"]), ("deny", "scope_not_allowlisted")); self.assertNotIn(SECRET, json.dumps(other))
        self.policy.unlink()
        self.assertEqual(self.call(gateway)[1]["result"]["content"], PUBLIC)
        self.policy.write_text(json.dumps(widened))
        self.assert_refused(self.make())  # restart with the old pin: divergence, refused
        restarted = self.make(host_policy_sha256=adapter_module.digest(widened))  # the host re-pins: the new grant applies
        self.assertEqual(self.call(restarted, send(path="docs/other.md"))[1]["result"]["content"], SECRET)

    def test_selection_is_by_constructor_argument_only(self):
        import inspect
        parameter = inspect.signature(a2a.A2AGateway).parameters["policy_source"]
        self.assertEqual((parameter.kind, parameter.default), (inspect.Parameter.KEYWORD_ONLY, None))
        self.assertNotIn("policy_source", inspect.getsource(a2a._main))


if __name__ == "__main__":
    unittest.main()
