"""A2A edge (ADRs 0013/0014): bearer AuthN + per-skill scopes, then the unchanged PDP/PEP.

Transport and identity only. The Agent Card is discovery; nothing here reads it to decide.
After AuthN the edge builds a CallerPrincipal; the existing LocalReadAdapter runs PDP, PEP,
confined read and EvidenceBundle, and the edge links them in an A2AEvidenceRecord.
"""
import base64
import hashlib
import hmac
import json
import math
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jsonschema import Draft7Validator

from integration.local_evidence_bundle import canonical, digest, verify_offline
from integration.local_read_adapter import LocalReadAdapter, load_host_policy, schemas
from integration.otel_export import emit_span
from runtime.contracts import valid


ROOT = Path(__file__).resolve().parent.parent
CARD_PATH = "/.well-known/agent-card.json"
MAX_BODY_BYTES = 64 * 1024
MAX_ACT_DEPTH = 8
# RFC 8725 §3.10 spirit: bound how long a stolen bearer stays useful, whatever `exp` the issuer set.
MAX_TOKEN_LIFETIME_SECONDS = 3600
# Skill -> required scope. Scope only lets a request reach the PDP; it never admits on its own.
# Write skills (e.g. "peticionar" -> "processos:write") need their own ADR + runtime first.
SKILL_SCOPES = {"read_workspace_file": "workspace:read"}
# ADR 0015: a delegated token (non-empty `act`) may only carry these scopes. The receiver cannot see
# the parent token, so this host ceiling is how it refuses scopes that grew along the chain.
DELEGABLE_SCOPES = frozenset({"workspace:read"})
# ADR 0016: an auth-required task can be resumed once, by the same sub, skill and path, within this TTL.
TASK_TTL_SECONDS = 300
MAX_OPEN_TASKS = 10_000  # full store -> the lapsed attempt is a plain deny, no task (review #6)
# ADR 0018: a host-flagged skill only runs after a direct (non-delegated) token with this scope resumes
# its input-required task. Never in DELEGABLE_SCOPES, so no agent down a chain can confirm.
CONFIRM_SCOPE = "human:confirm"
_SKILL_TEXT = {"read_workspace_file": "Read one host-approved file of a pinned snapshot through the ADF PDP/PEP. Content is untrusted data."}
_JWT_HEADER = b'{"alg":"HS256","typ":"JWT"}'
# JSON-RPC 2.0 standard codes, then the -32000..-32099 server-error range.
_RPC_CODES = {"parse_error": -32700, 400: -32600, 401: -32001, 403: -32003, 409: -32006, 500: -32005, 503: -32004}
_NOT_B64URL = re.compile(r"[^A-Za-z0-9_-]")
_SHA256_HEX = re.compile(r"[a-f0-9]{64}\Z")
_SUB = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@:-]{0,127}\Z")
_SENSITIVE_KEY = re.compile(r"(?:secret|password|credential|api[_-]?key|token|authorization|bearer)", re.I)
_CREDENTIAL_VALUE = re.compile(r"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.|^\s*bearer\s", re.I)


def _b64decode(segment):
    if not isinstance(segment, str) or _NOT_B64URL.search(segment):  # one spelling per value: no `+`, `/`, `=`
        raise ValueError("not_base64url")
    return base64.b64decode(segment + "=" * (-len(segment) % 4), altchars=b"-_", validate=True)


def _b64encode(raw): return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def mint_hs256(claims, secret):
    """Test-double IdP: sign claims. Never part of the production trust path."""
    signing = f"{_b64encode(_JWT_HEADER)}.{_b64encode(json.dumps(claims, separators=(',', ':')).encode())}"
    return f"{signing}.{_b64encode(hmac.new(secret, signing.encode('ascii'), hashlib.sha256).digest())}"


