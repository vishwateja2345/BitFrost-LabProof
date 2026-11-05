"""Container-only fixed catalogue worker. Never run fixture imports on the host.

The trusted controller passes two reviewed enum arguments, not a command string.
No oracle, expected security outcome, or provisioning identity is reported here.
"""
import ast
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest

OPERATIONS = ("python-ast", "python-invariants")
VARIANTS = ("alpha", "beta", "gamma", "delta")
MAX_SOURCE_BYTES = 16384
MAX_INPUT_BYTES = 4096


def parse_args(args):
    if (type(args) not in (list, tuple) or len(args) != 2
            or any(type(a) is not str for a in args)
            or args[0] not in OPERATIONS or args[1] not in VARIANTS):
        raise ValueError("Expected one declared operation ID and one opaque variant ID")
    return args[0], args[1]


def read_bounded(path, limit):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Input exceeds fixed bound")
    return raw


def parse_inputs(raw):
    if type(raw) is not bytes or len(raw) > MAX_INPUT_BYTES:
        raise ValueError("Invalid input size")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate input key")
            result[key] = value
        return result
    values = json.loads(raw, object_pairs_hook=unique)
    if type(values) is not list or not 1 <= len(values) <= 8:
        raise ValueError("Invalid input array")
    ids = set()
    for row in values:
        if type(row) is not dict or set(row) != {"id", "actor", "record_id"}:
            raise ValueError("Invalid input fields")
        if any(type(v) is not str for v in row.values()):
            raise ValueError("Invalid input types")
        if row["id"] not in tuple(f"case-{i:02}" for i in range(1, 9)) or row["id"] in ids:
            raise ValueError("Invalid input ID")
        if row["actor"] not in ("alice", "bob", "guest") or row["record_id"] not in ("record-alice", "record-bob", "record-missing"):
            raise ValueError("Unknown synthetic input")
        ids.add(row["id"])
    return values


def inspect_ast(source):
    if type(source) is not bytes or len(source) > MAX_SOURCE_BYTES:
        raise ValueError("Invalid source size")
    tree = ast.parse(source, filename="authz.py")
    # Structural facts only: no label or security conclusion is inferred.
    return [{"node": type(node).__name__, "line": node.lineno}
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.If, ast.Return, ast.Import, ast.ImportFrom))]


def observe(variant):
    root = Path("/fixture") / variant
    inputs = parse_inputs(read_bounded(root / "inputs.json", MAX_INPUT_BYTES))
    read_bounded(root / "authz.py", MAX_SOURCE_BYTES)
    spec = importlib.util.spec_from_file_location("synthetic_authz", root / "authz.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # Container only; never called by parser tests.
    observations = []

    class ResponseShape(unittest.TestCase):
        def runTest(self):
            for row in inputs:
                with self.subTest(case=row["id"]):
                    response = module.read_record(row["actor"], row["record_id"])
                    # Public API-shape checks are NOT the independent security oracle.
                    self.assertIs(type(response), dict)
                    self.assertEqual(set(response), {"status", "body"})
                    self.assertIs(type(response["status"]), int)
                    self.assertTrue(100 <= response["status"] <= 599)
                    self.assertIs(type(response["body"]), dict)
                    self.assertLessEqual(len(response["body"]), 4)
                    self.assertTrue(all(type(k) is str and type(v) is str and len(k) <= 80 and len(v) <= 128
                                        for k, v in response["body"].items()))
                    observations.append({"case_id": row["id"], "response": response})

    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(unittest.TestSuite([ResponseShape()]))
    return observations, result.wasSuccessful()


def main(args=None):
    try:
        operation, variant = parse_args(sys.argv[1:] if args is None else args)
    except ValueError:
        print('{"schema_version":"worker-observation-1","status":"invalid-request"}')
        return 2
    result = {"schema_version": "worker-observation-1", "operation_id": operation,
              "variant": variant, "tool": "ast" if operation == "python-ast" else "unittest",
              "tool_version": sys.version.split()[0], "status": "tool-error", "exit_code": 1,
              "observations": [], "timed_out": False, "truncated": False}
    try:
        if operation == "python-ast":
            result["observations"] = inspect_ast(read_bounded(Path("/fixture") / variant / "authz.py", MAX_SOURCE_BYTES))
            success = True
        else:
            result["observations"], success = observe(variant)
        result.update(status="completed" if success else "tool-error", exit_code=0 if success else 1)
    except Exception:
        # Do not leak arbitrary paths, environment, or exception text.
        result["diagnostic"] = "operation-failed"
    print(json.dumps(result, separators=(",", ":"), allow_nan=False))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
