"""The host-side A2A client: the model gets read_via_adf(path) and never the bearer (credential outside the model)."""
import asyncio
import json
import os
import secrets
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import integration.a2a_gateway as a2a
import integration.local_read_adapter as adapter_module

ROOT = Path(__file__).resolve().parent.parent
ISSUER, AUDIENCE, PUBLIC, SECRET, APPROVED = "adf-test-idp", "adf-a2a-local", "public readme text", "SECRET-NEVER-LEAVES", "docs/readme.md"


def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


class McpA2AClientTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.repo = base / "source"; (self.repo / "docs").mkdir(parents=True); (self.repo / "config").mkdir()
        (self.repo / APPROVED).write_text(PUBLIC); (self.repo / "config/.env").write_text(SECRET)
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "t@example.invalid"); git(self.repo, "config", "user.name", "t")
        git(self.repo, "add", "-f", "."); git(self.repo, "commit", "-qm", "fixture")
        request = adapter_module.build_request({"snapshot_digest": "a" * 64}, "run-a2a", APPROVED, 64)
        config = {"schema_version": "1.0", **{key: request[key] for key in ("profiles", "policy", "context")}}
        policy = base / "host-policy.json"; policy.write_text(json.dumps(config))
        self.secret = secrets.token_bytes(32)
        self.common = {"validator": a2a.HS256TokenValidator(self.secret, ISSUER, AUDIENCE), "trusted_repository": self.repo, "trusted_revision": "HEAD", "evidence_dir": base / "evidence", "host_policy_path": str(policy), "host_policy_sha256": adapter_module.digest(config), "max_output_bytes": 64, "port": 0}
        self.server = self.serve(a2a.A2AGateway(**self.common))
        self.token_file = base / "token"; self.token_file.write_text(self.mint()); self.token_file.chmod(0o600)
        self.env = {"ADF_A2A_TOKEN_FILE": str(self.token_file), "ADF_A2A_URL": f"http://127.0.0.1:{self.server.server_address[1]}/"}

    def serve(self, gateway):
        server = a2a.make_server(gateway, "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start(); self.addCleanup(self.stop, server)
        return server

    def stop(self, server): server.shutdown(); server.server_close()

    def mint(self, exp=300, scope="workspace:read"):
        return a2a.mint_hs256({"iss": ISSUER, "aud": AUDIENCE, "sub": "agent-alpha", "exp": int(time.time()) + exp, "scope": scope}, self.secret)

    def call(self, path, env=None):
        from mcp import Client
        from integration.mcp_a2a_client import mcp

        async def exercise():
            async with Client(mcp) as client:
                tools = [tool.name for tool in (await client.list_tools()).tools]
                self.assertEqual(tools, ["read_via_adf"], "no confirmation tool exists here, by design")
                return await client.call_tool("read_via_adf", {"path": path})
        with patch.dict(os.environ, self.env if env is None else env, clear=True):
            result = asyncio.run(exercise())
        text = (result.content[0].text if result.content else "").removeprefix("Error executing tool read_via_adf: ")
        token = self.token_file.read_text().strip()
        if token: self.assertNotIn(token, text, "the bearer never reaches the model")
        self.assertNotIn(SECRET, text)
        return result.is_error, text

    def test_delivered_denied_and_paused_without_the_token(self):
        self.assertEqual(self.call(APPROVED), (False, PUBLIC))
        error, text = self.call("config/.env")
        self.assertTrue(error); self.assertIn("invalid_scope", text)
        error, text = self.call("docs/other.md")
        self.assertTrue(error); self.assertIn("scope_not_allowlisted", text)
        self.stop(self.server); self.server = self.serve(a2a.A2AGateway(**self.common, confirm_skills=frozenset({"read_workspace_file"})))
        self.env["ADF_A2A_URL"] = f"http://127.0.0.1:{self.server.server_address[1]}/"
        error, text = self.call(APPROVED)
        self.assertTrue(error); self.assertIn("input_required task=", text); self.assertIn("effect_binding=", text); self.assertNotIn(PUBLIC, text)

    def test_authn_and_transport_failures_are_reason_codes(self):
        self.token_file.write_text(self.mint(exp=-10))
        self.assertEqual(self.call(APPROVED)[1], "token_expired")
        self.token_file.write_text(self.mint(scope="other:scope"))
        self.assertEqual(self.call(APPROVED)[1], "insufficient_scope")
        self.token_file.write_text("not-a-jwt")
        self.assertTrue(self.call(APPROVED)[1].startswith("token_"))
        self.stop(self.server)
        self.assertEqual(self.call(APPROVED)[1], "a2a_transport_error")

    def test_host_configuration_is_refused_when_unsafe(self):
        cases = {"missing token file": {**self.env, "ADF_A2A_TOKEN_FILE": str(self.token_file) + ".missing"}, "relative token path": {**self.env, "ADF_A2A_TOKEN_FILE": "token"},
                 "no url": {k: v for k, v in self.env.items() if k != "ADF_A2A_URL"}, "non-loopback url": {**self.env, "ADF_A2A_URL": "http://10.0.0.5:8765/"}, "https elsewhere": {**self.env, "ADF_A2A_URL": "https://example.invalid/"}}
        for label, env in cases.items():
            with self.subTest(label=label): self.assertEqual(self.call(APPROVED, env), (True, "host_configuration_invalid"))
        self.token_file.chmod(0o644)
        self.assertEqual(self.call(APPROVED), (True, "host_configuration_invalid"), "group/world readable token file is refused")
        self.token_file.chmod(0o600); link = self.token_file.with_name("link"); link.symlink_to(self.token_file)
        self.assertEqual(self.call(APPROVED, {**self.env, "ADF_A2A_TOKEN_FILE": str(link)}), (True, "host_configuration_invalid"))
        self.token_file.write_text("")
        self.assertEqual(self.call(APPROVED), (True, "host_configuration_invalid"))

    def test_source_never_reads_the_token_from_argv_or_env_value(self):
        source = (ROOT / "integration/mcp_a2a_client.py").read_text()
        for forbidden in ("sys.argv", "ADF_A2A_TOKEN\"", "ADF_A2A_TOKEN'", "subprocess", "print("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__": unittest.main(verbosity=2)
