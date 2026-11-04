"""ADR 0030: detached HMAC-SHA256 signatures over evidence files, with a host-held key.

Opt-in: `ADF_EVIDENCE_KEY_FILE` (absolute path to 32 raw bytes, mode 0400) turns signing on. Once configured,
any failure to sign is `SigningUnavailable` and the caller delivers nothing. Unconfigured hosts are unchanged;
a verifier reports their files as `unsigned`. The signature lives next to the file as `<name>.sig`, so bundle,
record and journal schemas, digests and `verify_offline` stay byte-identical (aggregators read only `*.json`).
ponytail: HMAC (stdlib) first; Ed25519 when a partner needs verification without the shared key.
"""
import hashlib
import hmac
import json
import os
import secrets
import stat
from pathlib import Path

ALG = "hmac-sha256"
KEY_BYTES = 32


class SigningUnavailable(RuntimeError):
    """A configured key cannot be used; evidence must not be delivered unsigned."""


def key_path():
    """Configured key path or None (signing off)."""
    value = os.environ.get("ADF_EVIDENCE_KEY_FILE")
    return Path(value) if value else None


def load_key(path):
    try:
        path = Path(path)
        if not path.is_absolute():
            raise SigningUnavailable("key_path_not_absolute")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise SigningUnavailable("key_unreadable") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or (info.st_mode & 0o777) != 0o400 or info.st_size != KEY_BYTES:
            raise SigningUnavailable("key_file_invalid")
        key = os.read(fd, KEY_BYTES + 1)
    finally:
        os.close(fd)
    if len(key) != KEY_BYTES:
        raise SigningUnavailable("key_file_invalid")
    return key


def init_key(path):
    """Create the key owner-read-only; never overwrite. A human runs this (`adf key init`)."""
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, "wb") as handle:
        handle.write(secrets.token_bytes(KEY_BYTES))
    os.chmod(path, 0o400)
    return path


def key_id(key):
    return hashlib.sha256(key).hexdigest()[:16]


def _sidecar(path):
    path = Path(path)
    return path.with_name(path.name + ".sig")


def _mac(key, data):
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def sign_file(path, key):
    """Write `<path>.sig` (0600, exclusive) over the file's current bytes."""
    data = Path(path).read_bytes()
    meta = {"sig_version": "1.0", "alg": ALG, "key_id": key_id(key), "target_sha256": hashlib.sha256(data).hexdigest(), "value": _mac(key, data)}
    sidecar = _sidecar(path)
    fd = os.open(sidecar, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(meta, sort_keys=True, separators=(",", ":")))
    return sidecar


def sign_if_configured(path):
    """Sign when the host configured a key; raise SigningUnavailable instead of leaving the file unsigned."""
    configured = key_path()
    if configured is None:
        return None
    try:
        return sign_file(path, load_key(configured))
    except SigningUnavailable:
        raise
    except OSError as exc:
        raise SigningUnavailable("signature_write_failed") from exc


def verify_file(path, key):
    """-> 'not_checked' (no key given) | 'unsigned' (no sidecar) | 'valid' | 'invalid'. Offline, pure."""
    if key is None:
        return "not_checked"
    sidecar = _sidecar(path)
    if not sidecar.is_file():
        return "unsigned"
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        data = Path(path).read_bytes()
        expected = {"sig_version": "1.0", "alg": ALG, "key_id": key_id(key), "target_sha256": hashlib.sha256(data).hexdigest(), "value": _mac(key, data)}
        return "valid" if isinstance(meta, dict) and set(meta) == set(expected) and all(hmac.compare_digest(str(meta[k]), expected[k]) for k in expected) else "invalid"
    except (OSError, ValueError, TypeError):
        return "invalid"
