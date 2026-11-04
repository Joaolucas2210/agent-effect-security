"""ADR 0031 slice 1: host-pinned registry of MCP server and tool *names*.

Opt-in like the host policy (ADR 0011): `ADF_MCP_REGISTRY_FILE` + `ADF_MCP_REGISTRY_SHA256` (json-c14n-v1 pin).
Both unset -> no decision. One unset, a wrong pin, a swapped file or any shape outside the closed schema ->
`mcp_registry_invalid` and every MCP call is denied. Descriptions, annotations and schemas are not in the
registry: they authorize nothing (`cannot_authorize`). Slice 2 (tool-list digest) needs the live list, which
the PreToolUse payload does not carry.
"""
import os
import re
from pathlib import Path

from integration.local_evidence_bundle import digest

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")
_TOOL = re.compile(r"mcp__([A-Za-z0-9][A-Za-z0-9_.-]{0,119})__([A-Za-z0-9][A-Za-z0-9_.-]{0,119})\Z")


class RegistryInvalid(ValueError):
    pass


def validate(registry):
    """Closed shape: {schema_version: "1.0", servers: {name: {tools: [name, ...]}}}."""
    if not isinstance(registry, dict) or set(registry) != {"schema_version", "servers"} or registry["schema_version"] != "1.0" or not isinstance(registry["servers"], dict):
        raise RegistryInvalid("mcp_registry_invalid")
    for server, entry in registry["servers"].items():
        if not _NAME.fullmatch(server) or not isinstance(entry, dict) or set(entry) != {"tools"} or not isinstance(entry["tools"], list) or not all(isinstance(tool, str) and _NAME.fullmatch(tool) for tool in entry["tools"]):
            raise RegistryInvalid("mcp_registry_invalid")
    return registry


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
