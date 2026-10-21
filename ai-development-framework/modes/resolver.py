"""Pure H2-01 Mode and RunConfig resolution."""

from copy import deepcopy
import json
import math
import re

from jsonschema import Draft7Validator
from referencing import Registry, Resource


ALLOWED_BUDGET_OVERRIDES = ("tokens", "seconds", "tool_calls", "cost_usd")
APPROVED_MODE_IDS = frozenset({"prototyper", "builder", "grower", "sweeper", "maintainer"})
ALLOWED_OVERRIDE_PATHS = {
    "model.parameters",
    "seed",
    "experiment_id",
    "trial_id",
    *(f"budget.{field}" for field in ALLOWED_BUDGET_OVERRIDES),
}
MODEL_PARAMETER_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _error(code, field, message):
    return {"errors": [{"code": code, "field": field, "message": message}]}


def _registry(schemas):
    return Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )


def _validation_error(instance, schema_name, schemas, code):
    validator = Draft7Validator(schemas[schema_name], registry=_registry(schemas))
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
    if not errors:
        return None
    path = ".".join(str(part) for part in errors[0].absolute_path) or "$"
    return _error(code, path, "invalid or incomplete input")


def _invalid_model_parameters(parameters):
    return not isinstance(parameters, dict) or any(
        not isinstance(name, str)
        or not MODEL_PARAMETER_NAME.fullmatch(name)
        or type(value) not in (int, float, bool)
        or (type(value) is float and not math.isfinite(value))
        for name, value in parameters.items()
    )


def _override_paths(overrides):
    paths = []
    for key, value in overrides.items():
        if key in ("model", "budget") and isinstance(value, dict):
            paths.extend(f"{key}.{nested}" for nested in value)
        else:
            paths.append(key)
    return paths


def _prohibited_override(overrides):
    return next((path for path in _override_paths(overrides) if path not in ALLOWED_OVERRIDE_PATHS), None)


def _budget_error(budget, ceiling, source):
    for field in ALLOWED_BUDGET_OVERRIDES:
        value, maximum = budget[field], ceiling[field]
        if value is not None and maximum is not None and value > maximum:
            return _error("constraint_conflict", f"budget.{field}", f"exceeds {source} ceiling")
    return None


def _apply_overrides(run_config, overrides, context):
    prohibited = _prohibited_override(overrides)
    if prohibited:
        return _error("override_prohibited", prohibited, "override path is not allowed")
    blocked = set(context["organizational_constraints"]["prohibited_override_paths"])
    for path in _override_paths(overrides):
        if path in blocked:
            return _error("constraint_conflict", path, "override prohibited by organizational constraint")

    result = deepcopy(run_config)
    if "model" in overrides:
        result["model"]["parameters"] = deepcopy(overrides["model"]["parameters"])
    for field in ("seed", "experiment_id", "trial_id"):
        if field in overrides:
            result[field] = overrides[field]
    for field, value in overrides.get("budget", {}).items():
        current = result["budget"][field]
        if current is None or value is None or value > current:
            return _error("budget_expansion", f"budget.{field}", "budget overrides may only reduce known ceilings")
        result["budget"][field] = value
    return result


def _provenance(value, path, source, policy_id, policy_version, output):
    output[path] = {"source": source, "policy_id": policy_id, "policy_version": policy_version}
    if isinstance(value, dict):
        for key, nested in value.items():
            _provenance(nested, f"{path}.{key}", source, policy_id, policy_version, output)


def _resolved_provenance(run_config, mode, context, overrides):
    provenance = {}
    explicit = ("explicit_request", "execution_context", context["context_version"])
    mode_default = ("mode_default", mode["policy"]["id"], mode["policy"]["version"])
    for field, value in run_config.items():
        source = mode_default if field in {"mode", "context_policy", "verification_policy"} else explicit
        _provenance(value, field, *source, provenance)
    _provenance(run_config["task_ref"]["id"], "task_ref.id", "task_derived", "task_spec", "1.0", provenance)
    _provenance(run_config["task_ref"]["revision"], "task_ref.revision", "task_derived", "task_spec", "1.0", provenance)
    if overrides:
        for path in _override_paths(overrides):
            provenance[path] = {"source": "explicit_request", "policy_id": "requested_overrides", "policy_version": "1.0"}
    return provenance


