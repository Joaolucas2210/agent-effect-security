"""Typed, read-only view of the host's `ADF_*` environment (ARCH-09 / R-16, Phase 2B; ADR 0040 Proposed).

`from_env(environ)` reproduces what the existing readers compute today: same names, same defaults, same
None-vs-empty semantics. Values that fail *lazily* today (an invalid port raises only when `serve` reads it)
stay lazy here as properties, so building a config never raises. Pure: no I/O, no `os.environ` access or
mutation, no global. Filesystem checks (is_dir, file mode, pins) stay with the consumers that do them.
Secrets are `Secret`: repr/str print `<redacted>`; only `.reveal()` returns the value.
Harness-only variables (ADF_CONTRACTS_PYTHON, ADF_EVAL_WRITE, ADF_EVENTS_V1, ADF_DIR, ADF_BIN) are out of scope.
"""
from dataclasses import dataclass
from typing import Mapping

DEFAULT_MAX_OUTPUT_BYTES = 1 << 20  # read_gate_host.DEFAULT_MAX_OUTPUT_BYTES, integration/read_hook.py:124


class Secret:
    """Opaque holder: never printed, never equal to a plain string."""
    __slots__ = ("_value",)

    def __init__(self, value):
        object.__setattr__(self, "_value", value)

    def __setattr__(self, name, value):
        raise AttributeError("Secret is immutable")

    def reveal(self):
        return self._value

    def __copy__(self):
        return self  # immutable: dataclasses.asdict/deepcopy keep the redacted holder

    def __deepcopy__(self, memo):
        return self

    def __repr__(self):
        return "<redacted>"

    __str__ = __repr__


def _secret(value):
    return None if value is None else Secret(value)


@dataclass(frozen=True)
class RunConfig:
    """read_gate_host.host_settings (syntax part), adf-read-hook.py, adf-deny-gate.py, mcp_read_server.py."""
    trusted_repository: str | None  # raw: consumers differ on the fallback (None, "/", cwd) — see inventory
    trusted_revision: str  # default "HEAD"
    max_output_bytes: int | None  # None = invalid; host_settings() then returns None
    run_id: str | None
    adf_home: str | None  # "" -> None: every reader uses `ADF_HOME or ~/.adf`
    claude_project_dir: str | None  # not ADF_*, but host_settings' precedence depends on it

    @property
    def revision_valid(self):
        """read_gate_host.py:49, revision half."""
        rev = self.trusted_revision
        return bool(rev) and not rev.startswith("-") and "\x00" not in rev


@dataclass(frozen=True)
class PolicyConfig:
    """Read policy (ADR 0011) and MCP registry (ADR 0031) pins."""
    read_policy_file: str | None  # None vs "" matters: only both-None selects the demo
    read_policy_sha256: str | None
    mcp_registry_file: str | None  # raw; here "" counts as absent (mcp_registry.configured)
    mcp_registry_sha256: str | None
    mcp_probe_max_age_days_raw: str  # default "30"

    @property
    def read_policy_state(self):
        """'demo' | 'partial' | 'configured' — local_read_adapter.py:135, cli.read_policy_status."""
        pair = (self.read_policy_file, self.read_policy_sha256)
        return "demo" if pair == (None, None) else "partial" if None in pair else "configured"

    @property
    def mcp_registry_state(self):
        """'absent' | 'partial' | 'configured' — mcp_registry.configured (partial raises RegistryInvalid there)."""
        path, pin = self.mcp_registry_file, self.mcp_registry_sha256
        return "absent" if not path and not pin else "partial" if not path or not pin else "configured"

    @property
    def mcp_probe_max_age_days(self):
        """cli._doctor_mcp: int() raises ValueError; a negative value is the same error there."""
        return int(self.mcp_probe_max_age_days_raw)


@dataclass(frozen=True)
class EvidenceConfig:
    evidence_dir: str | None  # raw; host_settings / gates apply their own defaults
    evidence_key_file: str | None  # "" -> None: evidence_signing.key_path uses truthiness
    capture_timings: bool  # exactly "1"


@dataclass(frozen=True)
class A2AConfig:
    """a2a_gateway._main / host_validator and mcp_a2a_client."""
    url: str  # default "", validated by the client (loopback only)
    token_file: str  # default "", validated by the client (absolute, owner-only)
    port_raw: str  # default "8765"
    issuer: str
    audience: str
    confirm_skills: frozenset
    jwks_file: str | None
    jwks_sha256: str | None
    hs256_secret: Secret | None

    @property
    def auth_mode(self):
        """'rs256' when either JWKS variable is set (partial fails closed in load_jwks), else 'hs256'."""
        return "rs256" if self.jwks_file is not None or self.jwks_sha256 is not None else "hs256"

    @property
    def port(self):
        return int(self.port_raw)  # ValueError, as a2a_gateway.py:518

    def hs256_key(self):
        """bytes.fromhex(os.environ[...]) today: KeyError when unset, ValueError when not hex."""
        if self.hs256_secret is None:
            raise KeyError("ADF_A2A_HS256_SECRET")
        return bytes.fromhex(self.hs256_secret.reveal())


