"""ADR 0039 (Proposed): Community extension seams for the read adapter, each with the current behaviour as default.

Only one seam is cut: `PolicySource`. Evidence persistence, signing and the caller principal stay where they are
(ADR 0039 says why). A source is host code passed by constructor; nothing here is selected by environment, entry
point or registry. Whatever a source returns, the adapter re-checks it against its pin and the contract schemas, and
the PDP and PEP still decide and revalidate every read.
"""
import json
import re
from pathlib import Path
from typing import Optional, Protocol, Tuple

_PIN = re.compile(r"[a-f0-9]{64}")


class PolicySource(Protocol):
    def load(self) -> Optional[Tuple[dict, str]]:
        """(host policy config, its sha256 pin), or None for the reference demo. Raise to fail closed:
        the adapter then denies every read with `host_policy_invalid`."""


class HostPolicyFile:
    """Default source: the host-owned file and pin (`ADF_READ_POLICY_FILE` / `ADF_READ_POLICY_SHA256`)."""

    def __init__(self, path=None, sha256=None):
        self.path, self.sha256 = path, sha256

    def load(self):
        """Both absent selects the demo; a partial or malformed pair raises like `load_host_policy`."""
        return None if self.path is None and self.sha256 is None else self.read()

    def read(self):
        if not isinstance(self.sha256, str) or not _PIN.fullmatch(self.sha256) or self.path is None or not Path(self.path).is_absolute():
            raise ValueError("host_policy_invalid")
        return json.loads(Path(self.path).read_text(encoding="utf-8")), self.sha256
