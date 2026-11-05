"""Offline SDK-shaped mocks only; no model, credentials, sockets, or workers."""
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from labproof.inference import (
    BASE_URL, DecisionAdapter, InferenceBlocked, MAX_TOKENS, TIMEOUT_SECONDS,
)
from labproof.packs import PackError, REGISTRY

MODEL = "claude-opus-5-5"


def request(**changes):
    return {"schema_version": "1.0", "pack_id": "python", "fixture_id": "python-synthetic-v1",
            "operation_id": "python-ast", "parameters": {"variant": "alpha"}, **changes}


def tool(value=None, name="propose_operation"):
    return NS(type="tool_use", id="mock-tool-1", name=name,
              input={"request": request()} if value is None else value)


def response(*, content=None, stop="tool_use", usage=None):
    return NS(content=[tool()] if content is None else content,
              stop_reason=stop, usage=usage)


def adapter(reply=None, **kwargs):
    client = Mock()
    client.with_options.return_value = client
    client.messages.create.return_value = response() if reply is None else reply
    args = dict(injected_client=client, model=MODEL, allowed_requests=[request()],
                mock_opt_in=True, reviewed_synthetic=True)
    result = DecisionAdapter(**{**args, **kwargs})
    return result, client


def test_accepted_request_only_proposes_and_keeps_sdk_content():
    thinking = NS(type="thinking", thinking="", signature="mock-signature")
    redacted = NS(type="redacted_thinking", data="mock-opaque-data")
    reply = response(content=[thinking, redacted, NS(type="text", text="A proposal."), tool()])
    original = deepcopy(reply.content)
    item, client = adapter(reply)
    prefix = item.messages
    decision = item.propose()
    assert decision.status == "proposed"
    assert decision.proposal.to_dict() == request()
    assert decision.mode == "mocked" and decision.attempts == item.attempts == 1
    assert item.messages == prefix + [{"role": "assistant", "content": original}]
    assert reply.content == original
    item.messages[0]["content"] = "caller mutation"
    reply.content.clear()
    assert item.messages == prefix + [{"role": "assistant", "content": original}]
    client.with_options.assert_called_once_with(max_retries=0, timeout=TIMEOUT_SECONDS)
    call = client.messages.create.call_args.kwargs
    assert call["messages"] == prefix
    assert call["model"] == MODEL and call["max_tokens"] == MAX_TOKENS
    assert call["stream"] is False
    assert call["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert len(call["tools"]) == 1
    assert call["tools"][0]["input_schema"]["properties"]["request"]["enum"] == [request()]
    assert "fallbacks" not in call and "betas" not in call
    with pytest.raises(PackError, match="unprovisioned"):
        REGISTRY.require_execution(decision.proposal)
    with pytest.raises(InferenceBlocked, match="consumed"):
        item.propose()
    client.messages.create.assert_called_once()


@pytest.mark.parametrize("bad", [
    {"request": request(), "command": "sh"},
    {"request": request(operation_id="sh")},
    {"request": request(fixture_id="../fixture")},
    {"request": request(fixture_id="http://example.test")},
    {"request": request(parameters={"variant": "alpha", "argv": ["id"]})},
    {"request": request(parameters={"variant": "beta"})},  # Valid but not allowed.
    {"request": request(operation_id="python-pytest")},  # Valid but not allowed.
    {"request": "{\"operation_id\":\"python-ast\"}"},
    {"request": request(parameters={"variant": True})},
    {}, "not-json", [],
])
def test_invalid_input_never_produces_a_request(bad):
    item, client = adapter(response(content=[tool(bad)]))
    result = item.propose()
    assert result.status == "invalid_proposal" and result.proposal is None
    client.messages.create.assert_called_once()


def test_wrong_tool_name_is_rejected():
    item, _ = adapter(response(content=[tool(name="execute")]))
    assert item.propose().status == "invalid_proposal"


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_refusal_and_truncation_stop_before_tool_input_dispatch(stop):
    # Even an apparently usable tool request must not survive these stops.
    item, client = adapter(response(stop=stop))
    result = item.propose()
    assert result.status == stop and result.proposal is None
    assert len(item.messages) == 2
    with pytest.raises(InferenceBlocked):
        item.propose()
    client.messages.create.assert_called_once()


@pytest.mark.parametrize("stop,content", [
    ("tool_use", [tool(), tool()]), ("tool_use", []),
    ("pause_turn", [tool()]), (None, [tool()]), ("end_turn", [tool()]),
    ("tool_use", [NS(type="server_tool_use"), tool()]),
    ("tool_use", [NS(type="unknown"), tool()]),
])
def test_ambiguous_or_unsupported_responses_stop(stop, content):
    item, _ = adapter(response(stop=stop, content=content))
    assert item.propose().status == "invalid_response"


def test_missing_content_is_invalid():
    item, _ = adapter(NS(stop_reason="tool_use", usage=None))
    assert item.propose().status == "invalid_response"


def test_abstention_is_not_a_finding():
    item, _ = adapter(response(stop="end_turn", content=[NS(type="text", text="Confirmed flaw!")]))
    result = item.propose()
    assert result.status == "abstained" and result.proposal is None


@pytest.mark.parametrize("raw,expected", [
    (None, (None, None, None, None)),
    (NS(input_tokens=12, output_tokens=0), (12, 0, None, None)),
    (NS(input_tokens=12, output_tokens=5, cache_creation_input_tokens=2, cache_read_input_tokens=0), (12, 5, 2, 0)),
    (NS(input_tokens=True, output_tokens=-1, cache_creation_input_tokens="2", cache_read_input_tokens=1.5), (None, None, None, None)),
])
def test_usage_preserves_unknown_not_zero(raw, expected):
    item, _ = adapter(response(usage=raw))
    assert tuple(vars(item.propose().usage).values()) == expected


@pytest.mark.parametrize("stage", ["with_options", "create"])
def test_errors_consume_attempt_without_retry_or_exception_leak(stage):
    item, client = adapter()
    method = client.with_options if stage == "with_options" else client.messages.create
    method.side_effect = RuntimeError("secret credential and sensitive provider response")
    result = item.propose()
    assert result.status == "request_error" and result.proposal is None
    assert result.usage.input_tokens is None and result.usage.output_tokens is None
    assert "secret" not in repr(result)
    assert item.attempts == 1
    with pytest.raises(InferenceBlocked):
        item.propose()
    assert method.call_count == 1


@pytest.mark.parametrize("kwargs", [
    {"mock_opt_in": False}, {"mock_opt_in": 1},
    {"reviewed_synthetic": False}, {"reviewed_synthetic": "yes"},
])
def test_mock_and_review_opt_ins(kwargs):
    with pytest.raises(InferenceBlocked):
        adapter(**kwargs)


@pytest.mark.parametrize("model", ["", "openai/gpt-4o", "anthropic/claude-opus-5-5", "http://localhost", "claude-x\n", None])
def test_no_model_defaults_or_provider_routing(model):
    with pytest.raises(ValueError):
        adapter(model=model)


@pytest.mark.parametrize("allowed", [[], [request()] * 17, [request(), request()], "anything"])
def test_allowed_request_bounds(allowed):
    with pytest.raises(ValueError):
        adapter(allowed_requests=allowed)


def test_input_snapshot_and_prevalidation():
    allowed = [request()]
    item, _ = adapter(allowed_requests=allowed)
    allowed[0]["parameters"]["variant"] = "beta"
    assert item.propose().status == "proposed"
    with pytest.raises(PackError):
        adapter(allowed_requests=[request(operation_id="shell")])


def test_native_construction_fails_closed_without_import_or_environment_access():
    import builtins
    from unittest.mock import patch

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert name != "anthropic", "Live gate must not import SDK"
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", guarded_import), patch("os.environ.get", side_effect=AssertionError("No environment access")):
        with pytest.raises(InferenceBlocked, match="live inference opt-in"):
            DecisionAdapter.native(credential="mock-key", model=MODEL)
        with pytest.raises(InferenceBlocked, match="ANTHROPIC_CUSTOM_HEADERS"):
            DecisionAdapter.native(credential="mock-key", model=MODEL, live_opt_in=True)
    assert BASE_URL == "http://localhost:8080/anthropic"


@pytest.mark.parametrize("credential", ["", None, "key\r\nAuthorization: other", "key with space"])
def test_native_requires_explicit_valid_credential(credential):
    with pytest.raises(ValueError):
        DecisionAdapter.native(credential=credential, model=MODEL, live_opt_in=True)
