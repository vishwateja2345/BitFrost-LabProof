"""Non-executing language-pack contracts; declarations are not installed tools.

Only trusted application code constructs registries/acceptance records. Imported
manifests and model output cannot register tools or authorize execution. Requests
contain catalogue IDs and typed bounded parameters, never argv, paths or URLs.
A future runtime owns the separately reviewed fixed-argv mapping and must check
its own readiness/acceptance immediately before starting a worker.
"""
from dataclasses import dataclass
from enum import StrEnum
import hashlib
import re

from .contracts import SHA_RE, canonical

SCHEMA_VERSION = "1.0"
_TOKEN = re.compile(r"[a-z][a-z0-9_-]{0,79}\Z")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,79}\Z")
_IMAGE = re.compile(r"sha256:[a-f0-9]{64}\Z")


class PackError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise PackError(message)


def _token(value):
    _require(type(value) is str and _TOKEN.fullmatch(value), "Invalid catalogue ID")


def _version(value):
    _require(type(value) is str and _VERSION.fullmatch(value), "Invalid version")


def _digest(value, *, image=False, optional=False):
    if optional and value is None:
        return
    _require(type(value) is str and (_IMAGE if image else SHA_RE).fullmatch(value), "Invalid digest")


def _integer(value, low, high):
    # Compare before any conversion: bool, floats and arbitrarily big ints fail.
    _require(type(value) is int and low <= value <= high, "Integer outside fixed bounds")


def _object(value, fields):
    _require(type(value) is dict and set(value) == set(fields.split()), "Unexpected or missing fields")


def _items(values, cls, key, *, empty=False):
    _require(type(values) is tuple and (empty or bool(values)) and len(values) <= 64, "Expected bounded immutable tuple")
    _require(all(type(item) is cls for item in values), "Unexpected catalogue entry type")
    ids = [getattr(item, key) for item in values]
    _require(len(set(ids)) == len(ids), "Duplicate catalogue ID")


class ToolMaturity(StrEnum):
    DECLARED = "declared"
    PARSER_TESTED = "parser-tested"
    CONTAINMENT_TESTED = "containment-tested"
    CONTROL_VALIDATED = "control-validated"
    EVALUATION_APPROVED = "evaluation-approved"


@dataclass(frozen=True)
class ResourceLimits:
    wall_seconds: int = 30
    memory_bytes: int = 268435456
    cpu_millis: int = 1000
    pids: int = 32
    scratch_bytes: int = 16777216
    output_bytes: int = 1048576
    artifact_count: int = 16

    def __post_init__(self):
        for name, high in (("wall_seconds", 120), ("memory_bytes", 1073741824),
                           ("cpu_millis", 2000), ("pids", 128),
                           ("scratch_bytes", 67108864), ("output_bytes", 2000000),
                           ("artifact_count", 64)):
            _integer(getattr(self, name), 1, high)

    def to_dict(self):
        return dict(vars(self))


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    kind: str
    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None

    def __post_init__(self):
        _token(self.name)
        _require(type(self.kind) is str and self.kind in ("enum", "integer"), "Unsupported parameter type")
        _require(type(self.choices) is tuple, "Choices must be immutable")
        if self.kind == "enum":
            _require(1 <= len(self.choices) <= 16 and self.minimum is None and self.maximum is None, "Invalid enum specification")
            for choice in self.choices:
                _token(choice)
            _require(len(set(self.choices)) == len(self.choices), "Duplicate enum choice")
        else:
            _require(not self.choices, "Integer cannot have choices")
            _integer(self.minimum, 0, 2147483647)
            _integer(self.maximum, self.minimum, 2147483647)

    def validate(self, value):
        if self.kind == "enum":
            _require(type(value) is str and value in self.choices, "Unknown enum parameter")
        else:
            _integer(value, self.minimum, self.maximum)

    def to_dict(self):
        return {"name": self.name, "kind": self.kind, "choices": list(self.choices),
                "minimum": self.minimum, "maximum": self.maximum}