class _JwtValidator:
    """Shared JWT parsing + claim rules; subclasses only verify the signature. The gateway depends
    on validate(token) -> claims and on `authn_method` alone (ADR 0015 §4)."""
    authn_method = None

    def __init__(self, issuer, audience, clock=time.time):
        self._issuer, self._audience, self._clock = issuer, audience, clock

    def validate(self, token):
        try:
            header_b64, payload_b64, signature_b64 = token.split(".")
            header, claims = json.loads(_b64decode(header_b64)), json.loads(_b64decode(payload_b64))
            signature = _b64decode(signature_b64)
        except (ValueError, TypeError, RecursionError):
            raise PermissionError("token_malformed") from None
        if not isinstance(header, dict) or "crit" in header:  # RFC 7515 §4.1.11: no extension is understood
            raise PermissionError("token_alg_rejected")
        self._verify(header, f"{header_b64}.{payload_b64}".encode("ascii"), signature)
        return self._check_claims(claims)

    def _check_claims(self, claims):
        now = self._clock()
        if not isinstance(claims, dict) or not isinstance(claims.get("sub"), str) or not _SUB.fullmatch(claims["sub"]) or type(claims.get("exp")) is not int:
            raise PermissionError("token_claims_invalid")
        if claims.get("iss") != self._issuer:
            raise PermissionError("token_issuer_invalid")
        if claims.get("aud") != self._audience:  # exact: a multi-audience token is a passthrough risk
            raise PermissionError("token_audience_invalid")
        if now >= claims["exp"]:
            raise PermissionError("token_expired")
        if claims["exp"] - now > MAX_TOKEN_LIFETIME_SECONDS:
            raise PermissionError("token_lifetime_exceeded")
        if "nbf" in claims and (type(claims["nbf"]) is not int or now < claims["nbf"]):
            raise PermissionError("token_not_yet_valid")
        return claims


class HS256TokenValidator(_JwtValidator):
    """Pilot/test validator: a shared secret, so whoever holds it can mint any chain (ADR 0015).
    Production uses RS256JwksValidator."""
    authn_method = "bearer_jwt_hs256"

    def __init__(self, secret, issuer, audience, clock=time.time):
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError("weak_secret")
        super().__init__(issuer, audience, clock)
        self._secret = secret

    def _verify(self, header, signing_input, signature):
        if header.get("alg") != "HS256":
            raise PermissionError("token_alg_rejected")
        if not hmac.compare_digest(hmac.new(self._secret, signing_input, hashlib.sha256).digest(), signature):
            raise PermissionError("token_signature_invalid")


# DigestInfo DER prefix for SHA-256 (RFC 8017 §9.2, note 1).
_SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
_MIN_RSA_BITS, _MAX_RSA_BITS = 2048, 8192
# Product of the odd primes below 1000: a pinned modulus sharing any of them is degenerate (review #1).
_SMALL_PRIMES = math.prod(n for n in range(3, 1000, 2) if all(n % d for d in range(3, int(n ** 0.5) + 1, 2)))


def rs256_verify(n, e, message, signature):
    """RSASSA-PKCS1-v1_5 / SHA-256 verify in stdlib. Rebuilds the full expected encoding and compares
    it in constant time; never parses the decrypted block (no Bleichenbacher-style padding oracle)."""
    size = (n.bit_length() + 7) // 8
    if len(signature) != size or int.from_bytes(signature, "big") >= n:
        return False
    padding = size - 3 - len(_SHA256_DIGEST_INFO) - 32
    expected = b"\x00\x01" + b"\xff" * padding + b"\x00" + _SHA256_DIGEST_INFO + hashlib.sha256(message).digest()
    return padding >= 8 and hmac.compare_digest(pow(int.from_bytes(signature, "big"), e, n).to_bytes(size, "big"), expected)


def load_jwks(path, fingerprint):
    """Host-owned public keys, pinned like the host policy (ADR 0011): absolute path, SHA-256 of the
    file bytes, closed RSA entries (kty, kid, n, e, optional alg=RS256 / use=sig), n >= 2048 bits,
    e = 65537, unique kids. No network fetch, no repair: anything else is jwks_invalid."""
    try:
        if not isinstance(fingerprint, str) or not _SHA256_HEX.fullmatch(fingerprint) or path is None or not Path(path).is_absolute():
            raise ValueError
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != fingerprint:
            raise ValueError
        keys = json.loads(raw)["keys"]
        table = {}
        for key in keys:
            if not set(key) <= {"kty", "kid", "n", "e", "alg", "use"} or key.get("kty") != "RSA" or key.get("alg", "RS256") != "RS256" or key.get("use", "sig") != "sig":
                raise ValueError
            n, e = int.from_bytes(_b64decode(key["n"]), "big"), int.from_bytes(_b64decode(key["e"]), "big")
            if not isinstance(key["kid"], str) or not _SUB.fullmatch(key["kid"]) or key["kid"] in table or not _MIN_RSA_BITS <= n.bit_length() <= _MAX_RSA_BITS or n % 2 == 0 or math.gcd(n, _SMALL_PRIMES) != 1 or e != 65537:
                raise ValueError
            table[key["kid"]] = (n, e)
        if not table:
            raise ValueError
        return table
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        raise ValueError("jwks_invalid") from None


