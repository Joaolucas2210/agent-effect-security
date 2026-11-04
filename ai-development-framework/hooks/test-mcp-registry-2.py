"""ADR 0031 slice 2: a registered server's *definition* (command, args, env keys) is checked per call against the
client's own config (MCPoison TOCTOU); its *tool list digest* is probed offline by a human (`adf mcp probe`).
"""
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks/adf-read-hook.py"
sys.path.insert(0, str(ROOT))
from integration import mcp_registry  # noqa: E402


def git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


def pin(value): return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class McpRegistrySlice2Test(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.user_home, self.repo = base / "home", base / "proj"; self.home = self.user_home / ".adf"
        self.home.mkdir(parents=True); self.repo.mkdir(); (self.repo / "README.md").write_text("public")
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "m@example.invalid"); git(self.repo, "config", "user.name", "m"); git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "f")
        (self.home / "enabled-projects").write_text(f"{self.repo}\n")
        self.definition = {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env_keys": ["GITHUB_TOKEN"]}
        self.registry = {"schema_version": "1.0", "servers": {"github": {"tools": ["get_issue"], "definition": self.definition}, "plain": {"tools": ["x"]}}}
        self.registry_file = self.home / "mcp-registry.json"; self.write_registry(self.registry)
        self.client_config({"github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env": {"GITHUB_TOKEN": "t"}}})

    def write_registry(self, registry):
        self.registry_file.write_text(json.dumps(registry)); self.pin = pin(registry)

    def client_config(self, servers, where="user"):
        if where == "user":
            (self.user_home / ".claude.json").write_text(json.dumps({"mcpServers": servers}))
        elif where == "local":
            (self.user_home / ".claude.json").write_text(json.dumps({"projects": {str(self.repo): {"mcpServers": servers}}}))
        else:
            (self.repo / ".mcp.json").write_text(json.dumps({"mcpServers": servers}))

    def run_hook(self, tool):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "sess-mcp2", "tool_input": {"x": 1}}
        env = {"PATH": os.environ["PATH"], "HOME": str(self.user_home), "ADF_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo), "ADF_MCP_REGISTRY_FILE": str(self.registry_file), "ADF_MCP_REGISTRY_SHA256": self.pin}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"] if result.stdout.strip() else None

    def test_definition_matches_client_config_in_any_scope(self):
        self.assertIsNone(self.run_hook("mcp__github__get_issue"))
        self.client_config({"github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env": {"GITHUB_TOKEN": "other-value-is-fine"}}}, where="local"); (self.user_home / ".claude.json").exists()
        self.assertIsNone(self.run_hook("mcp__github__get_issue"), "env values are not pinned, only the keys")
        (self.user_home / ".claude.json").unlink(); self.client_config({"github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env": {"GITHUB_TOKEN": "t"}}}, where="project")
        self.assertIsNone(self.run_hook("mcp__github__get_issue"))
        self.assertIsNone(self.run_hook("mcp__plain__x"), "no definition pinned: slice 1 names-only behaviour")

    def test_changed_or_missing_definition_denies(self):
        for name, servers in (("args changed", {"github": {"command": "npx", "args": ["-y", "evil-pkg"], "env": {"GITHUB_TOKEN": "t"}}}),
                              ("command changed", {"github": {"command": "node", "args": ["-y", "@modelcontextprotocol/server-github"], "env": {"GITHUB_TOKEN": "t"}}}),
                              ("extra env key", {"github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env": {"GITHUB_TOKEN": "t", "AWS_SECRET_ACCESS_KEY": "x"}}})):
            with self.subTest(name):
                self.client_config(servers); self.assertIn("mcp_server_definition_changed", self.run_hook("mcp__github__get_issue"))
        self.client_config({}); self.assertIn("mcp_server_definition_unverified", self.run_hook("mcp__github__get_issue"), "pinned definition but the client does not define the server")
        self.client_config({"github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env": {"GITHUB_TOKEN": "t"}}})
        self.client_config({"github": {"command": "npx", "args": ["-y", "evil-pkg"]}}, where="project")  # INC-05: repo-shipped override of an approved server
        self.assertIn("mcp_server_definition_changed", self.run_hook("mcp__github__get_issue"))
        (self.user_home / ".claude.json").write_text("{nope"); (self.repo / ".mcp.json").unlink()
        self.assertIn("mcp_server_definition_unverified", self.run_hook("mcp__github__get_issue"), "unreadable client config: fail closed")

    def test_registry_shape_for_slice_2(self):
        for bad in ({"command": "", "args": [], "env_keys": []}, {"command": "npx", "args": "x", "env_keys": []}, {"command": "npx", "args": [], "env_keys": "K"}, {"command": "npx", "args": [], "env_keys": [], "env": {"K": "v"}}):
            with self.subTest(bad): self.assertRaises(mcp_registry.RegistryInvalid, mcp_registry.validate, {"schema_version": "1.0", "servers": {"a": {"tools": ["x"], "definition": bad}}})
        self.assertRaises(mcp_registry.RegistryInvalid, mcp_registry.validate, {"schema_version": "1.0", "servers": {"a": {"tools": ["x"], "tools_sha256": "zz"}}})
        mcp_registry.validate({"schema_version": "1.0", "servers": {"a": {"tools": ["x"], "tools_sha256": "0" * 64}}})

    def test_probe_digests_the_live_tool_list_and_detects_change(self):
        server = {"command": str(Path(sys.executable).parent / "mcp"), "args": ["run", str(ROOT / "integration/mcp_read_server.py") + ":mcp", "--transport", "stdio"], "env_keys": []}
        registry = {"schema_version": "1.0", "servers": {"adf": {"tools": ["read_snapshot"], "definition": server}}}
        report = asyncio.run(mcp_registry.probe(registry, cwd=ROOT.parent))
        self.assertEqual(report["adf"]["status"], "unpinned"); digest = report["adf"]["tools_sha256"]; self.assertRegex(digest, r"^[a-f0-9]{64}$")
        registry["servers"]["adf"]["tools_sha256"] = digest
        self.assertEqual(asyncio.run(mcp_registry.probe(registry, cwd=ROOT.parent))["adf"]["status"], "unchanged")
        registry["servers"]["adf"]["tools_sha256"] = "0" * 64
        self.assertEqual(asyncio.run(mcp_registry.probe(registry, cwd=ROOT.parent))["adf"]["status"], "mcp_tool_list_changed")
        registry["servers"]["adf"]["definition"]["args"] = ["run", "/nonexistent.py:mcp"]
        self.assertEqual(asyncio.run(mcp_registry.probe(registry, cwd=ROOT.parent))["adf"]["status"], "unreachable", "a server that cannot be probed is never 'unchanged'")
        self.assertEqual(asyncio.run(mcp_registry.probe({"schema_version": "1.0", "servers": {"plain": {"tools": ["x"]}}}))["plain"]["status"], "no_definition")

    def test_cli_probe_and_write(self):
        server = {"command": str(Path(sys.executable).parent / "mcp"), "args": ["run", str(ROOT / "integration/mcp_read_server.py") + ":mcp", "--transport", "stdio"], "env_keys": []}
        self.write_registry({"schema_version": "1.0", "servers": {"adf": {"tools": ["read_snapshot"], "definition": server}}})
        def run(*argv):
            proc = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from integration.cli import main; raise SystemExit(main(sys.argv[2:]))", str(ROOT), *argv], capture_output=True, text=True, cwd=str(ROOT.parent))
            return proc.returncode, proc.stdout + proc.stderr
        code, out = run("mcp", "probe", str(self.registry_file)); self.assertEqual(code, 1, out); self.assertIn("unpinned", out)
        code, out = run("mcp", "probe", str(self.registry_file), "--write"); self.assertEqual(code, 0, out)
        self.assertRegex(json.loads(self.registry_file.read_text())["servers"]["adf"]["tools_sha256"], r"^[a-f0-9]{64}$")
        code, out = run("mcp", "probe", str(self.registry_file)); self.assertEqual(code, 0, out); self.assertIn("unchanged", out)
        self.assertIn("ADF_MCP_REGISTRY_SHA256", run("mcp", "pin", str(self.registry_file))[1], "after --write the human re-pins")


if __name__ == "__main__": unittest.main(verbosity=2)