@dataclass(frozen=True)
class FixtureSpec:
    fixture_id: str
    source_digest: str | None = None

    def __post_init__(self):
        _token(self.fixture_id)
        _digest(self.source_digest, optional=True)

    def to_dict(self):
        return dict(vars(self))


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    version: str | None = None
    maturity: ToolMaturity = ToolMaturity.DECLARED
    review_digest: str | None = None

    def __post_init__(self):
        _token(self.tool_id)
        if self.version is not None:
            _version(self.version)
        _require(type(self.maturity) is ToolMaturity, "Invalid tool maturity")
        _digest(self.review_digest, optional=True)
        if self.maturity != ToolMaturity.DECLARED:
            _require(self.version is not None and self.review_digest is not None, "Promotion requires versioned review evidence")

    def to_dict(self):
        return {"tool_id": self.tool_id, "version": self.version,
                "maturity": self.maturity.value, "review_digest": self.review_digest}


@dataclass(frozen=True)
class OperationSpec:
    operation_id: str
    tool_id: str
    parameters: tuple[ParameterSpec, ...]
    oracle_id: str
    # Digest of the separately reviewed, trusted fixed-argv/config adapter.
    # No executable template is accepted from a request or imported artifact.
    adapter_digest: str | None = None
    output_schema: str = "tool-result-1"

    def __post_init__(self):
        for value in (self.operation_id, self.tool_id, self.oracle_id):
            _token(value)
        _items(self.parameters, ParameterSpec, "name", empty=True)
        _require(len(self.parameters) <= 16, "Too many operation parameters")
        _digest(self.adapter_digest, optional=True)
        _require(self.output_schema == "tool-result-1", "Unsupported result schema")

    def to_dict(self):
        return {"operation_id": self.operation_id, "tool_id": self.tool_id,
                "parameters": [p.to_dict() for p in self.parameters],
                "oracle_id": self.oracle_id, "adapter_digest": self.adapter_digest,
                "output_schema": self.output_schema}


@dataclass(frozen=True)
class PackManifest:
    pack_id: str
    pack_version: str
    language: str
    fixtures: tuple[FixtureSpec, ...]
    tools: tuple[ToolSpec, ...]
    operations: tuple[OperationSpec, ...]
    resources: ResourceLimits = ResourceLimits()
    image_digest: str | None = None
    toolchain_version: str | None = None
    schema_version: str = SCHEMA_VERSION
    # Fixed container-only roots; these are not host mounts or request fields.
    read_roots: tuple[str, ...] = ("/fixture",)
    write_roots: tuple[str, ...] = ("/scratch", "/output")

    def __post_init__(self):
        _require(self.schema_version == SCHEMA_VERSION, "Unsupported pack schema")
        _token(self.pack_id)
        _version(self.pack_version)
        _require(type(self.language) is str and self.language in ("python", "typescript", "c", "rust"), "Unknown language")
        _items(self.fixtures, FixtureSpec, "fixture_id")
        _items(self.tools, ToolSpec, "tool_id")
        _items(self.operations, OperationSpec, "operation_id")
        _require(type(self.resources) is ResourceLimits, "Invalid resource limits")
        _digest(self.image_digest, image=True, optional=True)
        if self.toolchain_version is not None:
            _version(self.toolchain_version)
        _require(type(self.read_roots) is tuple and self.read_roots == ("/fixture",), "Read roots are fixed")
        _require(type(self.write_roots) is tuple and self.write_roots == ("/scratch", "/output"), "Write roots are fixed")
        _require(all(op.tool_id in {t.tool_id for t in self.tools} for op in self.operations), "Unknown operation tool")

    @property
    def provisioned(self):
        return (self.image_digest is not None and self.toolchain_version is not None
                and all(f.source_digest is not None for f in self.fixtures)
                and all(t.version is not None for t in self.tools)
                and all(op.adapter_digest is not None for op in self.operations))

    def to_dict(self):
        return {"schema_version": self.schema_version, "pack_id": self.pack_id,
                "pack_version": self.pack_version, "language": self.language,
                "fixtures": [f.to_dict() for f in self.fixtures],
                "tools": [t.to_dict() for t in self.tools],
                "operations": [op.to_dict() for op in self.operations],
                "resources": self.resources.to_dict(), "image_digest": self.image_digest,
                "toolchain_version": self.toolchain_version,
                "read_roots": list(self.read_roots), "write_roots": list(self.write_roots)}

    @property
    def digest(self):
        return hashlib.sha256(canonical(self.to_dict())).hexdigest()


