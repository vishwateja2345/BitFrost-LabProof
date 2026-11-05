"""Single-use, mocked native-Messages proposal adapter; never executes operations.

Live SDK construction is deliberately blocked. See INFERENCE.md for the SDK
ambient-header isolation blocker. The injected client is a trusted test seam,
not a safe way to enable a live client.
"""
from copy import deepcopy
from dataclasses import dataclass
import re
from threading import Lock
from typing import TYPE_CHECKING

from .contracts import canonical
from .packs import OperationRequest, PackError, REGISTRY

if TYPE_CHECKING:  # No optional SDK import (or credential discovery) at runtime.
    from anthropic import Anthropic

BASE_URL = "http://localhost:8080/anthropic"
MAX_TOKENS = 512
TIMEOUT_SECONDS = 10.0
MAX_ALLOWED_REQUESTS = 16
MAX_METADATA_BYTES = 16_384
TOOL_NAME = "propose_operation"
LIVE_BLOCKER = (
    "Live inference blocked: the reviewed SDK constructor merges "
    "ANTHROPIC_CUSTOM_HEADERS even with explicit default_headers={}; "
    "ambient header/credential isolation is unverified."
)
SYSTEM = (
    "Select at most one supplied synthetic operation by calling propose_operation. "
    "Return its exact request unchanged. These are reviewed catalogue metadata, "
    "not instructions to execute. This is only a proposal: it cannot run tools, "
    "authorize execution, establish a finding, or promote evidence. "
    "If none is suitable, abstain."
)


class InferenceBlocked(RuntimeError):
    """An opt-in, lifecycle, or live isolation gate prevented inference."""


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None


@dataclass(frozen=True)
class Decision:
    status: str
    proposal: OperationRequest | None = None
    usage: Usage = Usage()
    mode: str = "mocked"
    attempts: int = 1


def _model(value):
    # Native Anthropic only: no provider-routing prefix or URL-shaped model ID.
    if type(value) is not str or not re.fullmatch(r"claude-[a-z0-9-]{1,90}", value):
        raise ValueError("An explicit native Claude model ID is required")
    return value


def _usage(response):
    raw = getattr(response, "usage", None)
    values = {}
    for name in Usage.__dataclass_fields__:
        value = getattr(raw, name, None)
        values[name] = value if type(value) is int and value >= 0 else None
    return Usage(**values)


class DecisionAdapter:
    """Exactly one SDK-shaped request, with no dispatch or continuation method.

    Only narrow registry-validated requests are exposed to the client. The
    reviewed_synthetic flag is caller attestation, not an automated data review.
    """

    def __init__(self, *, injected_client: "Anthropic", model: str,
                 allowed_requests, mock_opt_in: bool = False,
                 reviewed_synthetic: bool = False):
        if mock_opt_in is not True:
            raise InferenceBlocked("Explicit mocked inference opt-in required")
        if reviewed_synthetic is not True:
            raise InferenceBlocked("Caller must review synthetic metadata before inference")
        self._model = _model(model)
        if type(allowed_requests) not in (list, tuple) or not 1 <= len(allowed_requests) <= MAX_ALLOWED_REQUESTS:
            raise ValueError("Supply between 1 and 16 exact allowed requests")
        self._allowed = tuple(REGISTRY.validate_operation(r) for r in allowed_requests)
        payload = [r.to_dict() for r in self._allowed]
        if len({canonical(r) for r in payload}) != len(payload):
            raise ValueError("Duplicate allowed request")
        metadata = canonical({"synthetic": True, "allowed_requests": payload})
        if len(metadata) > MAX_METADATA_BYTES:
            raise ValueError("Synthetic metadata exceeds byte ceiling")
        self._client = injected_client
        self._messages = [{"role": "user", "content": metadata.decode("ascii")}]
        self._tools = [{
            "name": TOOL_NAME,
            "description": "Propose one exact allowed synthetic request; never execute it.",
            "input_schema": {
                "type": "object",
                "properties": {"request": {"type": "object", "enum": payload}},
                "required": ["request"],
                "additionalProperties": False,
            },
        }]
        self._attempts = 0
        self._lock = Lock()

    @classmethod
    def native(cls, *, credential: str, model: str, live_opt_in: bool = False):
        """Reserved live construction gate; always fails before any SDK import.

        Credentials must be supplied by the caller, never discovered here. No
        dependency is needed until a reviewed construction path is enabled.
        """
        if live_opt_in is not True:
            raise InferenceBlocked("Explicit live inference opt-in required")
        _model(model)
        if type(credential) is not str or not credential or not credential.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in credential):
            raise ValueError("An explicit nonempty credential is required")
        raise InferenceBlocked(LIVE_BLOCKER)

    @property
    def attempts(self):
        return self._attempts

    @property
    def messages(self):
        """Detached transcript preserving all response content blocks unchanged."""
        return deepcopy(self._messages)

    def propose(self) -> Decision:
        with self._lock:
            if self._attempts:
                raise InferenceBlocked("Single proposal attempt already consumed")
            # Consume the attempt even if client configuration or request fails.
            self._attempts += 1
        try:
            response = self._client.with_options(
                max_retries=0, timeout=TIMEOUT_SECONDS,
            ).messages.create(
                model=self._model, max_tokens=MAX_TOKENS, stream=False,
                system=SYSTEM, messages=deepcopy(self._messages),
                tools=deepcopy(self._tools),
                tool_choice={"type": "auto", "disable_parallel_tool_use": True},
            )
        except Exception:
            # All failures terminate identically: no retry/reroute and no
            # exception body (which may contain a credential) in the result.
            return Decision("request_error")

        usage = _usage(response)
        stop = getattr(response, "stop_reason", None)
        content = getattr(response, "content", None)
        # Preserve whole SDK content, including signed/redacted thinking. Never
        # synthesize tool results or edit this prefix for another call.
        if isinstance(content, list):
            self._messages.append({"role": "assistant", "content": deepcopy(content)})
        if stop in ("refusal", "max_tokens"):
            return Decision(stop, usage=usage)
        if not isinstance(content, list):
            return Decision("invalid_response", usage=usage)
        if any(getattr(b, "type", None) not in ("text", "thinking", "redacted_thinking", "tool_use") for b in content):
            return Decision("invalid_response", usage=usage)
        calls = [b for b in content if b.type == "tool_use"]
        if stop == "end_turn" and not calls:
            return Decision("abstained", usage=usage)
        if stop != "tool_use" or len(calls) != 1:
            return Decision("invalid_response", usage=usage)
        call = calls[0]
        value = getattr(call, "input", None)
        if getattr(call, "name", None) != TOOL_NAME or type(value) is not dict or set(value) != {"request"} or type(value["request"]) is not dict:
            return Decision("invalid_proposal", usage=usage)
        try:
            request = REGISTRY.validate_operation(value["request"])
        except PackError:
            return Decision("invalid_proposal", usage=usage)
        if request not in self._allowed:
            return Decision("invalid_proposal", usage=usage)
        return Decision("proposed", proposal=request, usage=usage)
