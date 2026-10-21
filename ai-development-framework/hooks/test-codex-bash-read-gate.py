"""Codex Bash-read gate checks against a real local adapter and evidence bundle."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("codex_bash_read_gate", ROOT / "hooks/codex-bash-read-gate.py")
gate = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(gate)


class CodexGateTest(unittest.TestCase):
    def test_parser(self):
        for command, expected in (("cat README.md", "README.md"), ("cat -- docs/a-b.txt", "docs/a-b.txt"), (" ls", None), ("rm file", None), ("python -c 'print(1)'", None)):
            self.assertEqual(gate.parse_read_equivalent_bash(command), expected)
        for command in ("cat", "cat -", "cat a b", "cat file|", "cat file | wc", "cat > out", "cat $(echo file)", "cat *.md", "cat 'file'", "cat file; rm x", "cat file\nrm x", "cat /etc/passwd > out", "ls && cat README.md", "/bin/cat README.md", "env cat README.md"):
            with self.subTest(command=command), self.assertRaises(ValueError): gate.parse_read_equivalent_bash(command)

    def test_hook_payloads(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"; repo.mkdir(); repo = repo.resolve()
            (repo / "README.md").write_text("public-content", encoding="utf-8")
            (repo / ".env").write_text("secret-content", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "p4@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "P4"], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "initial"], check=True)
            evidence = Path(temp) / "evidence"
            env = {"ADF_TRUSTED_REPOSITORY": str(repo), "ADF_TRUSTED_REVISION": "HEAD", "ADF_EVIDENCE_DIR": str(evidence), "ADF_MAX_OUTPUT_BYTES": "64"}
            base = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "codex-p4", "tool_input": {"command": f"cat {repo / 'README.md'}"}}
            with patch.dict(os.environ, env):
                self.assertEqual(gate.gate(base), {})
                self.assertEqual(len(list((evidence / "codex-p4").glob("*.json"))), 1)
                self.assertEqual(gate.gate({**base, "tool_input": {"command": "cat README.md", "workdir": str(repo), "description": "Read the file", "max_output_tokens": 100}}), {})
                self.assertEqual(len(list((evidence / "codex-p4").glob("*.json"))), 2)
                for command, code in ((f"cat {repo / '.env'}", "invalid_referenced_contract"), ("cat /etc/passwd", "path_outside_trusted_root"), ("cat README.md | wc", "unsafe_read_command")):
                    output = gate.gate({**base, "tool_input": {"command": command}})["hookSpecificOutput"]
                    self.assertEqual(output["permissionDecision"], "deny")
                    self.assertIn(code, output["permissionDecisionReason"])
                    self.assertNotIn("secret-content", json.dumps(output))
                self.assertEqual(gate.gate({**base, "tool_input": {"command": "pnpm test"}}), {})
                self.assertEqual(gate.gate({**base, "tool_name": "apply_patch"}), {})
                injected = gate.gate({**base, "tool_input": {"command": base["tool_input"]["command"], "ADF_TRUSTED_REPOSITORY": "/etc"}})["hookSpecificOutput"]
                self.assertEqual(injected["permissionDecision"], "deny")
                self.assertIn("unexpected_tool_input", injected["permissionDecisionReason"])
                self.assertIn("path_outside_trusted_root", gate.gate({**base, "tool_input": {"command": "cat README.md", "workdir": str(Path(temp))}})["hookSpecificOutput"]["permissionDecisionReason"])
            with patch.dict(os.environ, {"ADF_TRUSTED_REPOSITORY": "", "ADF_EVIDENCE_DIR": ""}):
                self.assertIn("host_configuration_invalid", gate.gate(base)["hookSpecificOutput"]["permissionDecisionReason"])
            process = subprocess.run([sys.executable, str(ROOT / "hooks/codex-bash-read-gate.py")], input=json.dumps(base), text=True, capture_output=True, cwd=repo, env={**os.environ, **env})
            self.assertEqual(process.returncode, 0)
            self.assertEqual(json.loads(process.stdout), {})
            self.assertEqual(process.stderr, "")
            relative = subprocess.run([sys.executable, str(ROOT / "hooks/codex-bash-read-gate.py")], input=json.dumps({**base, "tool_input": {"command": "cat README.md"}}), text=True, capture_output=True, cwd=repo, env={**os.environ, **env})
            self.assertEqual(json.loads(relative.stdout), {})
            # The packaged wrapper works without installing a host hooks.json.
            hooks = repo / "ai-development-framework/hooks"; hooks.mkdir(parents=True)
            for name in ("codex-bash-read-gate.py", "codex-bash-read-gate.wrapper.sh"):
                shutil.copy2(ROOT / "hooks" / name, hooks / name)
            python_dir = repo / ".venv/bin"; python_dir.mkdir(parents=True)
            (python_dir / "python3").symlink_to(sys.executable)
            wrapper_env = {key: value for key, value in os.environ.items() if not key.startswith("ADF_")}
            wrapper_env["ADF_EVIDENCE_DIR"] = str(evidence)
            wrapper_env["PYTHONPATH"] = os.pathsep.join(sys.path)  # fixture reuses the runner's installed packages
            wrapper = subprocess.run(["bash", str(hooks / "codex-bash-read-gate.wrapper.sh")], input=json.dumps({**base, "session_id": "wrapper-check"}), text=True, capture_output=True, cwd=hooks, env=wrapper_env)
            self.assertEqual(wrapper.returncode, 0, wrapper.stderr)
            self.assertEqual(json.loads(wrapper.stdout), {})
            self.assertEqual(len(list((evidence / "wrapper-check").glob("*.json"))), 1)
            configured = ROOT.parent / ".codex/hooks.json"
            if configured.is_file():
                config = json.loads(configured.read_text())
                commands = [hook["command"] for group in config["hooks"]["PreToolUse"] for hook in group["hooks"] if "codex-bash-read-gate" in hook.get("command", "")]
                for command in commands:
                    deployed = subprocess.run(command, shell=True, input=json.dumps({**base, "session_id": "deployed-check"}), text=True, capture_output=True, cwd=hooks, env=wrapper_env, check=False)
                    self.assertEqual(deployed.returncode, 0, deployed.stderr)
                    self.assertEqual(json.loads(deployed.stdout), {})
                    self.assertEqual(len(list((evidence / "deployed-check").glob("*.json"))), 1)
            for forbidden in ("import subprocess", "from subprocess", "socket", "urllib", "http.client", "requests"):
                self.assertNotIn(forbidden, (ROOT / "hooks/codex-bash-read-gate.py").read_text().lower())


if __name__ == "__main__": unittest.main(verbosity=2)
