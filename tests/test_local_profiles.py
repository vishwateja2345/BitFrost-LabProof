"""Offline profile contracts: no workers, provisioning or imported authority."""
from dataclasses import FrozenInstanceError, asdict, replace
from hashlib import sha256

import pytest

from labproof import local_engine, local_profiles
from labproof.contracts import canonical
from labproof.packs import FixtureSpec, OperationRequest, PackError, PackRegistry, REGISTRY
from labproof.sandbox.policy import LaunchPlan, SandboxLimits, SandboxPolicyError


IMAGE = "sha256:" + "a" * 64
LEGACY = {
    "python": ("python-invariants", "python", "/usr/local/bin/python", ("-I", "-B", "/worker/worker.py")),
    "typescript": ("typescript-node-test", "node", "/usr/local/bin/node", ("/worker/worker.mjs",)),
    "c": ("c-gcc", "c", "/worker/observe", ()),
    "rust": ("rust-cargo-test", "rust", "/worker/observe", ()),
}


def request(pack="python", *, operation=None, fixture=None, parameters=None):
    return {"schema_version": "1.0", "pack_id": pack,
            "operation_id": operation or LEGACY[pack][0],
            "fixture_id": fixture or f"{pack}-synthetic-v1",
            "parameters": {"variant": "alpha"} if parameters is None else parameters}


@pytest.mark.parametrize("pack", LEGACY)
@pytest.mark.parametrize("variant", local_profiles.VARIANTS)
def test_exact_legacy_plans_and_limits(pack, variant):
    value = request(pack, parameters={"variant": variant})
    profile = local_profiles.resolve_profile(value)
    operation, language, executable, prefix = LEGACY[pack]
    assert profile is local_profiles.PROFILES[(pack, operation, f"{pack}-synthetic-v1")]
    assert profile is local_profiles.default_profile(pack)
    assert profile.language == language
    assert local_profiles.build_launch_plan(value, IMAGE) == LaunchPlan(
        f"{operation}-{variant}", IMAGE, (executable, *prefix, operation, variant))
    expected = SandboxLimits(wall_seconds=60, memory_bytes=536870912,
                             scratch_bytes=67108864, output_executable=True) if pack == "rust" else SandboxLimits()
    # Integer/float JSON spelling is part of the retained config contract.
    assert canonical(asdict(profile.limits)) == canonical(asdict(expected))


def test_immutable_profiles_and_derived_compatibility_view():
    assert dict(local_engine.OPERATIONS) == LEGACY
    assert local_engine.OPERATIONS is local_profiles.OPERATIONS
    profile = local_profiles.resolve_profile(request())
    with pytest.raises(TypeError):
        local_profiles.PROFILES[("python", profile.operation_id, profile.fixture_id)] = profile
    with pytest.raises(TypeError):
        local_engine.OPERATIONS["python"] = LEGACY["c"]
    with pytest.raises(FrozenInstanceError):
        profile.executable = "/bin/sh"
    with pytest.raises(FrozenInstanceError):
        profile.limits.wall_seconds = 60
    with pytest.raises(TypeError):
        profile.prefix[0] = "-c"


@pytest.mark.parametrize("field", ("pack_id", "operation_id", "fixture_id"))
@pytest.mark.parametrize("bad", (None, [], 1, True, "", "../python", "python\n", "python;id", "x" * 81))
def test_malformed_ids_fail_through_registry(field, bad):
    value = request()
    value[field] = bad
    with pytest.raises(PackError):
        local_profiles.resolve_profile(value)
    with pytest.raises(PackError):
        local_profiles.build_launch_plan(value, IMAGE)
    with pytest.raises(PackError):
        local_profiles.canonical_request_key(value, "observation")


@pytest.mark.parametrize("operation", ("python-ast", "python-ruff", "python-pytest"))
def test_registered_but_unmapped_operation_fails_closed(operation):
    value = request(operation=operation)
    REGISTRY.validate_operation(value)
    with pytest.raises(PackError, match="No reviewed local operation/fixture"):
        local_profiles.build_launch_plan(value, IMAGE)


def test_registered_but_unmapped_fixture_fails_closed(monkeypatch):
    pack = REGISTRY.get("python")
    monkeypatch.setattr(local_profiles, "REGISTRY", PackRegistry((replace(
        pack, fixtures=(*pack.fixtures, FixtureSpec("python-second-fixture"))),)))
    value = request(fixture="python-second-fixture")
    local_profiles.REGISTRY.validate_operation(value)
    with pytest.raises(PackError, match="No reviewed local operation/fixture"):
        local_profiles.resolve_profile(value)
    with pytest.raises(PackError):
        local_profiles.build_launch_plan(value, IMAGE)