class RS256JwksValidator(_JwtValidator):
    """Asymmetric validator over a host-pinned JWKS: the gateway holds only public keys, so it
    cannot mint tokens. ponytail: static file, no rotation fetch; rotate by re-pinning the file."""
    authn_method = "bearer_jwt_rs256"

    def __init__(self, jwks_path, jwks_sha256, issuer, audience, clock=time.time):
        super().__init__(issuer, audience, clock)
        self._keys = load_jwks(jwks_path, jwks_sha256)

    def _verify(self, header, signing_input, signature):
        if header.get("alg") != "RS256":  # also blocks HS256-with-public-key confusion
            raise PermissionError("token_alg_rejected")
        key = self._keys.get(header.get("kid")) if isinstance(header.get("kid"), str) else None
        if key is None:
            raise PermissionError("token_key_unknown")
        if not rs256_verify(*key, signing_input, signature):
            raise PermissionError("token_signature_invalid")


def act_chain(claims):
    """RFC 8693 `act` chain, current actor first (ADR 0015): closed `{sub, act?}` levels, depth
    <= MAX_ACT_DEPTH, no `sub` repeated across subject + actors. Audit only, never authorizes."""
    chain, act = [], claims.get("act")
    while act is not None:
        if len(chain) >= MAX_ACT_DEPTH or not isinstance(act, dict) or not set(act) <= {"sub", "act"} or not isinstance(act.get("sub"), str) or not _SUB.fullmatch(act["sub"]):
            raise PermissionError("delegation_chain_invalid")
        chain.append(act["sub"]); act = act.get("act")
    if len({claims.get("sub"), *chain}) != len(chain) + 1:
        raise PermissionError("delegation_chain_invalid")
    return chain


def exchange_hs256(validator, subject_token, actor, requested_scopes, audience, secret, ttl=300):
    """Test double for an RFC 8693-style exchange (ADR 0015): tests and local pilot only, no endpoint,
    not a production AS. The subject token must be valid for this validator's audience; the derived
    token targets the next hop's `aud`, narrows scopes, never outlives its parent and appends `actor`."""
    claims = validator.validate(subject_token)
    parent = set(claims["scope"].split()) if isinstance(claims.get("scope"), str) else set()
    if not set(requested_scopes) <= parent:
        raise PermissionError("scope_escalation_denied")
    derived = {"iss": claims["iss"], "aud": audience, "sub": claims["sub"], "scope": " ".join(sorted(set(requested_scopes))), "act": {"sub": actor, **({"act": claims["act"]} if "act" in claims else {})}, "exp": min(claims["exp"], int(time.time()) + ttl)}
    act_chain(derived)  # malformed actor, cycle or depth fails closed before anything is signed
    return mint_hs256(derived, secret)


def carries_credential(value):
    if isinstance(value, dict):
        return any(_SENSITIVE_KEY.search(str(key)) or carries_credential(item) for key, item in value.items())
    if isinstance(value, list):
        return any(carries_credential(item) for item in value)
    return isinstance(value, str) and bool(_CREDENTIAL_VALUE.search(value))