@dataclass(frozen=True)
class OperationRequest:
    pack_id: str
    operation_id: str
    fixture_id: str
    parameters: tuple[tuple[str, str | int], ...]
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self):
        _require(self.schema_version == SCHEMA_VERSION, "Unsupported request schema")
        for value in (self.pack_id, self.operation_id, self.fixture_id):
            _token(value)
        _require(type(self.parameters) is tuple and len(self.parameters) <= 16, "Invalid parameters")
        names = []
        for pair in self.parameters:
            _require(type(pair) is tuple and len(pair) == 2, "Invalid parameter pair")
            name, value = pair
            _token(name)
            if type(value) is str:
                _token(value)
            else:
                _integer(value, 0, 2147483647)
            names.append(name)
        _require(len(set(names)) == len(names), "Duplicate parameter ID")
        object.__setattr__(self, "parameters", tuple(sorted(self.parameters)))

    @classmethod
    def parse(cls, value):
        _object(value, "schema_version pack_id operation_id fixture_id parameters")
        _require(type(value["parameters"]) is dict, "Parameters must be an object")
        return cls(value["pack_id"], value["operation_id"], value["fixture_id"],
                   tuple(value["parameters"].items()), value["schema_version"])

    def to_dict(self):
        return {"schema_version": self.schema_version, "pack_id": self.pack_id,
                "operation_id": self.operation_id, "fixture_id": self.fixture_id,
                "parameters": dict(self.parameters)}


@dataclass(frozen=True)
class ExecutionAcceptance:
    """Trusted controller assertion, not an authorization token from a model.

    Controller must authenticate retained evidence and compare runtime/policy
    identities itself. Digest equality is binding, not evidence authentication.
    """
    pack_digest: str
    image_digest: str
    runtime_id: str
    policy_digest: str
    canary_evidence_digest: str

    def __post_init__(self):
        for value in (self.pack_digest, self.policy_digest, self.canary_evidence_digest):
            _digest(value)
        _digest(self.image_digest, image=True)
        _token(self.runtime_id)


@dataclass(frozen=True)
class PackRegistry:
    packs: tuple[PackManifest, ...]
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self):
        _require(self.schema_version == SCHEMA_VERSION, "Unsupported registry schema")
        _items(self.packs, PackManifest, "pack_id")
        for attr, key in (("operations", "operation_id"), ("fixtures", "fixture_id")):
            ids = [getattr(item, key) for pack in self.packs for item in getattr(pack, attr)]
            _require(len(set(ids)) == len(ids), "Duplicate cross-pack catalogue ID")

    def get(self, pack_id):
        _token(pack_id)
        for pack in self.packs:
            if pack.pack_id == pack_id:
                return pack
        raise PackError("Unknown language pack")

    def validate_operation(self, value):
        request = value if type(value) is OperationRequest else OperationRequest.parse(value)
        pack = self.get(request.pack_id)
        _require(request.fixture_id in {f.fixture_id for f in pack.fixtures}, "Unknown fixture")
        operation = next((op for op in pack.operations if op.operation_id == request.operation_id), None)
        _require(operation is not None, "Unknown reviewed operation")
        parameters = dict(request.parameters)
        _require(set(parameters) == {p.name for p in operation.parameters}, "Unexpected or missing parameters")
        for spec in operation.parameters:
            spec.validate(parameters[spec.name])
        return request

    def require_execution(self, value, acceptance=None):
        request = self.validate_operation(value)
        pack = self.get(request.pack_id)
        _require(pack.provisioned, "Execution blocked: pack is declared/unprovisioned")
        operation = next(op for op in pack.operations if op.operation_id == request.operation_id)
        tool = next(t for t in pack.tools if t.tool_id == operation.tool_id)
        _require(tool.maturity in (ToolMaturity.CONTAINMENT_TESTED, ToolMaturity.CONTROL_VALIDATED,
                                   ToolMaturity.EVALUATION_APPROVED), "Execution blocked: containment unaccepted")
        _require(type(acceptance) is ExecutionAcceptance, "Execution blocked: trusted acceptance required")
        _require(acceptance.pack_digest == pack.digest and acceptance.image_digest == pack.image_digest,
                 "Execution blocked: stale or mismatched acceptance")
        return pack


@dataclass(frozen=True)
class DiagnosticRef:
    artifact_id: str
    sha256: str
    bytes: int

    def __post_init__(self):
        _token(self.artifact_id)
        _digest(self.sha256)
        _integer(self.bytes, 0, 2000000)

    def to_dict(self):
        return dict(vars(self))