@dataclass(frozen=True)
class OtelConfig:
    enabled: bool  # exactly "1"
    endpoint: Secret  # may carry userinfo; otel_export never logs it
    headers: Secret  # raw `k=v,...`, credentials
    flush_seconds: float
    service_name: str


@dataclass(frozen=True)
class HostConfig:
    run: RunConfig
    policy: PolicyConfig
    evidence: EvidenceConfig
    a2a: A2AConfig
    otel: OtelConfig

    def redacted(self):
        """Nested dict for diagnostics; secrets as '<redacted>' when set."""
        return {name: {key: str(value) if isinstance(value, Secret) else value for key, value in vars(getattr(self, name)).items()} for name in ("run", "policy", "evidence", "a2a", "otel")}


def _budget(raw):
    """read_gate_host.py:46,49 budget half."""
    return int(raw) if raw.isascii() and raw.isdecimal() and int(raw) >= 1 else None


def _flush(raw):
    """otel_export._flush_seconds reads this since Phase 2C (equivalence: hooks/test-config-migration-otel-flush.py)."""
    return min(int(raw), 2000) / 1000 if raw.isascii() and raw.isdecimal() else 0.3


def _a2a(env):
    return A2AConfig(
        url=env.get("ADF_A2A_URL", ""), token_file=env.get("ADF_A2A_TOKEN_FILE", ""), port_raw=env.get("ADF_A2A_PORT", "8765"),
        issuer=env.get("ADF_A2A_ISSUER", "adf-test-idp"), audience=env.get("ADF_A2A_AUDIENCE", "adf-a2a-local"),
        confirm_skills=frozenset(filter(None, env.get("ADF_A2A_CONFIRM_SKILLS", "").split(","))),
        jwks_file=env.get("ADF_A2A_JWKS_FILE"), jwks_sha256=env.get("ADF_A2A_JWKS_SHA256"), hs256_secret=_secret(env.get("ADF_A2A_HS256_SECRET")))


def from_env(environ: Mapping[str, str]) -> HostConfig:
    env = environ
    run = RunConfig(
        trusted_repository=env.get("ADF_TRUSTED_REPOSITORY"), trusted_revision=env.get("ADF_TRUSTED_REVISION", "HEAD"),
        max_output_bytes=_budget(env.get("ADF_MAX_OUTPUT_BYTES", str(DEFAULT_MAX_OUTPUT_BYTES))), run_id=env.get("ADF_RUN_ID"),
        adf_home=env.get("ADF_HOME") or None, claude_project_dir=env.get("CLAUDE_PROJECT_DIR"))
    policy = PolicyConfig(
        read_policy_file=env.get("ADF_READ_POLICY_FILE"), read_policy_sha256=env.get("ADF_READ_POLICY_SHA256"),
        mcp_registry_file=env.get("ADF_MCP_REGISTRY_FILE"), mcp_registry_sha256=env.get("ADF_MCP_REGISTRY_SHA256"),
        mcp_probe_max_age_days_raw=env.get("ADF_MCP_PROBE_MAX_AGE_DAYS", "30"))
    evidence = EvidenceConfig(env.get("ADF_EVIDENCE_DIR"), env.get("ADF_EVIDENCE_KEY_FILE") or None, env.get("ADF_CAPTURE_TIMINGS") == "1")
    otel = OtelConfig(
        enabled=env.get("ADF_OTEL_ENABLED") == "1", endpoint=Secret(env.get("ADF_OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318").rstrip("/")),
        headers=Secret(env.get("ADF_OTEL_EXPORTER_OTLP_HEADERS", "")), flush_seconds=_flush(env.get("ADF_OTEL_FLUSH_MS", "300")),
        service_name=env.get("ADF_OTEL_SERVICE_NAME", "adf-control-plane"))
    return HostConfig(run, policy, evidence, _a2a(env), otel)


def hook_environ(environ: Mapping[str, str], root: str, evidence_dir: str) -> dict:
    """Pure form of integration/read_hook.py:122-127: the host-derived root always wins; revision, budget and
    evidence dir are `setdefault` (an inherited value, even an empty one, wins). Returns a new dict."""
    defaults = {"ADF_TRUSTED_REVISION": "HEAD", "ADF_MAX_OUTPUT_BYTES": str(DEFAULT_MAX_OUTPUT_BYTES), "ADF_EVIDENCE_DIR": evidence_dir}
    return {**defaults, **environ, "ADF_TRUSTED_REPOSITORY": root}