def agent_card(port, authenticated=False):
    """Discovery only. The public card hides every skill that requires a scope."""
    skills = [{"id": skill, "name": skill.replace("_", " "), "description": _SKILL_TEXT[skill], "tags": ["read"], "security": [{"bearer": [scope]}]} for skill, scope in SKILL_SCOPES.items()]
    return {
        "protocolVersion": "0.3.0", "name": "ADF control plane", "description": "Local A2A edge; every request is decided by the ADF PDP (ADR 0013).",
        "url": f"http://127.0.0.1:{port}/", "version": "0.1.0", "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["application/json"], "defaultOutputModes": ["application/json"],
        "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}}, "security": [{"bearer": []}],
        "supportsAuthenticatedExtendedCard": True, "skills": skills if authenticated else [item for item in skills if not item["security"]],
    }


def _error(status, request_id, reason, audit=None):
    data = {"reason_code": reason, **({"audit": audit} if audit else {})}
    return status, {"jsonrpc": "2.0", "id": request_id, "error": {"code": _RPC_CODES.get(reason, _RPC_CODES[status]), "message": reason, "data": data}}


def span_attributes(status, response, duration_ms):
    """ADR 0020: ids and codes already in the response; never body content, path or token."""
    body = response.get("result") or response.get("error", {}).get("data") or {}
    audit, task = body.get("audit") or {}, body.get("task") or {}
    return {"http.response.status_code": status, "adf.has_principal": status not in (400, 401), "adf.duration_ms": duration_ms,
            "adf.outcome": body.get("outcome") or ("deny" if "error" in response else None), "adf.reason_code": body.get("reason_code"),
            "adf.act_depth": len(audit["act"]) if "act" in audit else None, "adf.task_state": task.get("status", {}).get("state"),
            **{f"adf.{key}": audit.get(key) for key in ("skill", "decision_id", "bundle_id", "record_id", "confirmation")}}


def caller_principal(claims, chain, authn_method="bearer_jwt_hs256"):
    """ADR 0014: who asks, built only after AuthN. Never a credential; never sent by a client."""
    scope = claims.get("scope")
    return {"schema_version": "1.0", "sub": claims["sub"], "scopes": sorted(set(scope.split())) if isinstance(scope, str) else [], "act": chain, "token_aud": claims["aud"], "authn_method": authn_method, "expires_at": claims["exp"]}


def effect_binding(principal, skill, path):
    """ADR 0022: closed descriptor of the effect a pause binds to; the confirmation must reproduce it exactly."""
    return digest({"sub": principal["sub"], "skill": skill, "path": path})


