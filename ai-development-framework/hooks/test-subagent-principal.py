"""ADR 0033: a Claude Code subagent acts for the main thread of its session; the local principal carries that as
`act=["claude:main"]` (depth 1), `principal_rules` may cap depth with `max_act_depth`, the PDP denies deeper
principals with `act_depth_exceeded`, and journal/span record the depth. Main thread unchanged (depth 0).
"""
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks/adf-read-hook.py"
sys.path.insert(0, str(ROOT))
from integration.local_read_adapter import build_request, load_host_policy, schemas  # noqa: E402
from integration.read_gate_host import local_principal  # noqa: E402
from tools.pdp import decide  # noqa: E402


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


pack = _module("effect_security_read_v0", ROOT / "policy-packs/effect-security-read-v0/build.py")
otel_suite = _module("otel_suite", ROOT / "hooks/test-otel-export.py")
WORKER, MAIN, SESSION = "claude:worker", "claude:main", "sess-depth"


def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


class SubagentPrincipalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve(); self.repo = base / "repo"; self.home = base / "adf-home"; self.home.mkdir(); self.repo.mkdir()
        (self.repo / "README.md").write_text("public"); (self.repo / "docs").mkdir(); (self.repo / "docs/guide.md").write_text("guide")
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "m@example.invalid"); git(self.repo, "config", "user.name", "m"); git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "f")
        (self.home / "enabled-projects").write_text(f"{self.repo}\n")
        self.schemas = schemas()

    def test_local_principal_carries_the_act_chain(self):
        self.assertEqual(local_principal({"agent_type": "worker"}, "claude")["act"], [MAIN])
        self.assertEqual(local_principal({}, "claude")["act"], [], "main thread: depth 0")
        self.assertEqual(local_principal({"agent_type": "main"}, "claude")["act"], [])
        self.assertIsNone(local_principal({"agent_type": "bad name"}, "claude"))

    def policy(self, *principal_args):
        principals = {item.split("=")[0]: item.split("=")[1].split(",") for item in principal_args}
        target, pin = pack.write(pack.build(SESSION, ["README.md", "docs/guide.md"], 64, principals=principals), Path(self.temp.name) / "policy.json")
        return target, pin

    def decide_for(self, config, path, principal):
        request = build_request({"snapshot_digest": "a" * 64}, SESSION, path, 64, host_policy=config)
        return decide(request["intent"], request["profiles"], request["policy"], request["context"], self.schemas, principal=principal)["stable_reason_code"]

    def test_pdp_caps_act_depth_per_principal(self):
        target, pin = self.policy(f"{WORKER}=README.md", f"{MAIN}=README.md,docs/guide.md")
        config = load_host_policy(str(target), pin, self.schemas)
        worker = {**local_principal({"agent_type": "worker"}, "claude")}; main = local_principal({}, "claude")
        self.assertEqual(self.decide_for(config, "README.md", worker), "admit_read", "no cap: a subagent reads what its rule allows")
        capped = copy.deepcopy(config); capped["policy"]["principal_rules"] = [dict(rule, max_act_depth=0) if rule["sub"] == WORKER else rule for rule in capped["policy"]["principal_rules"]]
        capped["policy"]["policy_sha256"] = __import__("integration.local_evidence_bundle", fromlist=["digest"]).digest({k: v for k, v in capped["policy"].items() if k != "policy_sha256"})
        capped["context"]["policy_ref"]["policy_sha256"] = capped["policy"]["policy_sha256"]
        self.assertEqual(self.decide_for(capped, "README.md", worker), "act_depth_exceeded")
        self.assertEqual(self.decide_for(capped, "README.md", main), "admit_read", "main thread is depth 0")
        deep = dict(worker, act=[MAIN] * 9)
        self.assertEqual(self.decide_for(config, "README.md", deep), "invalid_principal", "the schema caps the chain at 8")

    def test_builder_writes_max_act_depth(self):
        target, pin = pack.write(pack.build(SESSION, ["README.md"], 64, principals={WORKER: ["README.md"]}, max_act_depth={WORKER: 0}), Path(self.temp.name) / "p2.json")
        loaded = load_host_policy(str(target), pin, self.schemas)
        self.assertEqual(loaded["policy"]["principal_rules"], [{"sub": WORKER, "allowed_scopes": [{"kind": "filesystem", "path": "README.md"}], "max_act_depth": 0}])
        self.assertEqual(pack.main(["--run-id", SESSION, "--allow", "README.md", "--max-act-depth", "nobody=0", "--out", str(Path(self.temp.name) / "x.json")]), 2, "a cap without a principal rule is refused")
        self.assertEqual(pack.main(["--run-id", SESSION, "--allow", "README.md", "--principal", f"{WORKER}=README.md", "--max-act-depth", f"{WORKER}=1", "--out", str(Path(self.temp.name) / "y.json")]), 0)

    def test_hook_end_to_end_denies_the_subagent_with_a_bundle_journal_and_span(self):
        target, pin = pack.write(pack.build(SESSION, ["README.md"], 64, principals={WORKER: ["README.md"], MAIN: ["README.md"]}, max_act_depth={WORKER: 0}), Path(self.temp.name) / "p3.json")
        sink = otel_suite.Sink(); self.addCleanup(sink.close)
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home.parent), "ADF_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo), "ADF_READ_POLICY_FILE": str(target), "ADF_READ_POLICY_SHA256": pin, "ADF_MAX_OUTPUT_BYTES": "64", "ADF_OTEL_ENABLED": "1", "ADF_OTEL_EXPORTER_OTLP_ENDPOINT": sink.endpoint}
        def read(agent_type=None):
            payload = {"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": SESSION, "tool_input": {"file_path": str(self.repo / "README.md")}, **({"agent_type": agent_type, "agent_id": "a1"} if agent_type else {})}
            proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual((proc.returncode, proc.stderr), (0, "")); return json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("deny/act_depth_exceeded bundle=", read("worker"))
        self.assertIn("delivered/read_delivered", read())
        journals = sorted((self.home / "evidence").rglob("_attempts/*.jsonl")); starts = [json.loads(p.read_text().splitlines()[0])["payload"] for p in journals]
        self.assertIn({"principal_sub": WORKER, "act_depth": 1}, starts); self.assertIn({"principal_sub": MAIN, "act_depth": 0}, starts)
        spans = [otel_suite.attrs(json.loads(b)["resourceSpans"][0]["scopeSpans"][0]["spans"][0]) for b in (sink.arrived.acquire(timeout=5), sink.arrived.acquire(timeout=5)) and sink.bodies[-2:]]
        self.assertEqual(sorted((s["adf.agent_type"], str(s["adf.act_depth"])) for s in spans), [("main", "0"), ("worker", "1")])
        text = "".join(p.read_text() for p in journals); self.assertNotIn('"a1"', text); self.assertNotIn("agent_id", text)  # the harness agent_id is not recorded


if __name__ == "__main__": unittest.main(verbosity=2)
