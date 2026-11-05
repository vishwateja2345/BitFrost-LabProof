"""Finite generated-input/replay contract for the unaccepted Hypothesis pilot.

No registration in legacy fixed plans. Requests select synthetic values only;
image/argv authority remains trusted host code and requires live acceptance.
"""
from hashlib import sha256
from math import ceil

from .adapters.hypothesis_codec import parse_codec, VERSION, MAX_INVOCATIONS, _hex
from .contracts import canonical, require, SHA_RE
from .local_profiles import VARIANTS
from .sandbox.policy import LaunchPlan, SandboxLimits

REQUEST_VERSION = "codec-request-1"
PROFILE_ID = "python-hypothesis-codec-1"
LIMITS = SandboxLimits(output_bytes=60000)
REQUEST_FIELDS = {"schema_version", "profile_id", "variant", "property", "seed", "cases", "replay"}
REPLAY_FIELDS = {"source_request_sha256", "source_raw_sha256", "example_id", "input_hex", "input_sha256"}


def digest(value):
    return sha256(canonical(value)).hexdigest()


def _digest(value):
    require(type(value) is str and SHA_RE.fullmatch(value), "Invalid codec digest")


def validate_request(value):
    require(type(value) is dict and set(value) == REQUEST_FIELDS, "Invalid codec request fields")
    require(value["schema_version"] == REQUEST_VERSION and value["profile_id"] == PROFILE_ID,
            "Unsupported codec request/profile")
    require(type(value["variant"]) is str and value["variant"] in VARIANTS, "Invalid codec variant")
    require(type(value["property"]) is str and value["property"] in ("roundtrip", "boundary", "malformed"),
            "Invalid codec property")
    for name, low, high in (("seed", 0, 65535), ("cases", 1, 16)):
        require(type(value[name]) is int and low <= value[name] <= high, "Invalid codec " + name)
    replay = value["replay"]
    if replay is not None:
        require(type(replay) is dict and set(replay) == REPLAY_FIELDS, "Invalid concrete replay fields")
        require(value["property"] == "malformed", "Concrete replay supports malformed frames only")
        for name in ("source_request_sha256", "source_raw_sha256", "input_sha256"):
            _digest(replay[name])
        require(type(replay["example_id"]) is int and 5 <= replay["example_id"] <= MAX_INVOCATIONS + 1,
                "Invalid counterexample reference")
        raw = _hex(replay["input_hex"])
        require(not raw or raw[0] != len(raw) - 1, "Replay input must be malformed")
        require(sha256(raw).hexdigest() == replay["input_sha256"], "Replay input digest mismatch")
    # Return detached data: callers cannot mutate a previously checked reference.
    from .contracts import parse_json
    return parse_json(canonical(value))


def generation_request(variant, property_id="malformed", seed=0, cases=16):
    return validate_request({"schema_version": REQUEST_VERSION, "profile_id": PROFILE_ID,
                             "variant": variant, "property": property_id,
                             "seed": seed, "cases": cases, "replay": None})


def parse_request_output(request, raw):
    request = validate_request(request)
    replay = request["replay"]
    return parse_codec(raw, variant=request["variant"], property_id=request["property"],
                       seed=request["seed"], cases=request["cases"],
                       replay_hex=None if replay is None else replay["input_hex"])


def make_replay(source_request, source_raw, example_id, *, variant=None):
    source_request = validate_request(source_request)
    require(source_request["replay"] is None and source_request["property"] == "malformed",
            "Replay must originate from malformed generation, not another replay")
    require(type(example_id) is int, "Invalid counterexample reference")
    observation = parse_request_output(source_request, source_raw)
    require(observation["controls_ok"] and observation["observation"] == "counterexample",
            "Replay source lacks a controlled counterexample")
    selected = [row for row in observation["counterexamples"]
                if row["example_id"] == example_id and row["kind"] == "generated"]
    require(len(selected) == 1, "Replay source example is not a generated counterexample")
    raw = bytes.fromhex(selected[0]["input_hex"])
    return validate_request({**source_request, "variant": source_request["variant"] if variant is None else variant,
                             "replay": {"source_request_sha256": digest(source_request),
                                        "source_raw_sha256": sha256(source_raw).hexdigest(),
                                        "example_id": example_id, "input_hex": raw.hex(),
                                        "input_sha256": sha256(raw).hexdigest()}})


def validate_replay_source(request, source_request, source_raw):
    request = validate_request(request)
    require(request["replay"] is not None, "Expected replay request")
    expected = make_replay(source_request, source_raw, request["replay"]["example_id"], variant=request["variant"])
    require(canonical(request) == canonical(expected), "Replay source/configuration binding mismatch")
    return request


def launch_plan(request, image_id):
    """Host-only recipe builder, not acceptance or imported image authority."""
    request = validate_request(request)
    replay = request["replay"]
    argv = ("/usr/local/bin/python", "-I", "-B", "/worker/hypothesis_codec.py",
            request["variant"], request["property"], str(request["seed"]), str(request["cases"]),
            "none" if replay is None else replay["input_hex"])
    return LaunchPlan("codec-" + digest(request), image_id, argv)


def reservation(request):
    validate_request(request)
    return {"actions": 1, "target_invocations": MAX_INVOCATIONS,
            "wall_seconds": ceil(LIMITS.wall_seconds + LIMITS.cleanup_seconds),
            "output_bytes": LIMITS.output_bytes}