def evidence_record(principal, skill, outcome, reason_code, decision_id=None, bundle_id=None, task_id=None, confirmed=False, binding=None):
    record = {"schema_version": "1.0", "record_id": "", "nonce": uuid.uuid4().hex, "edge_id": "a2a", "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "skill": skill, "principal": principal, "outcome": outcome, "reason_code": reason_code, "decision_id": decision_id, "bundle_id": bundle_id, **({"task_id": task_id} if task_id else {}), **({"confirmation": "human_confirmed"} if confirmed else {}), **({"effect_binding": binding} if binding else {})}
    record["record_id"] = digest({key: value for key, value in record.items() if key != "record_id"})
    return record


def persist_record(record, evidence_dir):
    """evidence_dir/_a2a/<record_id>.json, owner-only, never overwriting (same law as bundles)."""
    directory = Path(evidence_dir) / "_a2a"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / f"{record['record_id']}.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(canonical(record))


def verify_record(record, bundle, contract_schemas):
    """Offline, fail-closed. Verifies what the edge saw and its bundle link; never authorizes."""
    if not Draft7Validator(contract_schemas["a2a_evidence_record"]).is_valid(record) or not Draft7Validator(contract_schemas["caller_principal"]).is_valid(record["principal"]):
        return False
    if record["record_id"] != digest({key: value for key, value in record.items() if key != "record_id"}):
        return False
    if bundle is None:
        return record["bundle_id"] is None and record["decision_id"] is None
    return verify_offline(bundle, contract_schemas) and (bundle["bundle_id"], bundle["decision_id"]) == (record["bundle_id"], record["decision_id"])


class A2AGateway:
    """Host-configured edge. Requests carry only skill + path; repository, revision, evidence,
    policy and budget are the host's, exactly as for the Claude/Codex gates."""

    def __init__(self, validator, trusted_repository, trusted_revision, evidence_dir, host_policy_path, host_policy_sha256, max_output_bytes, port, workspace_parent=None, confirm_skills=frozenset()):
        self._confirm_skills = frozenset(confirm_skills)  # host-owned, like policy; never from a request
        self._validator, self._budget, self._port, self._evidence = validator, max_output_bytes, port, Path(evidence_dir)
        self._schemas = schemas()
        self._request = Draft7Validator(json.loads((ROOT / "integration/v1/schemas/a2a-request.schema.json").read_text(encoding="utf-8")))
        try:
            self._policy = load_host_policy(host_policy_path, host_policy_sha256, self._schemas)
        except Exception:  # never fall back to the adapter's demo grants
            self._policy = None
        if type(max_output_bytes) is not int or max_output_bytes < 0:
            self._policy = None
        # ponytail: in-memory, single process; a restart loses tasks, so resume fails closed (task_not_found).
        self._tasks, self._tasks_lock = {}, threading.Lock()
        self._adapter = None if self._policy is None else LocalReadAdapter(trusted_repository, trusted_revision, evidence_dir, workspace_parent, host_policy_path=host_policy_path, host_policy_sha256=host_policy_sha256)

    def card(self, authenticated=False): return agent_card(self._port, authenticated)

    def handle(self, authorization, body):
        """Return (http_status, JSON-RPC response). The span (ADR 0020) only observes the answer."""
        start = time.time_ns()
        status, response = self._handle(authorization, body)
        end = time.time_ns()
        emit_span("adf.a2a.request", span_attributes(status, response, (end - start) // 1_000_000), start, end)
        return status, response

    def _handle(self, authorization, body):
        """Fixed order, every failure fails closed."""
        try:
            request = json.loads(body)
        except (ValueError, TypeError, RecursionError):
            return _error(400, None, "parse_error")
        request_id = request.get("id") if isinstance(request, dict) and type(request.get("id")) in (str, int) else None
        try:
            leaked = carries_credential(request)
        except RecursionError:  # nesting no closed request can have
            return _error(400, request_id, "invalid_request")
        if leaked:
            return _error(400, None, "credential_in_payload")
        if not self._request.is_valid(request):
            return _error(400, request_id, "invalid_request")
        try:
            claims = self._authenticate(authorization)
            principal = caller_principal(claims, act_chain(claims), self._validator.authn_method)
            if not valid("caller_principal", principal):
                raise PermissionError("token_claims_invalid")
        except PermissionError as exc:
            return _error(401, request_id, exc.args[0])
        if request["method"] == "agent/getAuthenticatedExtendedCard":
            return 200, {"jsonrpc": "2.0", "id": request_id, "result": self.card(authenticated=True)}
        message = request["params"]["message"]
        return self._authorize_and_read(request_id, principal, message["parts"][0]["data"], message.get("taskId"))

    def _authenticate(self, authorization):
        if not isinstance(authorization, str) or not authorization.startswith("Bearer ") or not authorization[7:]:
            raise PermissionError("auth_missing")
        return self._validator.validate(authorization[7:])

    def _audit(self, record):
        return {"sub": record["principal"]["sub"], "act": record["principal"]["act"], **{key: record[key] for key in ("skill", "outcome", "reason_code", "decision_id", "bundle_id", "record_id")}, **{key: record[key] for key in ("task_id", "confirmation", "effect_binding") if key in record}}

    def _open_task(self, principal, skill, path, state="auth-required"):
        task_id, now = uuid.uuid4().hex, time.time()
        with self._tasks_lock:
            self._tasks = {key: task for key, task in self._tasks.items() if task[3] > now}
            if len(self._tasks) >= MAX_OPEN_TASKS:
                return None
            self._tasks[task_id] = ((principal["sub"], tuple(principal["act"])), skill, path, now + TASK_TTL_SECONDS, state)
        return task_id

    def _claim_task(self, task_id, principal, skill, path):
        """Consume a task exactly once -> (reason, state). A mismatch leaves it for its owner.
        auth-required binds sub + actor chain; input-required binds sub and needs a direct human."""
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return "task_not_found", None
            if task[3] <= time.time():
                del self._tasks[task_id]
                return "task_expired", None
            confirming = task[4] == "input-required"
            if task[0][0] != principal["sub"] or (not confirming and task[0][1] != tuple(principal["act"])):
                return "task_principal_mismatch", None
            if task[1:3] != (skill, path):
                return "task_binding_mismatch", None
            if confirming and (principal["act"] or CONFIRM_SCOPE not in principal["scopes"]):
                return "human_confirmation_required", None
            del self._tasks[task_id]
        return None, task[4]

    def _deny(self, status, request_id, principal, skill, reason, task_id=None, binding=None):
        record = evidence_record(principal, skill, "deny", reason, task_id=task_id, binding=binding)
        try:
            persist_record(record, self._evidence)
        except OSError:  # a deny stays a deny; there is just no record to point at
            return _error(status, request_id, reason)
        return _error(status, request_id, reason, self._audit(record))

    def _authorize_and_read(self, request_id, principal, data, task_id=None):
        skill, path = data["skill"], data["arguments"]["path"]
        if principal["act"] and not set(principal["scopes"]) <= DELEGABLE_SCOPES:
            return self._deny(403, request_id, principal, skill, "scope_escalation_denied", task_id)
        required = SKILL_SCOPES.get(skill)
        if required is None:
            return self._deny(403, request_id, principal, skill, "unknown_skill", task_id)
        if required not in principal["scopes"]:
            return self._deny(403, request_id, principal, skill, "insufficient_scope", task_id)
        if self._adapter is None:
            return self._deny(503, request_id, principal, skill, "host_policy_invalid", task_id)
        claimed, binding = None, effect_binding(principal, skill, path)  # ADR 0022: what a pause binds and a resume must match
        if task_id is not None:  # resume = a brand-new admission; the task carries no authority
            reason, claimed = self._claim_task(task_id, principal, skill, path)
            if reason:
                return self._deny(403 if reason == "human_confirmation_required" else 409, request_id, principal, skill, reason, task_id, binding)
        confirmed = claimed == "input-required"
        if skill in self._confirm_skills and not confirmed:  # ADR 0018: pause before PDP, PEP and effect
            return self._pause_for_confirmation(request_id, principal, skill, path, binding)
        run_id = self._policy["context"]["resolved_run_config_ref"]["run_id"]
        result = self._adapter.read(run_id, path, self._budget, principal=principal)
        # ADR 0016: the credential lapsed between admission and effect -> auth-required, no effect.
        if result["reason_code"] == "principal_expired":
            task_id = self._open_task(principal, skill, path)
            state = "auth-required" if task_id else None
        else:
            state = None if task_id is None else "completed" if result["outcome"] == "delivered" else "failed"
        try:
            bundle = json.loads(Path(result["bundle_path"]).read_text(encoding="utf-8")) if result["bundle_path"] else None
            record = evidence_record(principal, skill, result["outcome"], result["reason_code"], bundle and bundle["decision_id"], result["bundle_id"], task_id, confirmed, binding if confirmed else None)
            if not verify_record(record, bundle, self._schemas):
                raise ValueError("a2a_evidence_invalid")
            persist_record(record, self._evidence)
        except (OSError, ValueError, KeyError):  # no verifiable evidence -> no content leaves
            return _error(500, request_id, "a2a_evidence_failed")
        delivered = result["outcome"] == "delivered"
        response = {"outcome": result["outcome"], "reason_code": result["reason_code"], "effect": "read" if delivered else "none", "taint": result["taint"], "audit": self._audit(record), **({"content": result["content"]} if delivered else {}), **({"task": {"kind": "task", "id": task_id, "status": {"state": state}}} if state else {})}
        return 200, {"jsonrpc": "2.0", "id": request_id, "result": response}

    def _pause_for_confirmation(self, request_id, principal, skill, path, binding):
        task_id = self._open_task(principal, skill, path, "input-required")  # full store -> plain deny, no task
        record = evidence_record(principal, skill, "deny", "input_required", task_id=task_id, binding=binding)
        try:
            persist_record(record, self._evidence)
        except OSError:
            return _error(500, request_id, "a2a_evidence_failed")
        response = {"outcome": "deny", "reason_code": "input_required", "effect": "none", "audit": self._audit(record), **({"task": {"kind": "task", "id": task_id, "status": {"state": "input-required"}}} if task_id else {})}
        return 200, {"jsonrpc": "2.0", "id": request_id, "result": response}


def make_server(gateway, host, port):
    """Loopback-only HTTP transport (ADR 0013). Logs method/route/status, never headers or query."""
    if host != "127.0.0.1":
        raise ValueError("loopback_only")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self._send(*((200, gateway.card()) if self.path == CARD_PATH else (404, {"error": "not_found"})))

        def do_POST(self):
            if self.path != "/":
                return self._send(404, {"error": "not_found"})
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self._send(411, {"error": "length_required"})
            if not 0 <= length <= MAX_BODY_BYTES:
                return self._send(413, {"error": "payload_too_large"})
            self._send(*gateway.handle(self.headers.get("Authorization"), self.rfile.read(length)))

        def _send(self, status, payload):
            raw = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            if status in (401, 403):  # RFC 6750 §3: invalid_token vs insufficient_scope
                self.send_header("WWW-Authenticate", f'Bearer realm="adf-a2a", error="{"invalid_token" if status == 401 else "insufficient_scope"}"')
            self.end_headers()
            self.wfile.write(raw)

        def log_request(self, code="-", size="-"):
            route = "card" if self.path == CARD_PATH else "rpc" if self.path == "/" else "other"
            sys.stderr.write(f"a2a {self.command} {route} {code}\n")

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer((host, port), Handler)


def host_validator(issuer, audience):
    """ADF_A2A_JWKS_FILE (absolute) + ADF_A2A_JWKS_SHA256 select RS256 over pinned public keys;
    otherwise the HS256 pilot secret ADF_A2A_HS256_SECRET (hex). A partial JWKS config fails closed."""
    jwks_path, jwks_pin = os.environ.get("ADF_A2A_JWKS_FILE"), os.environ.get("ADF_A2A_JWKS_SHA256")
    if jwks_path is not None or jwks_pin is not None:
        return RS256JwksValidator(jwks_path, jwks_pin, issuer, audience)
    return HS256TokenValidator(bytes.fromhex(os.environ["ADF_A2A_HS256_SECRET"]), issuer, audience)


def _main(argv):
    """Local pilot. `mint` is the HS256 test-double IdP only; RS256 tokens come from a real IdP."""
    issuer, audience = os.environ.get("ADF_A2A_ISSUER", "adf-test-idp"), os.environ.get("ADF_A2A_AUDIENCE", "adf-a2a-local")
    if argv[:1] == ["mint"] and len(argv) in (3, 5):
        ttl = 3600  # pilot IdP double only; a human-in-the-loop flow needs more than the old 300 s
        if len(argv) == 5:
            if argv[3] != "--ttl" or not argv[4].isdecimal() or not 1 <= int(argv[4]) <= 86400:
                print("usage: mint <sub> <scope> [--ttl SECONDS<=86400]", file=sys.stderr)
                return 2
            ttl = int(argv[4])
        print(mint_hs256({"iss": issuer, "aud": audience, "sub": argv[1], "scope": argv[2], "exp": int(time.time()) + ttl}, bytes.fromhex(os.environ["ADF_A2A_HS256_SECRET"])))
        return 0
    if argv != ["serve"]:
        print("usage: python -m integration.a2a_gateway serve | mint <sub> <scope> [--ttl SECONDS]", file=sys.stderr)
        return 2
    from integration.read_gate_host import host_policy_settings, host_settings
    settings = host_settings()
    if settings is None:
        print("host settings invalid (ADF_TRUSTED_REPOSITORY / ADF_EVIDENCE_DIR / ADF_TRUSTED_REVISION / ADF_MAX_OUTPUT_BYTES)", file=sys.stderr)
        return 2
    root, revision, evidence, budget = settings
    port = int(os.environ.get("ADF_A2A_PORT", "8765"))
    confirm = frozenset(filter(None, os.environ.get("ADF_A2A_CONFIRM_SKILLS", "").split(",")))  # ADR 0018, host-owned
    gateway = A2AGateway(host_validator(issuer, audience), root, revision, evidence, **host_policy_settings(), max_output_bytes=budget, port=port, confirm_skills=confirm)
    make_server(gateway, "127.0.0.1", port).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
