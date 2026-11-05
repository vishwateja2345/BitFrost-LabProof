"""Contract tests, not tool/parser or real-containment acceptance evidence."""
from dataclasses import FrozenInstanceError, replace
import hashlib

import pytest

from labproof.packs import (
    DiagnosticRef, ExecutionAcceptance, FixtureSpec, OperationRequest,
    PackError, PackRegistry, ParameterSpec, REGISTRY, ResourceLimits,
    ToolMaturity, ToolResult, ToolSpec,
)


def request(pack="python", operation="python-ast", **parameters):
    return {"schema_version": "1.0", "pack_id": pack, "operation_id": operation,
            "fixture_id": f"{pack}-synthetic-v1", "parameters": {"variant": "alpha", **parameters}}


def test_catalogue_is_declared_and_unprovisioned():
    assert tuple(p.pack_id for p in REGISTRY.packs) == ("python", "typescript", "c", "rust")
    for pack in REGISTRY.packs:
        assert not pack.provisioned
        assert pack.image_digest is None and pack.toolchain_version is None
        assert all(f.source_digest is None for f in pack.fixtures)
        assert all(t.version is None and t.maturity == ToolMaturity.DECLARED for t in pack.tools)
        for operation in pack.operations:
            parameters = {p.name: p.choices[0] if p.kind == "enum" else p.minimum for p in operation.parameters}
            value = request(pack.pack_id, operation.operation_id, **parameters)
            assert REGISTRY.validate_operation(value).to_dict() == value
            with pytest.raises(PackError, match="unprovisioned"):
                REGISTRY.require_execution(value)


def test_immutable_snapshots_and_stable_hash():
    source = request()
    parsed = OperationRequest.parse(source)
    source["parameters"]["variant"] = "beta"
    assert dict(parsed.parameters) == {"variant": "alpha"}
    exported = REGISTRY.get("python").to_dict()
    exported["tools"][0]["version"] = "invented"
    assert REGISTRY.get("python").tools[0].version is None
    with pytest.raises(FrozenInstanceError):
        parsed.pack_id = "rust"
    assert REGISTRY.get("python").digest == REGISTRY.get("python").digest
    assert replace(REGISTRY.get("python"), pack_version="0.2.0").digest != REGISTRY.get("python").digest


@pytest.mark.parametrize("field,value", [
    ("schema_version", "2.0"), ("pack_id", []), ("pack_id", "unknown"),
    ("operation_id", "sh"), ("operation_id", "python-ast;id"),
    ("fixture_id", "../fixture"), ("fixture_id", "https://example.com"),
    ("fixture_id", "C:\\temp\\fixture"), ("parameters", []),
])
def test_rejects_malformed_operation(field, value):
    payload = request()
    payload[field] = value
    with pytest.raises(PackError):
        REGISTRY.validate_operation(payload)


@pytest.mark.parametrize("key", ["command", "argv", "url", "path", "flags", "image_digest", "resources"])
def test_rejects_extra_request_and_parameter_fields(key):
    payload = request()
    payload[key] = "anything"
    with pytest.raises(PackError):
        REGISTRY.validate_operation(payload)
    payload = request(**{key: "anything"})
    with pytest.raises(PackError):
        REGISTRY.validate_operation(payload)


@pytest.mark.parametrize("value", [True, False, -1, 65536, 10**10000, 1.0, "1", None, [], float("inf"), float("nan")], ids=lambda value: type(value).__name__)
def test_strict_bounded_integer_parameters(value):
    with pytest.raises(PackError):
        REGISTRY.validate_operation(request(operation="python-hypothesis", seed=value, cases=10))


@pytest.mark.parametrize("value", ["../normal", "--help", "https://example.com", [], True, "unknown", "defective", "corrected", "normal", "ambiguous"])
def test_enum_parameters_are_not_strings_to_execute(value):
    with pytest.raises(PackError):
        REGISTRY.validate_operation(request(variant=value))


def test_operation_parameter_ceiling_matches_requests():
    original = REGISTRY.get("python")
    parameters = tuple(ParameterSpec(f"p{i}", "integer", minimum=0, maximum=1)
                       for i in range(16))
    operation = replace(original.operations[0], parameters=parameters)
    registry = PackRegistry((replace(original, operations=(operation,)),))
    payload = request()
    payload["parameters"] = {p.name: 0 for p in parameters}
    assert registry.validate_operation(payload).to_dict() == payload
    with pytest.raises(PackError, match="Too many operation parameters"):
        replace(operation, parameters=parameters + (ParameterSpec("p16", "integer", minimum=0, maximum=1),))


def test_required_and_bounded_parameters():
    with pytest.raises(PackError):
        REGISTRY.validate_operation(request(operation="python-hypothesis"))
    with pytest.raises(PackError):
        REGISTRY.validate_operation(request(operation="python-hypothesis", seed=1, cases=101))
    for seed, cases in ((0, 1), (65535, 100)):
        REGISTRY.validate_operation(request(operation="python-hypothesis", seed=seed, cases=cases))


@pytest.mark.parametrize("field", list(vars(ResourceLimits())))
@pytest.mark.parametrize("value", [True, 0, -1, 10**10000, 1.0, float("inf"), float("nan"), "1"], ids=lambda value: type(value).__name__)
def test_resource_limits_reject_noninteger_and_excessive_values(field, value):
    with pytest.raises(PackError):
        ResourceLimits(**{field: value})


