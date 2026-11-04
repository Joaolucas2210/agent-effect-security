"""ADR 0031 slice 1: host-pinned registry of MCP server and tool *names*.

Opt-in like the host policy (ADR 0011): `ADF_MCP_REGISTRY_FILE` + `ADF_MCP_REGISTRY_SHA256` (json-c14n-v1 pin).
Both unset -> no decision. One unset, a wrong pin, a swapped file or any shape outside the closed schema ->
`mcp_registry_invalid` and every MCP call is denied. Descriptions, annotations and schemas are not in the
registry: they authorize nothing (`cannot_authorize`). Slice 2 (tool-list digest) needs the live list, which
the PreToolUse payload does not carry.
"""
import hashlib
import json
import os
import re
from pathlib import Path

from integration.local_evidence_bundle import digest

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")
_TOOL = re.compile(r"mcp__([A-Za-z0-9][A-Za-z0-9_.-]{0,119})__([A-Za-z0-9][A-Za-z0-9_.-]{0,119})\Z")
_HASH = re.compile(r"[a-f0-9]{64}\Z")


class RegistryInvalid(ValueError):
    pass


def validate(registry):
    """Closed shape: {schema_version: "1.0", servers: {name: {tools: [name, ...]}}}."""
    if not isinstance(registry, dict) or set(registry) != {"schema_version", "servers"} or registry["schema_version"] != "1.0" or not isinstance(registry["servers"], dict):
        raise RegistryInvalid("mcp_registry_invalid")
    for server, entry in registry["servers"].items():
        if not _NAME.fullmatch(server) or not isinstance(entry, dict) or not {"tools"} <= set(entry) <= {"tools", "definition", "tools_sha256"} or not isinstance(entry["tools"], list) or not all(isinstance(tool, str) and _NAME.fullmatch(tool) for tool in entry["tools"]):
            raise RegistryInvalid("mcp_registry_invalid")
        definition = entry.get("definition")
        if definition is not None and not (isinstance(definition, dict) and set(definition) == {"command", "args", "env_keys"} and isinstance(definition["command"], str) and definition["command"] and isinstance(definition["args"], list) and all(isinstance(a, str) for a in definition["args"]) and isinstance(definition["env_keys"], list) and all(isinstance(k, str) and k for k in definition["env_keys"])):
            raise RegistryInvalid("mcp_registry_invalid")
        if "tools_sha256" in entry and not (isinstance(entry["tools_sha256"], str) and _HASH.fullmatch(entry["tools_sha256"])):
            raise RegistryInvalid("mcp_registry_invalid")
    return registry


def _normalise(server):
    """Client config entry -> the pinned shape: command, args, sorted env *keys* (values are secrets, never pinned)."""
    if not isinstance(server, dict) or not isinstance(server.get("command"), str):
        return None
    args, env = server.get("args") or [], server.get("env") or {}
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args) or not isinstance(env, dict):
        return None
    return {"command": server["command"], "args": list(args), "env_keys": sorted(str(k) for k in env)}


def client_definitions(name, root, home):
    """Every definition of `name` the Claude Code client would load: user scope and local scope in ~/.claude.json,
    project scope in <root>/.mcp.json. Unreadable config -> None (unverified), never 'absent'."""
    found = []
    try:
        user_file = Path(home) / ".claude.json"
        if user_file.exists():
            data = json.loads(user_file.read_text(encoding="utf-8"))
            for scope in (data.get("mcpServers") or {}, ((data.get("projects") or {}).get(str(root)) or {}).get("mcpServers") or {}):
                if name in scope:
                    found.append(_normalise(scope[name]))
        project_file = Path(root) / ".mcp.json"
        if project_file.exists():
            scope = json.loads(project_file.read_text(encoding="utf-8")).get("mcpServers") or {}
            if name in scope:
                found.append(_normalise(scope[name]))
    except (OSError, ValueError, AttributeError, TypeError):
        return None
    return found


def check_definition(name, entry, root, home):
    """-> None (ok or nothing pinned) or a reason code. Every definition the client could load must equal the pin."""
    pinned = entry.get("definition")
    if pinned is None:
        return None
    found = client_definitions(name, root, home)
    if not found:
        return "mcp_server_definition_unverified"
    expected = {"command": pinned["command"], "args": list(pinned["args"]), "env_keys": sorted(pinned["env_keys"])}
    return None if all(item == expected for item in found) else "mcp_server_definition_changed"


def tools_digest(tools):
    """Digest over name + inputSchema of the live tool list; descriptions and annotations are excluded on purpose."""
    canonical = sorted(({"name": t["name"], "inputSchema": t.get("inputSchema")} for t in tools), key=lambda t: t["name"])
    return hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


async def probe(registry, cwd=None, timeout=30):
    """Human-run, never from a hook: start each pinned server over stdio, list tools, compare digests.
    -> {name: {status: no_definition | unreachable | unpinned | unchanged | mcp_tool_list_changed, tools_sha256?}}"""
    import asyncio
    from mcp import Client, StdioServerParameters
    report = {}
    for name, entry in validate(registry)["servers"].items():
        definition = entry.get("definition")
        if definition is None:
            report[name] = {"status": "no_definition"}
            continue
        env = {key: os.environ[key] for key in definition["env_keys"] if key in os.environ}
        env.update({key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ})
        params = StdioServerParameters(command=definition["command"], args=list(definition["args"]), env=env, cwd=str(cwd) if cwd else None)
        try:
            async def _list():
                async with Client(params) as client:
                    return [tool.model_dump(by_alias=True, exclude_none=True) for tool in (await client.list_tools()).tools]
            tools = await asyncio.wait_for(_list(), timeout)
        except Exception:
            report[name] = {"status": "unreachable"}
            continue
        live = tools_digest(tools)
        pinned = entry.get("tools_sha256")
        report[name] = {"status": "unpinned" if pinned is None else ("unchanged" if pinned == live else "mcp_tool_list_changed"), "tools_sha256": live}
    return report


def pin(registry):
    return digest(validate(registry))


def configured():
    """(path, pin) when both are set, None when neither is, RegistryInvalid when only one is."""
    path, fingerprint = os.environ.get("ADF_MCP_REGISTRY_FILE"), os.environ.get("ADF_MCP_REGISTRY_SHA256")
    if not path and not fingerprint:
        return None
    if not path or not fingerprint:
        raise RegistryInvalid("mcp_registry_invalid")
    return Path(path), fingerprint


def load(path, fingerprint):
    """Pinned load; never repairs. The pin is computed once by the human (`adf mcp pin`), not per request."""
    import json
    try:
        if not Path(path).is_absolute() or not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
            raise RegistryInvalid("mcp_registry_invalid")
        registry = validate(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise RegistryInvalid("mcp_registry_invalid") from exc
    if digest(registry) != fingerprint:
        raise RegistryInvalid("mcp_registry_invalid")
    return registry


def decide(tool_name, registry):
    """-> None (registered) or a stable reason code. Exact names, no case folding, no wildcard."""
    match = _TOOL.fullmatch(tool_name) if isinstance(tool_name, str) else None
    if match is None:
        return "mcp_tool_name_invalid"
    server, tool = match.groups()
    entry = registry["servers"].get(server)
    if entry is None:
        return "mcp_server_not_registered"
    if tool not in entry["tools"]:
        return "mcp_tool_not_registered"
    return None
