"""Opt-in, local stdio MCP tool: the host holds the A2A bearer; the model only sees `read_via_adf(path)`.

The credential never enters the model context: no token pasted into a prompt, no env var the agent can
echo from its own tool. This process reads it from ADF_A2A_TOKEN_FILE (owner-only, absolute) and calls the
gateway at ADF_A2A_URL (loopback only, ADR 0013). A deny is a ToolError carrying the reason_code; a pause is
a ToolError carrying the task id and effect_binding, and there is deliberately no confirmation tool here:
the human confirms with a `human:confirm` token this process never holds (ADR 0018).
"""
import json
import os
import stat
import urllib.error
import urllib.request
import uuid

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations


mcp = MCPServer("adf-a2a-client")
SKILL = "read_workspace_file"


def _token():
    path = os.environ.get("ADF_A2A_TOKEN_FILE", "")
    if not os.path.isabs(path):
        raise ToolError("host_configuration_invalid")
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:  # symlink or group/world readable: refuse
            raise ToolError("host_configuration_invalid")
        with open(path, encoding="utf-8") as handle:
            token = handle.read().strip()
    except (OSError, UnicodeDecodeError):
        raise ToolError("host_configuration_invalid") from None
    if not token or any(char.isspace() for char in token):
        raise ToolError("host_configuration_invalid")
    return token


def _url():
    url = os.environ.get("ADF_A2A_URL", "")
    if not url.startswith("http://127.0.0.1:"):  # ponytail: TLS only via the host's proxy (A2A-8a), never from here
        raise ToolError("host_configuration_invalid")
    return url


def _reason(payload):
    """Stable reason_code from a JSON-RPC error or a 200 deny; never the body, never the token."""
    error = payload.get("error")
    if isinstance(error, dict):
        return str((error.get("data") or {}).get("reason_code") or "a2a_error")
    result = payload.get("result") or {}
    task = (result.get("task") or {}).get("id")
    binding = (result.get("audit") or {}).get("effect_binding")
    return str(result.get("reason_code") or "a2a_error") + (f" task={task} effect_binding={binding}" if task else "")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False), structured_output=False)
def read_via_adf(path: str) -> str:
    """Read one exact workspace path through the ADF A2A gateway; the bearer stays in this process."""
    token, url = _token(), _url()
    message = {"kind": "message", "role": "user", "messageId": uuid.uuid4().hex, "parts": [{"kind": "data", "data": {"skill": SKILL, "arguments": {"path": path}}}]}
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {"message": message}}).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read())
        except ValueError:
            raise ToolError("a2a_transport_error") from None
    except (urllib.error.URLError, OSError, ValueError):
        raise ToolError("a2a_transport_error") from None
    if not isinstance(payload, dict):
        raise ToolError("a2a_transport_error")
    result = payload.get("result") or {}
    if result.get("outcome") == "delivered" and isinstance(result.get("content"), str):
        return result["content"]
    raise ToolError(_reason(payload))
