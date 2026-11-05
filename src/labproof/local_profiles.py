"""Trusted local v1 mappings, not imported registrations or runtime acceptance.

Only the four reviewed operation/fixture pairs below can produce launch plans.
Images still come from trusted provisioning, and the session still earns its own
containment acceptance. The request key is a future evidence building block; it
neither changes v1 artifact identities nor identifies a fresh worker/reset.
"""
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType

from .contracts import canonical, require, ID_RE
from .packs import REGISTRY, PackError
from .sandbox.policy import LaunchPlan, SandboxLimits

VARIANTS = ("alpha", "beta", "gamma", "delta")
PHASES = ("observation", "verification")


@dataclass(frozen=True, slots=True)
class LocalOperationProfile:
    pack_id: str
    operation_id: str
    fixture_id: str
    language: str
    executable: str
    prefix: tuple[str, ...]
    limits: SandboxLimits = SandboxLimits()


# Authored here only. Catalogue declarations alone never grant a local adapter.
PROFILES = MappingProxyType({
    (profile.pack_id, profile.operation_id, profile.fixture_id): profile
    for profile in (
        LocalOperationProfile("python", "python-invariants", "python-synthetic-v1",
                              "python", "/usr/local/bin/python", ("-I", "-B", "/worker/worker.py")),
        LocalOperationProfile("typescript", "typescript-node-test", "typescript-synthetic-v1",
                              "node", "/usr/local/bin/node", ("/worker/worker.mjs",)),
        LocalOperationProfile("c", "c-gcc", "c-synthetic-v1", "c", "/worker/observe", ()),
        LocalOperationProfile("rust", "rust-cargo-test", "rust-synthetic-v1", "rust", "/worker/observe", (),
                              SandboxLimits(wall_seconds=60, memory_bytes=536870912,
                                            scratch_bytes=67108864, output_executable=True)),
    )
})
_DEFAULT_PROFILES = MappingProxyType({profile.pack_id: profile for profile in PROFILES.values()})
# Compatibility view for the current CLI and callers; not execution authority.
OPERATIONS = MappingProxyType({
    profile.pack_id: (profile.operation_id, profile.language, profile.executable, profile.prefix)
    for profile in PROFILES.values()
})


def default_profile(pack_id):
    """Select the existing v1 operation, without asserting runtime readiness."""
    REGISTRY.get(pack_id)
    profile = _DEFAULT_PROFILES.get(pack_id)
    if profile is None:
        raise PackError("Local execution unavailable for this pack")
    return profile


def _resolve(request):
    request = REGISTRY.validate_operation(request)
    profile = PROFILES.get((request.pack_id, request.operation_id, request.fixture_id))
    if profile is None:
        raise PackError("No reviewed local operation/fixture mapping")
    # Do not silently ignore parameters if a declaration grows before its local
    # adapter is reviewed. Only the fixed legacy variant argument is supported.
    parameters = dict(request.parameters)
    if set(parameters) != {"variant"} or parameters["variant"] not in VARIANTS:
        raise PackError("Parameters lack a reviewed local mapping")
    return request, profile


def resolve_profile(request):
    """Validate the full catalogue request, then require its exact local pair."""
    return _resolve(request)[1]


def build_launch_plan(request, image_id):
    """Build unchanged v1 argv; image_id must be from trusted provisioning.

    No commands, image IDs or extra argv parameters are read from the request.
    This host-internal function is not an imported-evidence execution API.
    """
    request, profile = _resolve(request)
    variant = dict(request.parameters)["variant"]
    return LaunchPlan(f"{profile.operation_id}-{variant}", image_id,
                      (profile.executable, *profile.prefix, profile.operation_id, variant))


def canonical_request_key(request, phase):
    """Hash the validated full request and phase, not a v1 execution identity.

    Registry validation (including parameter bounds) precedes canonicalization.
    Fixture, variant, seed and all other declared parameters are retained. This
    does not require a local mapping and cannot authorize execution; future
    evidence must additionally bind fresh worker/reset and provenance identities.
    """
    request = REGISTRY.validate_operation(request)
    if type(phase) is not str or phase not in PHASES:
        raise PackError("Unknown local evidence phase")
    return sha256(canonical({"request": request.to_dict(), "phase": phase})).hexdigest()


