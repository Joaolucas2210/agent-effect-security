"""ADR 0028 slice 1b: a closed grammar of Bash read-equivalents; sensitive paths deny, anything the parser
cannot see through denies as ambiguous, unknown commands are not ADF's call. INC-07 is the reference case.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks/adf-read-hook.py"


def git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


class BashReadGrammarTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.home, self.repo = base / "adf-home", base / "proj"
        self.home.mkdir(); (self.repo / "config").mkdir(parents=True); (self.repo / "secrets").mkdir(); (self.repo / "src").mkdir()
        (self.repo / "config/.env").touch(); (self.repo / "secrets/token").touch(); (self.repo / "README.md").write_text("public"); (self.repo / "src/app.py").write_text("x")
        os.symlink(self.repo / "config/.env", self.repo / "link")
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "m@example.invalid"); git(self.repo, "config", "user.name", "m"); git(self.repo, "add", "-f", "."); git(self.repo, "commit", "-qm", "f")
        (self.home / "enabled-projects").write_text(f"{self.repo}\n")

    def bash(self, command, codex=False):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "sess-1b", "tool_input": {"command": command}, **({"cwd": str(self.repo)} if codex else {})}
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home.parent), "ADF_HOME": str(self.home), **({} if codex else {"CLAUDE_PROJECT_DIR": str(self.repo)})}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, cwd=str(self.repo), timeout=120)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        out = json.loads(result.stdout) if result.stdout.strip() else None
        return out["hookSpecificOutput"]["permissionDecisionReason"] if isinstance(out, dict) and "hookSpecificOutput" in out else out

    def deny(self, command, reason, **kw):
        got = self.bash(command, **kw); self.assertIsInstance(got, str, f"{command!r} should be denied, got {got!r}"); self.assertIn(reason, got, command)

    def test_read_equivalents_on_sensitive_paths_deny(self):
        for command in ("head config/.env", "tail -n 20 secrets/token", "sed -n 1,5p config/.env", "rg KEY config/.env", "grep -r AKIA secrets/", "grep -rn x ./secrets", "less link", "more ./link",
                        "head -- config/.env", "head 'config/.env'", 'head "config/.env"', "head README.md; head config/.env", "ls && tail secrets/token",
                        "awk '{print}' config/.env", "strings secrets/token", "xxd config/.env", "head src/../config/.env", "timeout 5 head config/.env", "env head config/.env", "nice -n 5 tail config/.env"):
            with self.subTest(command): self.deny(command, "uncovered_read_denied_sensitive")
        self.deny("head /tmp/anything/.ssh/id_rsa", "uncovered_read_denied_sensitive")  # sensitive components apply to any path, inside the root or not
        self.deny("cat README.md config/.env", "unsafe_read_command")  # multi-operand cat: the cat gate's own deny, unchanged
        self.assertEqual(self.bash("awk '{print $1}' README.md"), {}, "single-quoted $ is literal, not an expansion")

    def test_unparseable_read_shapes_are_ambiguous(self):
        for command in ("head $HOME/.env", "head ~/.env", "head `echo config/.env`", "head $(ls config)", "head config/*", "head config/.en?", "head < config/.env",
                        "python3 -c \"print(open('config/.env').read())\"", "python -c 'import sys; open(sys.argv[1])' config/.env", "node -e \"require('fs').readFileSync('config/.env')\"",
                        "bash -c 'head config/.env'", "sh -c \"tail secrets/token\"", "eval head config/.env", "find . -name '*.env' | xargs head", "head \"config/.env", "head -n $N config/.env"):
            with self.subTest(command): self.deny(command, "uncovered_bash_ambiguous")

    def test_benign_commands_are_not_adfs_call(self):
        for command in ("head README.md", "tail -f src/app.py", "grep -n def src/app.py", "rg TODO src", "sed -n 1p README.md", "ls -la", "npm test", "git status", "python3 -m pytest", "echo hello", "head -n 5 README.md src/app.py"):
            with self.subTest(command): self.assertEqual(self.bash(command), {}, command)

    def test_cat_gate_contract_is_preserved(self):
        self.assertIn("invalid_scope", self.bash("cat config/.env", codex=True), "single cat still goes through PDP and leaves a bundle")
        self.assertEqual(self.bash("cat README.md", codex=True), {})
        self.assertIn("unsafe_read_command", self.bash("cat README.md | wc", codex=True))
        bundles = [p for p in (self.home / "evidence").rglob("*.json")]
        self.assertEqual(len(bundles), 2, "cat decisions keep their bundles")

    def test_denies_are_journaled_without_the_command(self):
        self.deny("head config/.env", "uncovered_read_denied_sensitive"); self.deny("head $X", "uncovered_bash_ambiguous")
        journals = sorted((self.home / "evidence").rglob("_attempts/*.jsonl")); self.assertEqual(len(journals), 2)
        text = "".join(p.read_text() for p in journals)
        self.assertIn("uncovered_read_denied_sensitive", text); self.assertIn("uncovered_bash_ambiguous", text)
        self.assertNotIn("config/.env", text); self.assertNotIn("head", text)


if __name__ == "__main__": unittest.main(verbosity=2)
