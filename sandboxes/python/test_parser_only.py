"""Host-safe parser/source checks only. Never import fixture or worker modules."""
import ast
import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
SOURCE = HERE / "worker.py"


def parser_namespace():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    constants = {"OPERATIONS", "VARIANTS", "MAX_SOURCE_BYTES", "MAX_INPUT_BYTES"}
    functions = {"parse_args", "parse_inputs", "inspect_ast"}
    selected = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and t.id in constants for t in node.targets):
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in functions:
            selected.append(node)
    # Compile only the reviewed pure functions: no imports, observe/main, or fixture code.
    namespace = {"ast": ast, "json": json}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


@pytest.mark.parametrize("operation", ["python-ast", "python-invariants"])
@pytest.mark.parametrize("variant", ["alpha", "beta", "gamma", "delta"])
def test_fixed_enums(operation, variant):
    assert parser_namespace()["parse_args"]([operation, variant]) == (operation, variant)


@pytest.mark.parametrize("args", [[], ["python-ast"], ["python-ast", "alpha", "--exec"],
    ["python-pytest", "alpha"], ["python-hypothesis", "alpha"], ["python-ast", "defective"],
    ["python-ast", "../alpha"], ["python-ast", "alpha;sh"], ["python-ast", 1], {"operation": "python-ast"}])
def test_rejects_unreviewed_requests(args):
    with pytest.raises(ValueError):
        parser_namespace()["parse_args"](args)


def test_inputs_have_no_oracle_fields():
    parse = parser_namespace()["parse_inputs"]
    row = {"id": "case-01", "actor": "alice", "record_id": "record-bob"}
    assert parse(json.dumps([row]).encode()) == [row]
    for value in [[{**row, "expected": 403}], [row, row], [{**row, "actor": "admin"}],
                  [{**row, "record_id": "/etc/passwd"}], [], [row] * 9]:
        with pytest.raises(ValueError):
            parse(json.dumps(value).encode())
    with pytest.raises(ValueError):
        parse(b'[{"id":"case-01","id":"case-02","actor":"alice","record_id":"record-bob"}]')
    with pytest.raises(ValueError):
        parse(b" " * 4097)


def test_ast_inspection_does_not_execute_source():
    records = parser_namespace()["inspect_ast"](b'def example():\n    raise RuntimeError("must not execute")\n')
    assert records == [{"node": "FunctionDef", "line": 1}]


def test_python_fixture_sources_are_syntax_only():
    for path in (ROOT / "src/labproof/fixtures/packs/python").glob("*/authz.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


@pytest.mark.parametrize("sandbox,language", [("python", "python"), ("node", "typescript")])
def test_exact_copy_allowlist_excludes_host_oracles(sandbox, language):
    text = (ROOT / "sandboxes" / sandbox / "Dockerfile").read_text(encoding="utf-8")
    sources = [line.split()[1] for line in text.splitlines() if line.startswith("COPY ")]
    workers = [f"sandboxes/{sandbox}/worker." + ("py" if sandbox == "python" else "mjs")]
    if sandbox == "node":
        workers.append("sandboxes/node/observe.test.mjs")
    assert sources == workers + [f"src/labproof/fixtures/packs/{language}/{slot}/" for slot in ("alpha", "beta", "gamma", "delta")]
    assert "ARG BASE_IMAGE\nFROM ${BASE_IMAGE}" in text
    assert "USER 65532:65532" in text
    for path in sources:
        target = ROOT / path
        if target.is_dir():
            assert {p.name for p in target.iterdir()} == {"inputs.json", "authz.py" if language == "python" else "authz.ts"}
            assert b"expected" not in (target / "inputs.json").read_bytes()
    metadata = json.loads((ROOT / "sandboxes" / sandbox / "provisioning.host-only.json").read_text())
    assert metadata["status"] == "provisioning-blocked"
    assert metadata["base_image"] is None and metadata["image_digest"] is None