@dataclass(frozen=True)
class ToolResult:
    """Structural observations only; completion/exit code does not confirm a flaw.

    Parser, manifest binding, retained artifact verification and independent
    control grading are separate responsibilities of the future runner.
    """
    request: OperationRequest
    image_digest: str
    fixture_digest: str
    tool_id: str
    tool_version: str
    worker_id: str
    reset_id: str
    status: str
    exit_code: int | None
    timed_out: bool
    truncated: bool
    diagnostics: tuple[DiagnosticRef, ...] = ()
    signals: tuple[str, ...] = ()
    wall_millis: int | None = None
    peak_memory_bytes: int | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self):
        _require(self.schema_version == SCHEMA_VERSION, "Unsupported result schema")
        _require(type(self.request) is OperationRequest, "Invalid result request")
        _digest(self.image_digest, image=True)
        _digest(self.fixture_digest)
        for value in (self.tool_id, self.worker_id, self.reset_id):
            _token(value)
        _version(self.tool_version)
        _require(type(self.status) is str and self.status in ("completed", "tool-error", "timeout", "cancelled"), "Invalid result status")
        if self.exit_code is not None:
            _integer(self.exit_code, -2147483648, 2147483647)
        _require(type(self.timed_out) is bool and type(self.truncated) is bool, "Invalid result flags")
        _require(self.timed_out == (self.status == "timeout"), "Inconsistent timeout status")
        if self.status in ("completed", "tool-error"):
            _require(self.exit_code is not None, "Finished tool requires exit status")
        _items(self.diagnostics, DiagnosticRef, "artifact_id", empty=True)
        _require(sum(d.bytes for d in self.diagnostics) <= 8000000, "Diagnostic total exceeds ceiling")
        _require(type(self.signals) is tuple and len(self.signals) <= 64, "Invalid signals")
        for signal in self.signals:
            _token(signal)
        _require(len(set(self.signals)) == len(self.signals), "Duplicate signal")
        if self.wall_millis is not None:
            _integer(self.wall_millis, 0, 86400000)
        if self.peak_memory_bytes is not None:
            _integer(self.peak_memory_bytes, 0, 1099511627776)

    @classmethod
    def parse(cls, value):
        fields = "schema_version request image_digest fixture_digest tool_id tool_version worker_id reset_id status exit_code timed_out truncated diagnostics signals wall_millis peak_memory_bytes"
        _object(value, fields)
        _require(type(value["diagnostics"]) is list and len(value["diagnostics"]) <= 64, "Invalid diagnostics")
        diagnostics = []
        for item in value["diagnostics"]:
            _object(item, "artifact_id sha256 bytes")
            diagnostics.append(DiagnosticRef(**item))
        _require(type(value["signals"]) is list and len(value["signals"]) <= 64, "Invalid signals")
        return cls(**{**value, "request": OperationRequest.parse(value["request"]),
                      "diagnostics": tuple(diagnostics), "signals": tuple(value["signals"])})

    def to_dict(self):
        return {**vars(self), "request": self.request.to_dict(),
                "diagnostics": [d.to_dict() for d in self.diagnostics], "signals": list(self.signals)}


_VARIANT = ParameterSpec("variant", "enum", ("alpha", "beta", "gamma", "delta"))
_SEED = ParameterSpec("seed", "integer", minimum=0, maximum=65535)
_CASES = ParameterSpec("cases", "integer", minimum=1, maximum=100)


def _declared_pack(pack_id, tools):
    # IDs reserve a reviewed operation surface, not working adapters or fixtures.
    return PackManifest(
        pack_id=pack_id, pack_version="0.1.0", language=pack_id,
        fixtures=(FixtureSpec(f"{pack_id}-synthetic-v1"),),
        tools=tuple(ToolSpec(tool) for tool, _ in tools),
        operations=tuple(OperationSpec(f"{pack_id}-{tool}", tool,
                                       (_VARIANT, _SEED, _CASES) if bounded else (_VARIANT,),
                                       f"{pack_id}-controls-v1") for tool, bounded in tools),
    )


REGISTRY = PackRegistry((
    _declared_pack("python", (("ast", False), ("invariants", False), ("ruff", False), ("bandit", False),
                              ("pytest", False), ("hypothesis", True), ("coverage", False))),
    _declared_pack("typescript", (("tsc", False), ("eslint", False),
                                  ("node-test", False), ("fast-check", True))),
    _declared_pack("c", (("gcc", False), ("clang", False), ("clang-tidy", False), ("asan", True), ("ubsan", True))),
    _declared_pack("rust", (("cargo-check", False), ("cargo-test", False),
                            ("clippy", False), ("proptest", True))),
))