@dataclass(frozen=True, slots=True)
class ExperimentProfile:
    """V2 semantics attached only to an existing reviewed local adapter."""
    local: LocalOperationProfile
    parser_id: str = "parsed-worker-observation-1"
    grader_id: str = "host_control_rules_v1"
    exit_codes: tuple[int, ...] = (0,)
    required_variants: tuple[str, ...] = ("alpha", "beta", "gamma")
    max_actions: int = 8

    @property
    def profile_id(self):
        return self.local.operation_id + "-experiment-2"


EXPERIMENT_PROFILES = MappingProxyType({p.profile_id: p for p in
    (ExperimentProfile(local) for local in PROFILES.values())})


def validate_experiment_plan(value):
    """Imported plans select bounded requests, never executable authority."""
    require(type(value) is dict and set(value) == {"schema_version", "profile_id", "budgets", "steps"}, "Invalid experiment plan")
    require(value["schema_version"] == "experiment-plan-2", "Unsupported experiment plan")
    require(type(value["profile_id"]) is str and value["profile_id"] in EXPERIMENT_PROFILES, "Unknown experiment profile")
    profile = EXPERIMENT_PROFILES[value["profile_id"]]
    budgets = value["budgets"]
    limits = profile.local.limits
    require(type(budgets) is dict and set(budgets) == {"actions", "wall_seconds", "output_bytes"}, "Invalid experiment budgets")
    for key, maximum in (("actions", profile.max_actions),
                         ("wall_seconds", int(profile.max_actions * (limits.wall_seconds + limits.cleanup_seconds))),
                         ("output_bytes", profile.max_actions * limits.output_bytes)):
        require(type(budgets[key]) is int and 0 <= budgets[key] <= maximum, "Invalid experiment budget: " + key)
    steps = value["steps"]
    require(type(steps) is list and 1 <= len(steps) <= profile.max_actions, "Invalid experiment steps")
    seen, slots = {}, set()
    for step in steps:
        require(type(step) is dict and set(step) == {"id", "request", "phase", "replay_of"}, "Invalid experiment step")
        require(type(step["id"]) is str and ID_RE.fullmatch(step["id"]) and step["id"] not in seen, "Duplicate/invalid step ID")
        request, local = _resolve(step["request"])
        require(local == profile.local, "Request/profile mismatch")
        key = canonical_request_key(request, step["phase"])
        require(key not in slots, "Duplicate experiment request/phase")
        slots.add(key)
        if step["phase"] == "observation":
            require(step["replay_of"] is None, "Observation cannot replay")
        else:
            ref = step["replay_of"]
            require(type(ref) is str and ref in seen, "Dangling/forward replay")
            original = seen[ref]
            require(original["phase"] == "observation" and canonical(original["request"]) == canonical(request.to_dict()), "Replay request mismatch")
        seen[step["id"]] = step
    return profile


def default_experiment_plan(pack_id):
    local = default_profile(pack_id)
    profile = EXPERIMENT_PROFILES[local.operation_id + "-experiment-2"]
    variants = profile.required_variants
    steps = [{"id": f"{phase}_{variant}", "request": {
        "schema_version": "1.0", "pack_id": pack_id, "operation_id": local.operation_id,
        "fixture_id": local.fixture_id, "parameters": {"variant": variant}},
        "phase": phase, "replay_of": None if phase == "observation" else f"observation_{variant}"}
        for phase in PHASES for variant in variants]
    return {"schema_version": "experiment-plan-2", "profile_id": profile.profile_id,
            "budgets": {"actions": len(steps),
                        "wall_seconds": int(len(steps) * (local.limits.wall_seconds + local.limits.cleanup_seconds)),
                        "output_bytes": len(steps) * local.limits.output_bytes}, "steps": steps}