def test_duplicates_and_mutable_catalogues_rejected():
    pack = REGISTRY.get("python")
    for update in ({"tools": pack.tools + (pack.tools[0],)},
                   {"operations": pack.operations + (pack.operations[0],)},
                   {"fixtures": pack.fixtures + (pack.fixtures[0],)},
                   {"tools": list(pack.tools)}, {"read_roots": ("/home",)}):
        with pytest.raises(PackError):
            replace(pack, **update)
    with pytest.raises(PackError):
        PackRegistry((pack, pack))
    with pytest.raises(PackError):
        PackRegistry((pack, replace(pack, pack_id="second")))
    with pytest.raises(PackError):
        OperationRequest("python", "python-ast", "python-synthetic-v1", (("variant", "alpha"), ("variant", "beta")))
    with pytest.raises(PackError):
        ParameterSpec("mode", "enum", ("one", "one"))


@pytest.mark.parametrize("digest", ["latest", "sha256:abc", "https://example.com", 123, [], "A" * 64])
def test_reject_invalid_digests(digest):
    with pytest.raises(PackError):
        replace(REGISTRY.get("python"), image_digest=digest)
    with pytest.raises(PackError):
        FixtureSpec("fixture", digest)


def test_promotion_requires_review_evidence():
    with pytest.raises(PackError):
        ToolSpec("ruff", maturity=ToolMaturity.PARSER_TESTED)
    with pytest.raises(PackError):
        ToolSpec("ruff", maturity="declared")


def test_acceptance_is_bound_to_entire_pack_and_image():
    # Explicit synthetic test identities, never presented as real image evidence.
    digest = hashlib.sha256(b"contract-test-only-not-an-image").hexdigest()
    base = REGISTRY.get("python")
    pack = replace(base, image_digest=f"sha256:{digest}", toolchain_version="test-1",
                   fixtures=tuple(replace(f, source_digest=digest) for f in base.fixtures),
                   operations=tuple(replace(op, adapter_digest=digest) for op in base.operations),
                   tools=tuple(replace(t, version="test-1", maturity=ToolMaturity.CONTAINMENT_TESTED,
                                       review_digest=digest) for t in base.tools))
    registry = PackRegistry((pack,))
    assert pack.provisioned
    with pytest.raises(PackError, match="acceptance required"):
        registry.require_execution(request())
    acceptance = ExecutionAcceptance(pack.digest, pack.image_digest, "test-runtime", digest, digest)
    assert registry.require_execution(request(), acceptance) is pack
    with pytest.raises(PackError, match="mismatched"):
        registry.require_execution(request(), replace(acceptance, pack_digest=digest))
    changed = PackRegistry((replace(pack, resources=ResourceLimits(wall_seconds=29)),))
    with pytest.raises(PackError, match="mismatched"):
        changed.require_execution(request(), acceptance)
    unaccepted = PackRegistry((replace(pack, tools=tuple(replace(t, maturity=ToolMaturity.PARSER_TESTED) for t in pack.tools)),))
    with pytest.raises(PackError, match="containment unaccepted"):
        unaccepted.require_execution(request(), acceptance)


def result():
    digest = hashlib.sha256(b"contract-test-diagnostic").hexdigest()
    return ToolResult(OperationRequest.parse(request()), f"sha256:{digest}", digest,
                      "ast", "test-1", "test-worker", "test-reset", "completed", 0,
                      False, False, (DiagnosticRef("diagnostic-one", digest, 8),), ("static-warning",))


def test_tool_result_roundtrip_and_nonverdict_semantics():
    value = result()
    assert ToolResult.parse(value.to_dict()) == value
    # Nonzero scanner status need not mean an execution error or vulnerability.
    assert replace(value, exit_code=1).status == "completed"
    assert value.peak_memory_bytes is None
    payload = value.to_dict()
    payload["confirmed"] = True
    with pytest.raises(PackError):
        ToolResult.parse(payload)


@pytest.mark.parametrize("update", [
    {"exit_code": True}, {"exit_code": 10**10000}, {"timed_out": 1},
    {"status": "timeout"}, {"exit_code": None}, {"truncated": "false"},
    {"wall_millis": True}, {"peak_memory_bytes": -1},
    {"worker_id": "../worker"}, {"signals": ("https://example.com",)},
    {"signals": ("warning", "warning")},
])
def test_tool_result_rejects_invalid_observations(update):
    with pytest.raises(PackError):
        replace(result(), **update)


def test_diagnostics_bounded_immutable_unique():
    value = result()
    with pytest.raises(PackError):
        replace(value, diagnostics=value.diagnostics * 2)
    with pytest.raises(PackError):
        replace(value, diagnostics=list(value.diagnostics))
    with pytest.raises(PackError):
        replace(value.diagnostics[0], bytes=True)
    with pytest.raises(PackError):
        replace(value.diagnostics[0], artifact_id="output/file.txt")
    with pytest.raises(PackError):
        replace(value, diagnostics=tuple(replace(value.diagnostics[0], artifact_id=f"diag-{i}", bytes=2000000) for i in range(5)))
