#!/usr/bin/env python3
"""Checkout entry point for the Claude Code `Read` gate.
The code is `integration/claude_read_gate.py`: one implementation, also shipped in the wheel.

Kept for existing registrations, make targets and tooling that run or load this file by path. The module source runs
in this file's namespace (it is not imported), so every name read or patched here is the one the code uses. Both files
are pinned (ADR 0027).
"""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_IMPL = importlib.util.find_spec("integration.claude_read_gate").origin
exec(compile(Path(_IMPL).read_bytes(), _IMPL, "exec"))  # noqa: S102 - our own pinned module, not input