def resolve(request, catalog, schemas):
    """Return a ResolvedRunConfig envelope or stable structured errors without effects."""
    for name in ("catalog", "request", "resolved", "task", "run_config"):
        if name not in schemas:
            return _error("resolver_configuration_error", "schemas", "required schema is unavailable")
    if isinstance(request, dict) and isinstance(request.get("requested_overrides"), dict):
        prohibited = _prohibited_override(request["requested_overrides"])
        if prohibited:
            return _error("override_prohibited", prohibited, "override path is not allowed")
    invalid = _validation_error(catalog, "catalog", schemas, "invalid_catalog")
    if invalid:
        return invalid
    mode_ids = [mode["id"] for mode in catalog["modes"]]
    if len(mode_ids) != len(set(mode_ids)):
        return _error("duplicate_mode", "modes", "catalog contains duplicate mode IDs")
    if set(mode_ids) != APPROVED_MODE_IDS or len(mode_ids) != len(APPROVED_MODE_IDS):
        return _error("invalid_catalog", "modes", "catalog must contain exactly the five approved mode IDs")
    invalid = _validation_error(request, "request", schemas, "invalid_request")
    if invalid:
        return invalid
    parameters = request["execution_context"]["model"]["parameters"]
    if _invalid_model_parameters(parameters):
        return _error("invalid_model_parameters", "execution_context.model.parameters", "model parameters must be numeric or boolean scalars")
    overrides = request["requested_overrides"]
    if "model" in overrides and _invalid_model_parameters(overrides["model"]["parameters"]):
        return _error("invalid_model_parameters", "requested_overrides.model.parameters", "model parameters must be numeric or boolean scalars")
    invalid = _validation_error(request["task_spec"], "task", schemas, "invalid_task_spec")
    if invalid:
        return invalid

    mode = next((item for item in catalog["modes"] if item["id"] == request["requested_mode"]), None)
    if mode is None:
        return _error("unknown_mode", "requested_mode", "mode is not in the catalog")
    context = request["execution_context"]
    if mode["id"] not in context["organizational_constraints"]["allowed_modes"]:
        return _error("constraint_conflict", "requested_mode", "mode is not allowed by organizational constraint")

    base_budget = context["budget"]
    for source, ceiling in (
        ("organizational constraint", context["organizational_constraints"]["budget_ceiling"]),
        ("runtime capability", context["runtime_capability_ceilings"]["budget_ceiling"]),
    ):
        conflict = _budget_error(base_budget, ceiling, source)
        if conflict:
            return conflict

    run_config = {
        "schema_version": "1.0",
        "run_id": context["run_id"],
        "task_ref": {"id": request["task_spec"]["task_id"], "revision": request["task_spec"]["revision"], "sha256": context["task_ref_sha256"]},
        "model": deepcopy(context["model"]),
        "adapter": deepcopy(context["adapter"]),
        "mode": {"id": mode["id"], "version": mode["version"]},
        "context_policy": deepcopy(mode["context_policy"]),
        "toolset": deepcopy(context["toolset"]),
        "runtime": deepcopy(context["runtime"]),
        "budget": deepcopy(base_budget),
        "verification_policy": deepcopy(mode["verification_policy"]),
        "policy_hash": context["policy_hash"],
        "seed": context["seed"],
        "experiment_id": context["experiment_id"],
        "trial_id": context["trial_id"],
    }
    run_config = _apply_overrides(run_config, request["requested_overrides"], context)
    if "errors" in run_config:
        return run_config
    for source, ceiling in (
        ("organizational constraint", context["organizational_constraints"]["budget_ceiling"]),
        ("runtime capability", context["runtime_capability_ceilings"]["budget_ceiling"]),
    ):
        conflict = _budget_error(run_config["budget"], ceiling, source)
        if conflict:
            return conflict

    invalid = _validation_error(run_config, "run_config", schemas, "invalid_run_config")
    if invalid:
        return invalid
    restrictions = [
        {"id": "organizational-constraints", "source": "organizational_constraint", "version": context["organizational_constraints"]["version"]},
        {"id": "runtime-capability-ceilings", "source": "runtime_capability_ceiling", "version": context["runtime_capability_ceilings"]["version"]},
    ] + [
        {"id": restriction["id"], "source": "mode_restriction", "version": restriction["version"]}
        for restriction in mode["restrictions"]
    ]
    resolved = {
        "resolver_version": "1.0",
        "mode_id": mode["id"],
        "mode_catalog_version": catalog["catalog_version"],
        "run_config": run_config,
        "provenance": _resolved_provenance(run_config, mode, context, request["requested_overrides"]),
        "applied_restrictions": restrictions,
    }
    invalid = _validation_error(resolved, "resolved", schemas, "invalid_resolved_run_config")
    if invalid:
        return invalid
    return json.loads(json.dumps(resolved, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
