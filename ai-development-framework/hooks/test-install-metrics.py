"""Portable installation must preserve the host repo and start with clean metrics."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "Makefile.adf" if (ROOT / "Makefile.adf").is_file() else ROOT / "Makefile"


class InstallMetricsTest(unittest.TestCase):
    def test_make_install_preserves_host_files_and_refuses_reinstallation(self):
        with tempfile.TemporaryDirectory(prefix="adf install ") as directory:
            dest = Path(directory)
            originals = {name: f"host {name}\n" for name in ("Makefile", "AGENTS.md", "LICENSE", ".gitignore", "VERSION")}
            for name, content in originals.items():
                (dest / name).write_text(content)
            command = ["make", "-s", "-f", str(MAKEFILE), "install-metrics"]
            env = dict(os.environ, DEST=str(dest))
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            core = dest / "ai-development-framework"
            self.assertTrue((core / "hooks/run-local-evidence-trial.py").is_file())
            self.assertTrue((dest / "Makefile.adf").is_file())
            self.assertTrue((core / "docs/specs/agent-development-harness.md").is_file())
            self.assertFalse((dest / ".codex/hooks.json").exists())
            license_source = ROOT / "ai-development-framework/LICENSE"
            if not license_source.is_file():
                license_source = ROOT / "LICENSE"
            self.assertEqual((core / "LICENSE").read_text(), license_source.read_text())
            for name, content in originals.items():
                self.assertEqual((dest / name).read_text(), content)
            for name in ("evidence", "trials", "runs", "trajectories", "events.jsonl"):
                self.assertFalse((core / "docs/observability" / name).exists(), name)
            for name in ("docs/metrics/history.csv", "docs/evals/results.csv"):
                self.assertEqual(len((core / name).read_text().splitlines()), 1)
            summary = subprocess.run(["make", "-s", "-f", "Makefile.adf", "metrics"], cwd=dest, capture_output=True, text=True)
            self.assertEqual(summary.returncode, 0, summary.stderr)
            self.assertIn("events=0", summary.stdout)
            self.assertIn("eval_runs=0", summary.stdout)
            marker = core / "installed-marker"
            marker.write_text("keep")
            repeated = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertNotEqual(repeated.returncode, 0)
            legacy = subprocess.run(["make", "-s", "-f", str(MAKEFILE), "install-into"], cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertNotEqual(legacy.returncode, 0)
            self.assertEqual(marker.read_text(), "keep")
            for name, content in originals.items():
                self.assertEqual((dest / name).read_text(), content)

    def test_invalid_destination_and_symlink_conflicts_fail_before_copying(self):
        command = ["make", "-s", "-f", str(MAKEFILE), "install-metrics"]
        for value in ("", str(ROOT), str(ROOT / "does-not-exist")):
            result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, DEST=value), capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, value)
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory)
            (dest / "Makefile.adf").symlink_to(dest / "missing")
            result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, DEST=str(dest)), capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((dest / "ai-development-framework").exists())

    def test_source_secrets_caches_and_old_proposals_are_excluded(self):
        spec = importlib.util.spec_from_file_location("install_metrics", ROOT / "ai-development-framework/hooks/install-metrics.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as directory:
            source, dest = Path(directory) / "source", Path(directory) / "dest"
            source.mkdir(); dest.mkdir()
            (source / "Makefile").write_text("# fixture")
            (source / "LICENSE").write_text("fixture license")
            (source / "VERSION").write_text("0.1.0")
            core = source / "ai-development-framework"
            for name in (".env", "nested/.env.local", "__pycache__/cache.pyc", "docs/traces/proposals/failure.md", "docs/traces/proposals/TEMPLATE.md"):
                path = core / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
            for path, text in ((source / "docs/specs/agent-development-harness.md", "host document"), (core / "docs/specs/agent-development-harness.md", "packaged specification")):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            with patch.object(installer, "ROOT", source):
                installer.install(dest)
            copied = dest / "ai-development-framework"
            self.assertTrue((copied / "docs/traces/proposals/TEMPLATE.md").exists())
            self.assertFalse((copied / "docs/traces/proposals/failure.md").exists())
            self.assertFalse(list(copied.rglob(".env*")))
            self.assertFalse(list(copied.rglob("*.pyc")))
            self.assertEqual((copied / "docs/specs/agent-development-harness.md").read_text(), "packaged specification")

    def test_installed_runner_captures_and_aggregates_a_separate_git_repository(self):
        with tempfile.TemporaryDirectory(prefix="adf-trial-") as directory:
            dest = Path(directory).resolve()
            def run(*args, env=None):
                result = subprocess.run(args, cwd=dest, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result
            for args in (("init", "-q"), ("config", "user.email", "trial@example.invalid"), ("config", "user.name", "Trial")):
                run("git", *args)
            (dest / "README.md").write_text("Public trial fixture\n")
            run("git", "add", "README.md")
            run("git", "commit", "-qm", "fixture")
            installed = subprocess.run(["make", "-s", "-f", str(MAKEFILE), "install-metrics"], cwd=ROOT, env=dict(os.environ, DEST=str(dest)), capture_output=True, text=True)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            core = dest / "ai-development-framework"
            # Use installed dependencies, but import the vendored code, not the source clone.
            env = dict(os.environ, PYTHONPATH=str(core))
            run("make", "-s", "-f", "Makefile.adf", "local-evidence-trial", "TRIAL_ID=smoke-fixture", env=env)
            import json
            smoke = json.loads((core / "docs/observability/trials/smoke-fixture.json").read_text())
            self.assertEqual((smoke["reads_total"], smoke["bundles_total"]), (5, 4))
            evidence = core / "docs/observability/evidence/session-fixture"
            evidence.mkdir()
            revision = run("git", "rev-parse", "HEAD").stdout.strip()
            gate_env = dict(env, ADF_TRUSTED_REPOSITORY=str(dest), ADF_TRUSTED_REVISION=revision, ADF_EVIDENCE_DIR=str(evidence), ADF_CAPTURE_TIMINGS="1")
            payload = {"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": "session-fixture", "tool_input": {"file_path": str(dest / "README.md")}}
            python = os.environ.get("ADF_CONTRACTS_PYTHON", "python3")
            gate = subprocess.run([python, str(core / "hooks/claude-code-read-gate.py")], cwd=dest, env=gate_env, input=json.dumps(payload), capture_output=True, text=True)
            self.assertEqual(gate.returncode, 0, gate.stderr)
            self.assertEqual(json.loads(gate.stdout)["hookSpecificOutput"]["permissionDecision"], "allow", gate.stdout)
            run("make", "-s", "-f", "Makefile.adf", "local-evidence-trial", f"EVIDENCE_DIR={evidence}", "TRIAL_ID=session-fixture", env=env)
            report = json.loads((core / "docs/observability/trials/session-fixture.json").read_text())
            self.assertEqual((report["source"]["kind"], report["source"]["latency_recorded"]), ("persisted_evidence", False))
            self.assertEqual((report["reads_total"], report["bundles_total"], report["metrics"]["evidence_bundle_valid_total"]), (1, 1, 1))
            run("make", "-s", "-f", "Makefile.adf", "local-session-trial",
                f"EVIDENCE_DIR={evidence}", "TRIAL_ID=portable-v2", "TASK_ID=read-fixture", "SESSION_ID=session-fixture",
                "AGENT_NAME=other", "AGENT_VERSION=host-gate-test-1.0", f"REVISION_SHA={revision}", "ACCEPTANCE_SHA256=" + "a" * 64, env=env)
            target = core / "docs/observability/trials/portable-v2-session-fixture.v2.json"
            session = json.loads(target.read_text())
            self.assertEqual((session["attempts_observed_total"], session["bundles_valid_total"], session["timings"]["observed_total"]), (1, 1, 1))
            self.assertEqual(session["provenance"], {"agent_name": "other", "agent_version": "host-gate-test-1.0", "revision_sha": revision, "acceptance_sha256": "a" * 64})
            self.assertIsNone(session["task_outcome"])
            self.assertEqual(set(session["durations_ms"].values()), {None})
            self.assertEqual(session["timings"]["stages"]["total"]["count"], 1)
            self.assertNotIn("Public trial fixture", target.read_text())
            self.assertNotIn(str(dest), target.read_text())
            run(python, "-c", "import json, integration.session_trial as s; from pathlib import Path; assert Path(s.__file__).is_relative_to(Path('ai-development-framework').resolve()); assert s.verify_session_report(json.loads(Path('" + str(target.relative_to(dest)) + "').read_text()))", env=env)
            partial = subprocess.run(["make", "-s", "-f", "Makefile.adf", "local-session-trial",
                f"EVIDENCE_DIR={evidence}", "TRIAL_ID=partial-v2", "TASK_ID=read-fixture", "SESSION_ID=session-fixture", "AGENT_NAME=other"], cwd=dest, env=env, capture_output=True, text=True, check=False)
            self.assertNotEqual(partial.returncode, 0)
            self.assertFalse((core / "docs/observability/trials/partial-v2-session-fixture.v2.json").exists())
            run("bash", str(core / "hooks/test-packaging.sh"), env=env)
            for name in ("codex-bash-read-gate", "contracts-v1", "local-evidence-pilot-ci", "maintenance-routine", "run-events"):
                with self.subTest(portable_self_test=name):
                    run("bash", str(core / "hooks" / f"test-{name}.sh"), env=env)
            deployment = subprocess.run([python, str(core / "hooks/check-host-deployment.py")], cwd=dest, env=env, capture_output=True, text=True, check=False)
            self.assertEqual(deployment.returncode, 77)
            self.assertEqual(deployment.stdout.count("skipped:"), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
