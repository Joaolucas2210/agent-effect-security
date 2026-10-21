"""Opt-in, local stdio MCP tool: hand the model the adapter's verified snapshot text."""
import hashlib
import json
import os
import time
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from integration.local_evidence_bundle import verify_offline
from integration.local_read_adapter import LocalReadAdapter, schemas
from integration.otel_export import emit_local_read
from integration.read_gate_host import host_policy_settings, host_settings, read_adapter


mcp = MCPServer("adf-local-read")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False), structured_output=False)
def read_snapshot(path: str) -> str:
    """Read one exact, host-allowlisted UTF-8 path from a trusted Git snapshot."""
    required = (
        "ADF_TRUSTED_REPOSITORY", "ADF_TRUSTED_REVISION", "ADF_EVIDENCE_DIR",
        "ADF_MAX_OUTPUT_BYTES", "ADF_RUN_ID", "ADF_READ_POLICY_FILE", "ADF_READ_POLICY_SHA256",
    )
    if any(not os.environ.get(key) for key in required):
        raise ToolError("host_configuration_invalid")
    settings = host_settings()
    if settings is None:
        raise ToolError("host_configuration_invalid")
    repository, revision, evidence_dir, budget = settings
    start_ns = time.time_ns()
    result = read_adapter(LocalReadAdapter(repository, revision, evidence_dir, **host_policy_settings()), os.environ["ADF_RUN_ID"], path, budget, evidence_dir)
    emit_local_read("mcp_read", result, start_ns, hook=False)  # ADR 0021: long-lived process, no wait
    if result["outcome"] != "delivered":
        raise ToolError(result["reason_code"])
    try:
        bundle = json.loads(Path(result["bundle_path"]).read_text(encoding="utf-8"))
        content = result["content"]
        receipt = bundle["receipt"]
        if not verify_offline(bundle, schemas()) or bundle["bundle_id"] != result["bundle_id"] or receipt["content_sha256"] != hashlib.sha256(content.encode("utf-8")).hexdigest() or receipt["bytes_read"] != len(content.encode("utf-8")):
            raise ValueError("evidence_bundle_invalid")
    except Exception:
        raise ToolError("evidence_bundle_invalid") from None
    return content
