"""Source/recipe/parser checks only. Never compile or execute C/Rust on host."""
import json
from pathlib import Path
import re

import pytest

from labproof.adapters.observations import (
    ALICE, BOB, ObservationError, classify_cases, parse_observation,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "src" / "labproof" / "fixtures" / "packs"
VARIANTS = ("alpha", "beta", "gamma", "delta")
LANGUAGES = (("c", "c-gcc", "gcc", "c"), ("rust", "rust-cargo-test", "cargo", "rs"))


def authored_cases(variant):
    """Synthetic parser input, NOT a claimed executed tool observation."""
    responses = [
        {"status": 200, "body": BOB} if variant == "alpha" else {"status": 403, "body": {"error": "forbidden"}},
        {"status": 200, "body": BOB}, {"status": 200, "body": ALICE},
        {"status": 401, "body": {"error": "unauthorized"}},
        {"status": 404, "body": {"error": "not_found"}},
    ]
    if variant == "delta":
        responses = [{"status": 503, "body": {"error": "unavailable"}} if i != 3 else value
                     for i, value in enumerate(responses)]
    return [{"case_id": f"case-{i + 1:02}", "response": response} for i, response in enumerate(responses)]


def authored_output(operation, tool, variant):
    return {"schema_version": "worker-observation-1", "operation_id": operation,
            "variant": variant, "tool": tool, "tool_version": "1.2.3",
            "status": "completed", "exit_code": 0, "timed_out": False,
            "truncated": False, "observations": authored_cases(variant)}


@pytest.mark.parametrize("language,operation,tool,extension", LANGUAGES)
@pytest.mark.parametrize("variant", VARIANTS)
def test_compiled_language_parser_contract(language, operation, tool, extension, variant):
    raw = json.dumps(authored_output(operation, tool, variant)).encode()
    parsed = parse_observation(raw, operation, variant)
    assert parsed["tool"] == tool
    assert len(parsed["cases"]) == 5
    assert classify_cases(parsed["cases"]) == ("exposed" if variant == "alpha" else "unknown" if variant == "delta" else "safe")


@pytest.mark.parametrize("language,operation,tool,extension", LANGUAGES)
@pytest.mark.parametrize("update", [{"tool": "clang"}, {"tool_version": "gcc (GCC) 14.2.0"},
                                     {"exit_code": True}, {"truncated": True}, {"timed_out": True},
                                     {"variant": "defective"}, {"status": "tool-error"},
                                     {"observations": []}])
def test_compiled_language_parser_rejects_invalid_outputs(language, operation, tool, extension, update):
    payload = authored_output(operation, tool, "alpha")
    payload.update(update)
    with pytest.raises(ObservationError):
        parse_observation(json.dumps(payload).encode(), operation, "alpha")


@pytest.mark.parametrize("language,operation,tool,extension", LANGUAGES)
def test_oracle_and_inputs_match_reviewed_python_contract(language, operation, tool, extension):
    reference = json.loads((FIXTURES / "python" / "oracle.host-only.json").read_text())
    oracle = json.loads((FIXTURES / language / "oracle.host-only.json").read_text())
    assert oracle["fixture_id"] == f"{language}-synthetic-v1"
    for field in ("variant_roles", "case_roles", "expected_statuses"):
        assert oracle[field] == reference[field]
    for variant in VARIANTS:
        assert (FIXTURES / language / variant / "inputs.json").read_bytes() == (FIXTURES / "python" / variant / "inputs.json").read_bytes()
        assert oracle["expected_statuses"][variant] == [row["response"]["status"] for row in authored_cases(variant)]


@pytest.mark.parametrize("language,operation,tool,extension", LANGUAGES)
def test_recipes_require_digest_and_exclude_oracle(language, operation, tool, extension):
    docker = (ROOT / "sandboxes" / language / "Dockerfile").read_text()
    assert "ARG BASE_IMAGE\nFROM ${BASE_IMAGE}" in docker
    assert "@sha256:[a-f0-9]{64}" in docker
    assert "USER 65532:65532" in docker
    assert 'ENTRYPOINT ["/worker/observe"]' in docker
    copies = [line for line in docker.splitlines() if line.startswith("COPY ")]
    assert len(copies) == (5 if language == "c" else 6)
    assert not any("oracle" in line or "provisioning" in line or "COPY . " in line for line in copies)
    assert not any(word in docker for word in ("apt-get", "curl ", "wget ", "cargo install", "--privileged"))
    for variant in VARIANTS:
        assert any(f"/{variant}/authz.{extension}" in line for line in copies)


@pytest.mark.parametrize("language,operation,tool,extension", LANGUAGES)
def test_sources_contain_exact_fixed_cases_without_evaluation_labels(language, operation, tool, extension):
    worker = (ROOT / "sandboxes" / language / ("worker.c" if language == "c" else "src/main.rs")).read_text()
    inputs = json.loads((FIXTURES / language / "alpha" / "inputs.json").read_text())
    for row in inputs:
        pattern = r'"' + row["id"] + r'",\s*"' + row["actor"] + r'",\s*"' + row["record_id"] + '"'
        assert re.search(pattern, worker)
    for source in [worker] + [(FIXTURES / language / v / f"authz.{extension}").read_text() for v in VARIANTS]:
        assert not any(label in source for label in ("defective", "corrected", "ambiguous", "oracle.host-only"))
    assert f'"{operation}"' in worker
    if language == "c":
        assert "__GNUC__, __GNUC_MINOR__, __GNUC_PATCHLEVEL__" in worker
        assert "system(" not in worker and "popen(" not in worker
    else:
        assert '.args(["test", "--offline", "--locked"' in worker
        assert '"/output/cargo-target"' in worker
        assert ".env_clear()" in worker
        assert 'Command::new("/usr/local/cargo/bin/cargo")' in worker
        assert '"--exact", "tests::response_shapes"' in worker


@pytest.mark.parametrize("language,operation,tool,extension", LANGUAGES)
def test_source_response_literals_and_guard_shapes(language, operation, tool, extension):
    sources = {v: (FIXTURES / language / v / f"authz.{extension}").read_text() for v in VARIANTS}
    assert sources["beta"] == sources["gamma"]
    guard = 'strcmp(owner, actor) != 0' if language == "c" else 'owner != actor'
    assert guard not in sources["alpha"]
    assert guard in sources["beta"]
    for variant, source in sources.items():
        # Decode authored body string literals without compiling/evaluating source.
        if language == "c":
            literals = re.findall(r'"(\{(?:\\.|[^"\\])*\})"', source)
            bodies = [json.loads(json.loads('"' + literal + '"')) for literal in literals]
        else:
            bodies = [json.loads(literal) for literal in re.findall(r'r#"(\{[^\n]+?\})"#', source)]
        assert {"error": "unauthorized"} in bodies
        if variant == "delta":
            assert {"error": "unavailable"} in bodies
            assert BOB not in bodies and ALICE not in bodies
        else:
            assert BOB in bodies and ALICE in bodies
            assert {"error": "not_found"} in bodies
            assert ({"error": "forbidden"} in bodies) == (variant in ("beta", "gamma"))


def test_rust_lock_is_dependency_free():
    import tomllib
    manifest = tomllib.loads((ROOT / "sandboxes/rust/Cargo.toml").read_text())
    lock = tomllib.loads((ROOT / "sandboxes/rust/Cargo.lock").read_text())
    assert manifest["dependencies"] == {}
    assert lock["package"] == [{"name": "labproof-worker", "version": "0.1.0"}]
    assert "build" not in manifest["package"]
