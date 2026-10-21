"""One safe local-file read primitive for H3-01."""
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from .contracts import valid


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def sensitive_path(path, policy):
    """Deterministic metadata-only policy; it never inspects file contents."""
    return any(component in policy["deny_components"] or any(component.startswith(prefix) for prefix in policy["deny_component_prefixes"]) or any(component.endswith(suffix) for suffix in policy["deny_component_suffixes"]) for component in path.split("/"))


def _taint():
    return {"classification": "untrusted_workspace_file", "cannot_authorize": True}


def _result(descriptor, outcome, reason_code, content=None):
    result = {"result_version": "1.0", "outcome": outcome, "reason_code": reason_code, "bytes_read": len(content) if content is not None else 0, "taint": _taint(), "provenance": {"runtime_version": "1.0", "workspace_id": descriptor["workspace_id"], "snapshot_digest": descriptor["snapshot_digest"]}}
    if content is not None:
        result.update(content=content.decode("utf-8"), content_sha256=hashlib.sha256(content).hexdigest())
    return result


def receipt_for(decision, descriptor, result, timestamp=None):
    receipt = {"receipt_version": "1.0", "receipt_id": "", "decision_id": decision["decision_id"], "run_id": decision["bindings"]["run_id"], "operation_id": decision["bindings"]["operation_id"], "effective_scope": decision["effective_scope"], "profile_sha256": decision["bindings"]["profile_sha256"], "policy_sha256": decision["bindings"]["policy_sha256"], "workspace_id": descriptor["workspace_id"], "snapshot_digest": descriptor["snapshot_digest"], "outcome": result["outcome"], "reason_code": result["reason_code"], "bytes_read": result["bytes_read"], "timestamp": timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "provenance": {"runtime_version": "1.0", "kind": "redacted_runtime_receipt"}}
    if result["outcome"] == "delivered":
        receipt["content_sha256"] = result["content_sha256"]
    receipt["receipt_id"] = _digest({key: value for key, value in receipt.items() if key != "receipt_id"})
    return receipt


def verify_receipt(receipt):
    """Pure integrity check only; it neither authorizes nor reopens a file."""
    if not valid("runtime_audit_receipt", receipt):
        return False
    return receipt["receipt_id"] == _digest({key: value for key, value in receipt.items() if key != "receipt_id"})


class LocalReadRuntime:
    def __init__(self, sensitive_policy):
        self._policy = sensitive_policy

    @staticmethod
    def available():
        return all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY")) and os.open in os.supports_dir_fd

    def read(self, descriptor, path, max_output_bytes):
        if not self.available():
            return _result(descriptor, "deny", "safe_open_unavailable")
        if not isinstance(path, str) or not path or path.startswith("/") or "\x00" in path or any(part in {"", ".", ".."} for part in path.split("/")):
            return _result(descriptor, "deny", "invalid_path")
        if sensitive_path(path, self._policy):
            return _result(descriptor, "deny", "sensitive_path_denied")
        flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        descriptors = []
        try:
            root_fd = os.open(descriptor["canonical_root"], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
            descriptors.append(root_fd)
            current_fd = root_fd
            for part in path.split("/")[:-1]:
                current_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=current_fd)
                descriptors.append(current_fd)
            file_fd = os.open(path.rsplit("/", 1)[-1], flags, dir_fd=current_fd)
            descriptors.append(file_fd)
            metadata = os.fstat(file_fd)
            if not stat.S_ISREG(metadata.st_mode):
                return _result(descriptor, "deny", "unsafe_file_type")
            if metadata.st_size > max_output_bytes:
                return _result(descriptor, "deny", "output_limit_exceeded")
            content = os.read(file_fd, metadata.st_size)
            try:
                return _result(descriptor, "delivered", "read_delivered", content)
            except UnicodeDecodeError:
                return _result(descriptor, "deny", "content_encoding_invalid")
        except OSError:
            return _result(descriptor, "deny", "safe_open_failed")
        finally:
            for fd in reversed(descriptors):
                os.close(fd)
