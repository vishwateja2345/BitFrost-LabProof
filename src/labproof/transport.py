"""Frozen fixture replay; no sockets, subprocesses, URLs, or environment proxies."""
from dataclasses import dataclass, asdict
from importlib.resources import files

from .contracts import parse_json, require, canonical
from .policy import Action, Budget, VARIANTS


@dataclass(frozen=True)
class Response:
    status: int
    content_type: str
    body: str

    @classmethod
    def parse(cls, value):
        require(isinstance(value, dict) and set(value) == {"status", "content_type", "body"}, "Malformed response")
        require(type(value["status"]) is int and 100 <= value["status"] <= 599, "Invalid HTTP-shaped status")
        require(isinstance(value["content_type"], str) and value["content_type"] in {"application/json", "text/plain", "text/html"}, "Unsupported content type")
        require(isinstance(value["body"], str) and len(value["body"].encode("utf-8")) <= 4096, "Invalid response body")
        require(not 300 <= value["status"] <= 399, "Redirects are forbidden")
        return cls(**value)

    def to_dict(self):
        return asdict(self)


class ReplayTransport:
    def __init__(self):
        self.fixture_bytes = files("labproof").joinpath("fixtures/replay.json").read_bytes()
        self._fixtures = parse_json(self.fixture_bytes)["responses"]

    def reset(self):
        """Reload the same canned snapshot, NOT a live target reset."""
        self._fixtures = parse_json(self.fixture_bytes)["responses"]

    def execute(self, action: Action, *, variant: str, budget: Budget) -> Response:
        action.validate()
        require(variant in VARIANTS, "Unknown replay variant")
        budget.reserve()
        raw = self._fixtures[variant][action.check_id.value][action.control]
        budget.consume(len(canonical(raw)))
        return Response.parse(raw)


def doctor():
    # No Docker subprocess: merely finding the client would not establish isolation.
    return {
        "project_id": "labproof", "replay": "available", "assessment": "blocked",
        "docker_daemon": "not_probed", "containment": "not_verified",
        "live_model": "not_implemented", "network_operations": 0,
        "reason": "This non-probing check cannot accept a runtime. Use explicit local mode with trusted provisioning; acceptance runs before fixtures.",
        "local_mode": {"implemented": True, "readiness": "not_probed",
                       "entrypoint": "assess --mode local --pack <pack> --output <new-directory>",
                       "requires": ["trusted_installed_provisioning", "preloaded_reviewed_image",
                                    "per_session_containment_acceptance"]},
    }
