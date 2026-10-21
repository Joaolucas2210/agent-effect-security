"""Trusted, host-configured Git worktrees for H3-01 only."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SNAPSHOT_DIGEST_VERSION = "git-tree-items-v1"
WORKSPACE_FAILURE_CODES = frozenset({
    "workspace_git_unavailable",
    "workspace_repository_invalid",
    "workspace_revision_unavailable",
    "workspace_snapshot_enumeration_failed",
    "workspace_worktree_prepare_failed",
    "workspace_worktree_cleanup_failed",
    "workspace_worktree_prune_failed",
    "workspace_configuration_invalid",
    "workspace_run_id_invalid",
})


def _git(argv, cwd, failure_code):
    """Run one fixed Git argv; this module is the only H3-01 Git caller."""
    try:
        return subprocess.run(["git", "-C", str(cwd), *argv], check=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    except FileNotFoundError:
        raise RuntimeError("workspace_git_unavailable") from None
    except (OSError, subprocess.CalledProcessError):
        raise RuntimeError(failure_code) from None


def snapshot_digest(repository, revision):
    """SHA-256 of sorted NUL records: mode SP type SP object-id TAB path NUL."""
    try:
        commit = _git(["rev-parse", "--verify", f"{revision}^{{commit}}"], repository, "workspace_revision_unavailable").strip().decode("ascii")
    except RuntimeError:
        raise
    except Exception:
        raise RuntimeError("workspace_revision_unavailable") from None
    try:
        records = []
        for record in _git(["ls-tree", "-r", "-z", commit], repository, "workspace_snapshot_enumeration_failed").split(b"\0"):
            if record:
                header, path = record.split(b"\t", 1)
                mode, kind, object_id = header.split(b" ", 2)
                records.append((path, mode + b" " + kind + b" " + object_id + b"\t" + path + b"\0"))
    except RuntimeError:
        raise
    except Exception:
        raise RuntimeError("workspace_snapshot_enumeration_failed") from None
    canonical = SNAPSHOT_DIGEST_VERSION.encode("ascii") + b"\0" + b"".join(item for _, item in sorted(records))
    return commit, hashlib.sha256(canonical).hexdigest()


class WorkspaceManager:
    """Host owns repository/revision configuration; agents supply neither root nor ref."""
    def __init__(self, trusted_repository, trusted_revision, workspace_parent=None):
        self._repository = Path(trusted_repository).resolve()
        self._revision = trusted_revision
        self._parent = Path(workspace_parent or tempfile.gettempdir()).resolve()
        self._records = {}
        if not self._repository.is_dir():
            raise RuntimeError("workspace_repository_invalid")
        if not self._parent.is_dir():
            raise RuntimeError("workspace_configuration_invalid")

    def prepare(self, run_id):
        if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
            raise RuntimeError("workspace_run_id_invalid")
        commit, digest = snapshot_digest(self._repository, self._revision)
        try:
            root = Path(tempfile.mkdtemp(prefix="adf-h3-01-", dir=self._parent))
            os.rmdir(root)
            _git(["worktree", "add", "--detach", str(root), commit], self._repository, "workspace_worktree_prepare_failed")
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError("workspace_worktree_prepare_failed") from None
        workspace_id = f"ws-{run_id}-{uuid.uuid4().hex}"
        descriptor = {"workspace_version": "1.0", "workspace_id": workspace_id, "canonical_root": str(root.resolve()), "task_ref": digest, "snapshot_digest": digest, "ownership": "harness_owned", "lifecycle": "ephemeral_prepared", "provenance": {"manager_version": "1.0", "kind": "trusted_workspace_manager"}}
        self._records[workspace_id] = descriptor
        return dict(descriptor)

    def validate_descriptor(self, descriptor):
        if not isinstance(descriptor, dict):
            return False
        expected = self._records.get(descriptor.get("workspace_id"))
        return bool(expected and descriptor == expected and descriptor["lifecycle"] == "ephemeral_prepared" and Path(expected["canonical_root"]).is_dir())

    def mark_pending_cleanup(self, descriptor):
        if not self.validate_descriptor(descriptor):
            return False
        self._records[descriptor["workspace_id"]]["lifecycle"] = "pending_cleanup"
        return True

    def cleanup(self, workspace_id):
        descriptor = self._records.get(workspace_id)
        if not descriptor:
            return False
        if descriptor["lifecycle"] == "cleaned":
            return True
        root = Path(descriptor["canonical_root"]).resolve()
        if descriptor["ownership"] != "harness_owned" or root.parent != self._parent or not root.name.startswith("adf-h3-01-"):
            return False
        try:
            _git(["worktree", "remove", "--force", str(root)], self._repository, "workspace_worktree_cleanup_failed")
        except RuntimeError:
            raise
        try:
            _git(["worktree", "prune"], self._repository, "workspace_worktree_prune_failed")
        except RuntimeError:
            raise
        descriptor["lifecycle"] = "cleaned"
        return True
