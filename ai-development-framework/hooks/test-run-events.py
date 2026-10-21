"""Run-event contracts with real gates, disposable repositories and stdlib only."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
SECRET = "test-sensitive-value-do-not-log"


class RunEventsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.fw = self.repo / "fw"
        shutil.copytree(ROOT / "hooks", self.fw / "hooks")
        if (ROOT / "contracts").exists():
            shutil.copytree(ROOT / "contracts", self.fw / "contracts")
        self.fix = self.fw / "docs/evals/fixtures/demo"
        self.fix.mkdir(parents=True)
        (self.fix / "solution.cjs").write_text("module.exports = 42;\n")
        (self.fix / "test.js").write_text(
            "require('node:assert').strictEqual(require('./solution.cjs'), 42);\n"
        )
        self.trajectories = self.fw / "docs/evals/runs"
        self.trajectories.mkdir()
        (self.trajectories / "demo.trajectory.md").write_text(
            "---\niterations: 2\nest_tokens: 100\n---\n"
        )
        self.env = dict(os.environ, ADF="fw", ADF_EVENTS_V1="1", ADF_EVAL_WRITE="1",
                        GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
                        GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
                        GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid",
                        TEST_SECRET=SECRET)
        for key in ("RUN_ID", "ADF_DIR", "BASH_ENV", "GIT_DIR", "GIT_WORK_TREE"):
            self.env.pop(key, None)
        self.cmd(["git", "init", "-q"])
        self.cmd(["git", "commit", "-q", "--allow-empty", "-m", "fixture"])
        self.obs = self.fw / "docs/observability"
        self.runs = self.obs / "runs"

    def cmd(self, args, **kwargs):
        return subprocess.run(args, cwd=self.repo, env=self.env, capture_output=True,
                              text=True, check=True, **kwargs)

    def run_case(self, run_id="first", case="demo", expected=0, **env):
        config = dict(self.env, **env)
        if run_id is not None:
            config["RUN_ID"] = run_id
        p = subprocess.run(["bash", str(self.fw / "hooks/eval-agent-flow.sh"), case],
                           cwd=self.repo, env=config, capture_output=True, text=True)
        self.assertEqual(p.returncode, expected, p.stdout + p.stderr)
        self.assertNotIn(SECRET, p.stdout + p.stderr)
        return p

    def events(self, run_id="first"):
        text = (self.runs / run_id / "events.jsonl").read_text()
        self.assertNotIn(SECRET, text)
        return [json.loads(line) for line in text.splitlines()]

    def module(self):
        spec = importlib.util.spec_from_file_location("run_events", self.fw / "hooks/run-events.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_00_real_pass(self):
        self.run_case()
        events = self.events()
        self.assertEqual([e["type"] for e in events],
                         ["run.started", "gate.started", "gate.finished", "run.completed"])
        self.assertEqual([e["sequence"] for e in events], [1, 2, 3, 4])
        self.assertEqual(len({e["event_id"] for e in events}), 4)
        for event in events:
            self.assertEqual(event["run_id"], "first")
            self.assertEqual(event["task_id"], "demo")
            self.assertEqual(event["schema_version"], "1.0")
            self.assertTrue(event["timestamp"].endswith("Z"))
            self.module().validate_event(event)
        gate = events[2]["payload"]
        self.assertEqual((gate["status"], gate["exit_code"]), ("pass", 0))
        self.assertEqual(gate["run_id"], "first")
        self.assertGreaterEqual(gate["duration_seconds"], 0)
        self.assertEqual(events[3]["payload"]["outcome"], "success")
        for field in ("tokens_in", "tokens_out", "cost_usd"):
            self.assertIsNone(events[3]["payload"][field])

    def test_fail_and_independent_runs(self):
        self.run_case()
        original = (self.runs / "first/events.jsonl").read_bytes()
        (self.fix / "solution.cjs").write_text("module.exports = 41;\n")
        self.run_case("second", expected=1)
        events = self.events("second")
        self.assertEqual(events[2]["payload"]["status"], "fail")
        self.assertNotEqual(events[2]["payload"]["exit_code"], 0)
        self.assertEqual(events[-1]["payload"]["outcome"], "failure")
        self.assertEqual((self.runs / "first/events.jsonl").read_bytes(), original)
        csv = (self.fw / "docs/evals/results.csv").read_text().splitlines()
        self.assertEqual(len(csv), 2)
        self.assertTrue(csv[1].endswith(",demo,no,2,100,fail"))
        self.assertEqual(len((self.obs / "events.jsonl").read_text().splitlines()), 2)

    def test_repeated_and_invalid_ids(self):
        self.run_case()
        original = (self.runs / "first/events.jsonl").read_bytes()
        self.run_case(expected=2)
        self.assertEqual((self.runs / "first/events.jsonl").read_bytes(), original)
        for bad in ("../escape", "/tmp/escape", ".", "..", "a/b", "", "x\nsecret"):
            with self.subTest(id=bad):
                self.run_case(bad, expected=2)
        for bad in ("../demo", "../../outside", "missing", "demo\nsecret"):
            with self.subTest(case=bad):
                self.run_case("unused", case=bad, expected=2)
        self.assertFalse((self.runs / "unused").exists())

    def test_generated_ids_and_all(self):
        self.run_case(case="--all", expected=2)
        self.assertFalse(self.runs.exists())
        self.run_case(None)
        self.run_case(None)
        self.assertEqual(len(list(self.runs.iterdir())), 2)
        shutil.copytree(self.fix, self.fix.parent / "other")
        shutil.copy(self.trajectories / "demo.trajectory.md", self.trajectories / "other.trajectory.md")
        self.run_case(None, case="--all")
        self.assertEqual(len(list(self.runs.iterdir())), 4)

    def test_make_case_is_data_not_shell(self):
        source = ROOT.parent / "Makefile.adf" if (ROOT.parent / "Makefile.adf").is_file() else ROOT.parent / "Makefile"
        shutil.copy(source, self.repo / "Makefile")
        self.cmd(["make", "ADF=fw", "CASE=demo", "eval-agent-flow"])
        for case in ("demo; touch injected", "demo`touch injected`"):
            with self.subTest(case=case):
                p = subprocess.run(["make", "ADF=fw", "CASE=" + case, "eval-agent-flow"],
                                   cwd=self.repo, env=self.env, capture_output=True, text=True)
                self.assertFalse((self.repo / "injected").exists(), "CASE executed shell code")
                self.assertNotEqual(p.returncode, 0)

    def test_missing_runtime(self):
        tools = self.repo / "bin"
        tools.mkdir()
        for name in ("bash", "python3", "git", "awk", "grep", "mktemp", "mv", "date", "mkdir", "dirname"):
            (tools / name).symlink_to(shutil.which(name))
        self.run_case(PATH=str(tools))
        events = self.events()
        gate = events[2]["payload"]
        self.assertEqual((gate["status"], gate["reason_code"], gate["exit_code"]),
                         ("skipped", "runtime_unavailable", None))
        self.assertEqual(events[-1]["payload"]["outcome"], "skipped")

    def test_legacy_and_all(self):
        self.run_case(ADF_EVENTS_V1="0")
        csv = (self.fw / "docs/evals/results.csv").read_bytes()
        first = json.loads((self.obs / "events.jsonl").read_text())
        self.assertFalse(self.runs.exists())
        self.run_case(case="--all", ADF_EVENTS_V1="0")
        self.assertEqual((self.fw / "docs/evals/results.csv").read_bytes(), csv)
        self.run_case()
        self.assertEqual((self.fw / "docs/evals/results.csv").read_bytes(), csv)
        legacy = [json.loads(s) for s in (self.obs / "events.jsonl").read_text().splitlines()]
        self.assertEqual(len(legacy), 3)
        for event in legacy:
            for key in first.keys() - {"timestamp", "duration_seconds"}:
                self.assertEqual(event[key], first[key])
        # ADF_DIR, not ADF, is the legacy reader's API.
        p = subprocess.run(["bash", str(self.fw / "hooks/observability.sh"), "summary"],
                           cwd=self.repo, env=dict(self.env, ADF_DIR="fw"),
                           capture_output=True, text=True, check=True)
        self.assertIn("events=3", p.stdout)

    def test_digest(self):
        # Framed manifest: relative UTF-8 name + NUL + SHA256(content) + newline.
        h = hashlib.sha256()
        for path in sorted(self.fix.rglob("*")):
            if path.is_file():
                h.update(path.relative_to(self.fix).as_posix().encode() + b"\0")
                h.update(hashlib.sha256(path.read_bytes()).hexdigest().encode() + b"\n")
        self.run_case()
        self.assertEqual(self.events()[2]["payload"]["input_digest"], h.hexdigest())

    def test_symlink_and_write_failure(self):
        outside = self.repo / "outside"
        outside.mkdir()
        self.obs.mkdir()
        self.runs.symlink_to(outside, target_is_directory=True)
        self.run_case(expected=2)
        self.assertEqual(list(outside.iterdir()), [])
        self.runs.unlink()
        self.runs.write_text("not a directory")
        self.run_case(expected=2)
        self.assertFalse((self.obs / "events.jsonl").exists())

    def test_incomplete_on_projection_error(self):
        self.obs.mkdir()
        (self.obs / "events.jsonl").mkdir()  # deterministic failure even under root
        self.run_case(expected=2)
        events = self.events()
        self.assertEqual([e["type"] for e in events],
                         ["run.started", "gate.started", "gate.finished"])
        self.assertNotIn("run.completed", [e["type"] for e in events])

    def test_symlink_replacement_during_gate(self):
        outside = self.repo / "outside"
        outside.write_text("untouched")
        target = self.runs / "first/events.jsonl"
        (self.fix / "test.js").write_text(
            "const fs = require('node:fs');\n"
            f"fs.unlinkSync({json.dumps(str(target))});\n"
            f"fs.symlinkSync({json.dumps(str(outside))}, {json.dumps(str(target))});\n"
        )
        self.run_case(expected=2)
        self.assertEqual(outside.read_text(), "untouched")
        self.assertFalse((self.obs / "events.jsonl").exists())

    def test_parent_symlink(self):
        outside = self.repo / "outside"
        outside.mkdir()
        self.obs.symlink_to(outside, target_is_directory=True)
        self.run_case(expected=2)
        self.assertEqual(list(outside.iterdir()), [])

    def test_sensitive_tool_output(self):
        (self.fix / "test.js").write_text(
            "console.log(process.env.TEST_SECRET); console.error(process.env.TEST_SECRET);\n"
        )
        self.run_case()
        self.events()

    def test_schema_examples_with_independent_validator(self):
        try:
            from jsonschema import Draft7Validator, FormatChecker
            from referencing import Registry, Resource
        except ImportError:
            self.skipTest("independent JSON Schema check: optional jsonschema unavailable")
        self.run_case()
        schemas = self.fw / "contracts/v1"
        event = json.loads((schemas / "run-event.schema.json").read_text())
        gate = json.loads((schemas / "gate-result.schema.json").read_text())
        for schema in (event, gate):
            Draft7Validator.check_schema(schema)
        # RefResolver leaks its scope once the gate.finished payload follows the cross-file
        # $ref, which makes the envelope's own definitions unresolvable; a registry does not.
        registry = Registry().with_resources([(schema["$id"], Resource.from_contents(schema)) for schema in (event, gate)])
        validator = Draft7Validator(event, registry=registry, format_checker=FormatChecker())
        examples = self.events()
        for example in examples:
            validator.validate(example)
            for field in example:
                invalid = copy.deepcopy(example); del invalid[field]
                self.assertFalse(validator.is_valid(invalid), field)
        for field, value in (("status", "unknown"), ("duration_seconds", -1),
                             ("schema_version", "2.0"), ("required", 1)):
            invalid = copy.deepcopy(examples[2]); invalid["payload"][field] = value
            self.assertFalse(validator.is_valid(invalid), field)
        invalid = copy.deepcopy(examples[2]); invalid["payload"] = examples[0]["payload"]
        self.assertFalse(validator.is_valid(invalid))
        for field, value in (("sequence", -1), ("schema_version", "2.0"), ("run_id", "unsafe\n")):
            invalid = copy.deepcopy(examples[0]); invalid[field] = value
            self.assertFalse(validator.is_valid(invalid))

    def test_null_and_zero_are_distinct(self):
        self.run_case()
        events = self.events()
        mod = self.module()
        for value in (None, 0):
            event = copy.deepcopy(events[2]); event["payload"]["duration_seconds"] = value
            mod.validate_event(event)
        event = copy.deepcopy(events[3]); event["payload"]["tokens_in"] = 0
        with self.assertRaises(ValueError):
            mod.validate_event(event)

    def test_failed_completion_append_preserves_prior_events(self):
        self.run_case()
        examples = self.events()
        mod = self.module()
        path = self.repo / "partial.jsonl"
        with path.open("wb", buffering=0) as stream:
            for event in examples[:3]:
                mod.append_event(stream, event)
            before = path.read_bytes()
            with patch.object(mod.os, "fsync", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    mod.append_event(stream, examples[-1])
            self.assertEqual(path.read_bytes(), before)

    def test_legacy_destination_symlink(self):
        self.obs.mkdir()
        outside = self.repo / "outside"
        outside.write_text("untouched")
        (self.obs / "events.jsonl").symlink_to(outside)
        self.run_case(expected=2)
        self.assertEqual(outside.read_text(), "untouched")
        self.assertEqual(len(self.events()), 3)

    def test_contract_negative_examples(self):
        self.run_case()
        examples = self.events()
        mod = self.module()
        for event in examples:
            mod.validate_event(event)
        mutations = [
            ("schema_version", "2.0"), ("sequence", -1), ("sequence", True),
            ("run_id", "../escape"), ("timestamp", "yesterday"), ("type", "unknown"),
            ("payload", examples[0]["payload"]),
        ]
        for key, value in mutations:
            invalid = copy.deepcopy(examples[2]); invalid[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                mod.validate_event(invalid)
        for key, value in (("status", "unknown"), ("duration_seconds", -1),
                           ("duration_seconds", float("nan")), ("required", 1),
                           ("schema_version", "2.0"), ("input_digest", "not-a-hash")):
            invalid = copy.deepcopy(examples[2]); invalid["payload"][key] = value
            with self.subTest(gate_field=key), self.assertRaises(ValueError):
                mod.validate_event(invalid)
        for example in examples:
            invalid = copy.deepcopy(example); del invalid["task_id"]
            with self.assertRaises(ValueError): mod.validate_event(invalid)
            invalid = copy.deepcopy(example); invalid["payload"]["secret"] = SECRET
            with self.assertRaises(ValueError): mod.validate_event(invalid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
