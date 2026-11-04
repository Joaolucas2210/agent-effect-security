"""ADR 0028 1b, second pass (pilot findings 3 and 8): segments split only outside quotes; options that take an
argument do not turn it into a path; explicit pattern options (-e/-f) make every positional a path; a pattern
file (-f) is itself a read. Deny-only: nothing here admits.
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


class BashGrammar2Test(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve(); self.home, self.repo = base / "adf-home", base / "proj"
        self.home.mkdir(); (self.repo / "config").mkdir(parents=True); (self.repo / "secrets").mkdir(); (self.repo / "src").mkdir()
        for rel in ("config/.env", "secrets/token", "secrets/prog.awk", "README.md", "src/app.py", "patterns.txt", "prog.awk"): (self.repo / rel).touch()
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "m@example.invalid"); git(self.repo, "config", "user.name", "m"); git(self.repo, "add", "-f", "."); git(self.repo, "commit", "-qm", "f")
        (self.home / "enabled-projects").write_text(f"{self.repo}\n")

    def bash(self, command):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "sess-1b2", "tool_input": {"command": command}}
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home.parent), "ADF_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo)}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, cwd=str(self.repo), timeout=120)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        out = json.loads(result.stdout) if result.stdout.strip() else None
        return out["hookSpecificOutput"]["permissionDecisionReason"] if isinstance(out, dict) and "hookSpecificOutput" in out else out

    def passes(self, *commands):
        for command in commands:
            with self.subTest(command): self.assertEqual(self.bash(command), {}, command)

    def denies(self, reason, *commands):
        for command in commands:
            with self.subTest(command):
                got = self.bash(command); self.assertIsInstance(got, str, f"{command!r} should be denied, got {got!r}"); self.assertIn(reason, got)

    def test_separators_inside_quotes_are_not_segments(self):
        self.passes('grep -n "a|b" README.md', "grep -n 'x;y' src/app.py", 'echo "x; head config/.env"', "echo 'a && tail secrets/token'", 'grep -e "secret\\|token" src/app.py', 'rg "foo|bar" src', 'awk \'{ print $1 }\' README.md', 'printf "%s\\n" "a|b"')
        self.denies("uncovered_read_denied_sensitive", 'grep -n "a|b" config/.env', "echo done; head config/.env", "true && tail secrets/token", 'grep "x" README.md | head secrets/token')
        self.denies("uncovered_bash_ambiguous", 'grep -n "unterminated README.md', "head 'x README.md")

    def test_option_arguments_are_not_paths_and_pattern_options_make_positionals_paths(self):
        self.passes("grep -e secret -e token src/app.py", "grep --regexp=secret --regexp=token src/app.py", 'grep -e "a*b" README.md', "grep -m 1 -A 2 -B 2 -C 1 KEY README.md", "grep --include=*.py -r TODO src", "grep -d skip x README.md",
                    "rg -e foo -e bar src", "rg -g '*.py' TODO src", "rg -t py TODO .", "rg --type=py -m 5 TODO src", "sed -e 's/a/b/' README.md", "sed -n -e 1p -e 3p README.md", "sed --expression=s/a/b/ README.md",
                    "awk -F : '{print $1}' README.md", "awk -v x=1 '{print x}' README.md", "head -n 5 README.md", "tail -n +2 README.md", "cut -d , -f 1 README.md", "sort -k 2 -t , README.md", "od -j 4 -N 16 README.md", "xxd -l 16 -s 8 README.md", "strings -n 8 README.md")
        self.denies("uncovered_read_denied_sensitive", "grep -e x -e y config/.env", "grep --regexp=x secrets/token", "rg -e KEY config/.env", "rg -g '*.py' TODO secrets", "sed -e s/a/b/ config/.env", "sed -n -e 1p secrets/token", "awk -F : '{print $1}' config/.env",
                    "grep -A 2 -e x secrets/token", "cut -d , -f 1 secrets/token", "tail -n +2 config/.env")

    def test_pattern_and_program_files_are_reads(self):
        self.passes("grep -f patterns.txt README.md", "grep --file=patterns.txt README.md", "rg -f patterns.txt src", "sed -f patterns.txt README.md", "awk -f prog.awk README.md")
        self.denies("uncovered_read_denied_sensitive", "grep -f config/.env README.md", "grep --file=secrets/token README.md", "rg -f secrets/token src", "sed -f secrets/token README.md", "awk -f secrets/prog.awk README.md", "sort -o secrets/out README.md")

    def test_globs_still_ambiguous_only_in_path_operands(self):
        self.denies("uncovered_bash_ambiguous", "grep x *.py", "head config/*", "sed -n 1p src/?.py")
        self.passes("grep 'a*' README.md", "rg -g '**/*.py' TODO src", "grep --include='*.py' x src")


if __name__ == "__main__": unittest.main(verbosity=2)