@pytest.mark.parametrize("changes", (
    {"operation_id": "c-gcc"}, {"fixture_id": "c-synthetic-v1"},
    {"parameters": {"variant": "epsilon"}}, {"parameters": {"variant": "alpha", "seed": 1}},
    {"argv": ["/bin/sh"]}, {"image_id": IMAGE}, {"schema_version": "2.0"},
))
def test_no_request_commands_images_or_unsupported_combinations(changes):
    with pytest.raises(PackError):
        local_profiles.build_launch_plan({**request(), **changes}, IMAGE)


@pytest.mark.parametrize("image", ("python:latest", "sha256:" + "a" * 63, None))
def test_plan_reuses_exact_image_validation(image):
    with pytest.raises(SandboxPolicyError):
        local_profiles.build_launch_plan(request(), image)


def test_canonical_key_includes_full_validated_request():
    first = request(operation="python-hypothesis", parameters={"variant": "alpha", "seed": 7, "cases": 20})
    reordered = request(operation="python-hypothesis", parameters={"cases": 20, "seed": 7, "variant": "alpha"})
    expected = sha256(canonical({"request": first, "phase": "observation"})).hexdigest()
    assert local_profiles.canonical_request_key(first, "observation") == expected
    assert local_profiles.canonical_request_key(reordered, "observation") == expected
    assert local_profiles.canonical_request_key(OperationRequest.parse(first), "observation") == expected
    keys = {expected, local_profiles.canonical_request_key(first, "verification")}
    for name, value in (("variant", "beta"), ("seed", 8), ("cases", 21)):
        changed = {**first, "parameters": {**first["parameters"], name: value}}
        keys.add(local_profiles.canonical_request_key(changed, "observation"))
    assert len(keys) == 5
    # Computing identity of a declaration does not make it locally executable.
    with pytest.raises(PackError):
        local_profiles.build_launch_plan(first, IMAGE)


def test_key_separates_registered_fixtures_and_operations(monkeypatch):
    pack = REGISTRY.get("python")
    monkeypatch.setattr(local_profiles, "REGISTRY", PackRegistry((replace(
        pack, fixtures=(*pack.fixtures, FixtureSpec("python-second-fixture"))),)))
    values = (request(), request(fixture="python-second-fixture"), request(operation="python-ast"))
    assert len({local_profiles.canonical_request_key(value, "observation") for value in values}) == 3
    assert local_profiles.canonical_request_key(request(), "observation") != local_profiles.canonical_request_key(
        request(), "verification")


@pytest.mark.parametrize("parameters", (
    {"variant": "alpha", "seed": -1, "cases": 1},
    {"variant": "alpha", "seed": 65536, "cases": 1},
    {"variant": "alpha", "seed": True, "cases": 1},
    {"variant": "alpha", "seed": 1, "cases": 101},
    {"variant": "alpha", "seed": 1},
))
def test_key_cannot_bypass_registry_parameter_validation(parameters):
    with pytest.raises(PackError):
        local_profiles.canonical_request_key(request(operation="python-hypothesis", parameters=parameters), "observation")


@pytest.mark.parametrize("phase", (None, [], True, "", "observation\n", "other"))
def test_key_rejects_invalid_phase(phase):
    with pytest.raises(PackError, match="phase"):
        local_profiles.canonical_request_key(request(), phase)


def test_registry_validation_precedes_identity_encoding(monkeypatch):
    def no_encoding(*args):
        pytest.fail("Invalid request must fail before canonicalization")
    monkeypatch.setattr(local_profiles, "canonical", no_encoding)
    with pytest.raises(PackError):
        local_profiles.canonical_request_key({**request(), "fixture_id": "unknown"}, "observation")


def test_registry_extension_cannot_silently_expand_local_parameters(monkeypatch):
    pack = REGISTRY.get("python")
    seed = next(op for op in pack.operations if op.operation_id == "python-hypothesis").parameters[1]
    operations = tuple(replace(op, parameters=(*op.parameters, seed))
                       if op.operation_id == "python-invariants" else op for op in pack.operations)
    monkeypatch.setattr(local_profiles, "REGISTRY", PackRegistry((replace(pack, operations=operations),)))
    value = request(parameters={"variant": "alpha", "seed": 1})
    local_profiles.REGISTRY.validate_operation(value)
    with pytest.raises(PackError, match="Parameters lack a reviewed local mapping"):
        local_profiles.build_launch_plan(value, IMAGE)
