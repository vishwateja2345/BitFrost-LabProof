"""UNPROVISIONED container-only Hypothesis codec pilot, never import fixtures on host.

Fixed prospective argv: variant property seed cases replay_hex-or-none.
No commands/paths/images from inputs. No database, reuse, shrink, target or explain
phase. Every codec call (including Hypothesis final rechecks) passes invoke().
This source is not registered as an executable profile or accepted capability.
"""
import importlib.util
import json
from pathlib import Path
import sys

HYPOTHESIS_VERSION = "6.142.4"
MAX_INVOCATIONS = 128
MAX_OUTPUT = 60000


class InvocationBudget(BaseException):
    pass


class PropertyMismatch(AssertionError):
    pass


def args_checked(args):
    if len(args) != 5:
        raise ValueError("invalid arguments")
    variant, prop, seed, cases, replay = args
    if variant not in ("alpha", "beta", "gamma", "delta") or prop not in ("roundtrip", "boundary", "malformed"):
        raise ValueError("invalid fixed enum")
    if not seed.isascii() or not seed.isdecimal() or not cases.isascii() or not cases.isdecimal():
        raise ValueError("invalid integer")
    seed, cases = int(seed), int(cases)
    if not 0 <= seed <= 65535 or not 1 <= cases <= 16:
        raise ValueError("invalid bound")
    if replay != "none":
        if len(replay) > 514 or len(replay) % 2 or any(c not in "0123456789abcdef" for c in replay):
            raise ValueError("invalid concrete input")
        if prop != "malformed":
            raise ValueError("only malformed frame replay is reviewed")
    return variant, prop, seed, cases, replay


def main(args=None):
    try:
        variant, prop, rng_seed, cases, replay = args_checked(sys.argv[1:] if args is None else args)
    except ValueError:
        return 2
    # Runtime-only import; no host test imports or calls this function.
    import hypothesis
    from hypothesis import Phase, given, seed, settings, strategies as st
    from hypothesis.reporting import with_reporter
    if hypothesis.__version__ != HYPOTHESIS_VERSION:
        return 2
    source = Path("/fixture") / variant / "codec.py"
    if source.stat().st_size > 16384:
        return 2
    spec = importlib.util.spec_from_file_location("synthetic_codec", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    trace, examples = [], []
    exhausted = False

    def invoke(method, raw, example_id):
        nonlocal exhausted
        if len(trace) >= MAX_INVOCATIONS:
            exhausted = True
            raise InvocationBudget()
        row = {"id": len(trace) + 1, "example_id": example_id, "method": method,
               "input_hex": raw.hex(), "output_hex": None, "exception": None}
        # Retain an invocation before entering target code.
        trace.append(row)
        try:
            value = getattr(module, method)(raw)
            if type(value) is not bytes or len(value) > 257:
                row["exception"] = "invalid-result"
            else:
                row["output_hex"] = value.hex()
        except ValueError:
            row["exception"] = "ValueError"
        except Exception:
            row["exception"] = "unexpected"
        return row

    def example(kind, raw):
        row = {"id": len(examples) + 1, "kind": kind, "input_hex": raw.hex(), "outcome": "interrupted"}
        examples.append(row)
        return row

    def roundtrip(raw, kind):
        row = example(kind, raw)
        encoded = invoke("encode", raw, row["id"])
        good = encoded["exception"] is None and encoded["output_hex"] == (bytes([len(raw)]) + raw).hex()
        if good:
            decoded = invoke("decode", bytes.fromhex(encoded["output_hex"]), row["id"])
            good = decoded["exception"] is None and decoded["output_hex"] == raw.hex()
        row["outcome"] = "satisfied" if good else "counterexample"
        if not good:
            raise PropertyMismatch()

    def malformed(raw, kind):
        row = example(kind, raw)
        observed = invoke("decode", raw, row["id"])
        good = observed["exception"] == "ValueError"
        row["outcome"] = "satisfied" if good else "counterexample"
        if not good:
            raise PropertyMismatch()

    result = {"schema_version": "codec-worker-1", "fixture_id": "python-codec-v1",
              "variant": variant, "property": prop, "seed": rng_seed, "cases": cases,
              "replay_hex": None if replay == "none" else replay,
              "tool": "hypothesis", "tool_version": HYPOTHESIS_VERSION,
              "settings": {"database": None, "phases": ["generate"], "deadline": None,
                           "report_multiple_bugs": False, "max_examples": cases},
              "status": "tool-error", "invocation_limit": MAX_INVOCATIONS,
              "invocations": trace, "examples": examples, "rejections": 0, "shrinks": 0}
    try:
        # Same functional controls for every variant/property/fresh replay.
        roundtrip(b"", "control-empty")
        roundtrip(b"x" * 255, "control-boundary")
        row = example("control-oversize", b"x" * 256)
        observed = invoke("encode", b"x" * 256, row["id"])
        row["outcome"] = "satisfied" if observed["exception"] == "ValueError" else "counterexample"
        if row["outcome"] != "satisfied":
            raise PropertyMismatch()
        malformed(b"", "control-empty-frame")

        if replay != "none":
            frame = bytes.fromhex(replay)
            if frame and frame[0] == len(frame) - 1:
                raise ValueError("not malformed")
            malformed(frame, "replay")
        else:
            @seed(rng_seed)
            @settings(database=None, phases=(Phase.generate,), deadline=None,
                      max_examples=cases, report_multiple_bugs=False)
            @given(st.binary(min_size=0, max_size=32) if prop != "boundary" else st.sampled_from((b"", b"x" * 255)))
            def property_test(payload):
                if prop == "malformed":
                    # Construct invalid length directly: no filter/assume/rejections.
                    malformed(bytes([len(payload) + 1]) + payload, "generated")
                else:
                    roundtrip(payload, "generated")

            # Raw evidence is only the bounded JSON trace, never framework prose.
            with with_reporter(lambda _: None):
                property_test()
        result["status"] = "completed"
    except PropertyMismatch:
        result["status"] = "counterexample"
    except InvocationBudget:
        result["status"] = "budget-exhausted"
    except Exception:
        result["status"] = "tool-error"
    if exhausted:
        result["status"] = "budget-exhausted"
    raw = (json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    if len(raw) > MAX_OUTPUT:
        # Never truncate a trace into apparently complete evidence.
        return 2
    sys.stdout.buffer.write(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
