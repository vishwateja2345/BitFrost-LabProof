"""Opt-in clients for a stock Bifrost gateway and for Tavily Search, direct or through a Bifrost relay.

No credential or environment lookup, redirects, environment proxies, tool calls or client-side retries. A token is an
explicit argument that is never written to a record or echoed, and errors never carry provider text. Bifrost owns
retries, budgets and failover. The request shapes follow the Bifrost and Tavily documentation: `/v1/chat/completions` with an
`x-bf-vk` virtual key, `/relay/NAME/search`, and Tavily's `/search`.
"""
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime
from hashlib import sha256
import http.client
import json
import math
import re
import time
from urllib.parse import urlsplit

from .contracts import ValidationError, require

CHAT_PATH = "/v1/chat/completions"
SEARCH_HOST = "api.tavily.com"
MAX_REQUEST_BYTES = 131_072
MAX_CHAT_RESPONSE = 262_144
MAX_SEARCH_RESPONSE = 512_000
MAX_ERROR_BYTES = 8_192
MAX_REPLY_CHARS = 20_000
MAX_TOKENS = 4_096
MAX_FALLBACKS = 3
MAX_TIMEOUT = 180.0
MAX_EXCERPT_CHARS = 3_000
MAX_RESULTS = 5
MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")
LABEL = re.compile(r"^[A-Za-z0-9._:/@+-]{1,128}$")
RELAY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
URL_CHARS = re.compile(r"[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]{1,2000}")  # RFC 3986 characters only: no quotes, spaces, brackets or controls
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
# Refusal types documented by Bifrost; any other type is reported without provider text.
REFUSALS = {"budget_exceeded", "rate_limited", "token_limited", "request_limited", "model_blocked", "provider_blocked",
            "access_blocked", "virtual_key_required", "access_not_found", "relay_blocked"}


class GatewayError(ValidationError):
    """Sanitized: only an HTTP status and a documented refusal type, never provider text."""

    def __init__(self, message, *, status=None, kind=None):
        super().__init__(message)
        self.status, self.kind = status, kind


class SearchError(ValidationError):
    """Sanitized: only an HTTP status, never provider text."""

    def __init__(self, message, *, status=None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(raw: bytes):
    return sha256(raw).hexdigest()


def gateway_origin(value):
    require(isinstance(value, str) and 0 < len(value) <= 200 and value.isascii() and value == value.strip(), "invalid gateway URL")
    parts = urlsplit(value)
    try:
        port = parts.port
    except ValueError:
        raise ValidationError("invalid gateway port") from None
    host = (parts.hostname or "").lower()
    require(parts.scheme in ("http", "https") and host and parts.username is None and parts.password is None
            and not parts.query and not parts.fragment and parts.path in ("", "/"),
            "gateway URL must be an origin without credentials, path, query or fragment")
    remote_ok = parts.scheme == "https" and re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host) is not None and not host.split(".")[-1].isdigit()
    require(host in LOOPBACK or remote_ok, "plain HTTP is allowed only for a loopback gateway; remote gateways need an HTTPS hostname")
    return parts.scheme, host, port or (443 if parts.scheme == "https" else 80)


def post(target, path, body, *, headers, timeout, max_bytes, keep_error_body=False):
    """One POST to a fixed origin; no redirects, proxies or credential reads."""
    scheme, host, port = target
    connection = (http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection)(host, port, timeout=timeout)
    deadline = time.monotonic() + timeout
    try:
        connection.request("POST", path, body=body, headers={"Content-Type": "application/json", "Accept": "application/json",
                                                              "Accept-Encoding": "identity", **headers})
        response = connection.getresponse()
        if response.status != 200 and not keep_error_body:
            return Response(response.status, b"")  # Never echo provider error bodies.
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise GatewayError("compressed responses are unsupported")
        limit = max_bytes if response.status == 200 else MAX_ERROR_BYTES
        data = bytearray()
        while len(data) <= limit:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            chunk = response.read1(min(16_384, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > limit:
            require(response.status != 200, "response exceeds byte bound")
            del data[limit:]
        return Response(response.status, bytes(data))
    finally:
        connection.close()


class ScriptedTransport:
    """Ordered local responses for tests and the offline demo; not a claim of provider compatibility."""
    is_scripted = True

    def __init__(self, fixtures):
        require(isinstance(fixtures, list) and len(fixtures) <= 64, "scripted responses must be a bounded array")
        self.fixtures, self.calls = list(fixtures), []

    def __call__(self, target, path, body, *, headers, timeout, max_bytes, keep_error_body=False):
        require(bool(self.fixtures), "scripted response queue exhausted")
        status, value = self.fixtures.pop(0)
        self.calls.append({"target": target, "path": path, "body": json.loads(body), "header_names": sorted(headers)})
        return Response(status, value if isinstance(value, bytes) else json_bytes(value))


def _label(value):
    return value if isinstance(value, str) and LABEL.fullmatch(value) else None


def _count(value):
    return value if type(value) is int and 0 <= value <= 10**9 else None


def _refusal(raw):
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None
    kind = data.get("type")
    if kind is None and isinstance(data.get("error"), dict):
        kind = data["error"].get("type")
    return kind if isinstance(kind, str) and kind in REFUSALS else None


def _served_by(data):
    extra = data.get("extra_fields")
    info = extra.get("routing_info") if isinstance(extra, dict) else None
    if isinstance(info, dict):
        fallback = info.get("is_fallback")
        if "is_fallback" not in info and (info.get("provider") or info.get("model")):
            fallback = False  # Bifrost omits the false value on a primary-served response.
        return {"provider": _label(info.get("provider")), "model": _label(info.get("model")),
                "is_fallback": fallback if type(fallback) is bool else None}
    model = _label(data.get("model"))
    return None if model is None else {"provider": None, "model": model, "is_fallback": None}


def _token(value):
    require(isinstance(value, str) and 0 < len(value) <= 512 and all(33 <= ord(c) <= 126 for c in value), "invalid credential")
    return value


class GatewayClient:
    """Chat through Bifrost's OpenAI-compatible endpoint with an explicit virtual key."""

    def __init__(self, url, model, *, token, fallbacks=(), transport=None, allow_network=False, max_tokens=700, timeout=60.0, json_mode=False):
        self.target = gateway_origin(url)
        require(isinstance(model, str) and MODEL.fullmatch(model) is not None, "invalid model name")
        fallbacks = list(fallbacks)
        require(len(fallbacks) <= MAX_FALLBACKS and all(isinstance(item, str) and MODEL.fullmatch(item) for item in fallbacks)
                and len({model, *fallbacks}) == len(fallbacks) + 1, "invalid fallback models")
        require(type(max_tokens) is int and 1 <= max_tokens <= MAX_TOKENS, "invalid token ceiling")
        require(type(timeout) in (int, float) and math.isfinite(timeout) and 1 <= timeout <= MAX_TIMEOUT, "invalid gateway timeout")
        require(type(json_mode) is bool, "invalid JSON mode flag")
        self.json_mode = json_mode
        self.transport = transport if transport is not None else post
        require(getattr(self.transport, "is_scripted", False) or allow_network is True, "gateway access requires explicit network opt-in")
        self.token = _token(token)
        self.model, self.fallbacks, self.max_tokens, self.timeout = model, fallbacks, max_tokens, float(timeout)
        self.scripted = bool(getattr(self.transport, "is_scripted", False))

    def chat(self, messages):
        """One bounded request; returns a reply record or raises a sanitized GatewayError."""
        require(isinstance(messages, list) and 1 <= len(messages) <= 4 and all(
            isinstance(m, dict) and set(m) == {"role", "content"} and m["role"] in ("system", "user")
            and isinstance(m["content"], str) and 0 < len(m["content"]) <= 40_000 for m in messages), "invalid gateway messages")
        payload = {"model": self.model, "messages": messages, "temperature": 0, "max_tokens": self.max_tokens, "stream": False}
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}  # OpenAI-compatible; opt-in, a gateway or provider may ignore or reject it
        if self.fallbacks:
            payload["fallbacks"] = self.fallbacks
        body = json_bytes(payload)
        require(len(body) <= MAX_REQUEST_BYTES, "gateway request exceeds byte bound")
        started = time.monotonic()
        try:
            response = self.transport(self.target, CHAT_PATH, body, headers={"x-bf-vk": self.token}, timeout=self.timeout,
                                      max_bytes=MAX_CHAT_RESPONSE, keep_error_body=True)
        except GatewayError:
            raise
        except ValidationError:
            if self.scripted:
                raise
            raise GatewayError("gateway transport failed; not retried; usage unknown") from None
        except Exception:
            raise GatewayError("gateway transport failed; not retried; usage unknown") from None
        require(isinstance(response, Response) and type(response.status) is int and isinstance(response.body, bytes), "invalid gateway transport response")
        limit = MAX_CHAT_RESPONSE if response.status == 200 else MAX_ERROR_BYTES
        if len(response.body) > limit:
            raise GatewayError("gateway response exceeds byte bound")
        raw = response.body
        try:
            data = json.loads(raw.decode("utf-8"))
            data = data if isinstance(data, dict) else None
        except (UnicodeError, ValueError, RecursionError):
            data = None
        if response.status != 200:
            kind = _refusal(raw)
            raise GatewayError(f"gateway HTTP {response.status}" + (f" ({kind})" if kind else ""), status=response.status, kind=kind)
        try:
            require(data is not None, "invalid gateway JSON")
            choices = data.get("choices")
            require(isinstance(choices, list) and choices and isinstance(choices[0], dict), "gateway response has no choices")
            choice = choices[0]
            message = choice.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            require(isinstance(content, str) and 0 < len(content) <= MAX_REPLY_CHARS, "gateway reply text is missing or too large")
            require(choice.get("finish_reason") == "stop", "gateway reply was truncated or filtered")
        except (ValueError, TypeError, RecursionError, OverflowError):
            raise GatewayError("invalid gateway response contract") from None
        if self.token in content:
            raise GatewayError("gateway reply reflected the credential; discarded")
        reported = data.get("usage")
        usage = {key: _count(reported.get(key)) if isinstance(reported, dict) else None
                 for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
        routing = _served_by(data)
        if routing:
            routing = {key: None if isinstance(value, str) and self.token in value else value for key, value in routing.items()}
        extra = data.get("extra_fields") if isinstance(data.get("extra_fields"), dict) else {}
        latency = extra.get("latency")  # Bifrost reports milliseconds.
        latency = round(float(latency) / 1000, 3) if type(latency) in (int, float) and 0 <= latency < 86_400_000 else round(time.monotonic() - started, 3)
        return {"text": content, "usage": usage, "served_by": routing, "latency_seconds": latency,
                "request_sha256": digest(body), "response_sha256": digest(raw)}


def _date(value):
    """Tavily's published_date is a best-effort string, documented as an HTTP date; ISO dates are accepted too."""
    if not isinstance(value, str) or not 8 <= len(value) <= 64:
        return None
    try:
        if re.match(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value[:10]).isoformat()
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


class SearchClient:
    """Tavily Search, direct (Bearer key) or through a Bifrost relay (virtual key, the Tavily key stays in the gateway)."""

    def __init__(self, *, api_key, relay_url=None, relay=None, transport=None, allow_network=False, timeout=20.0):
        require((relay_url is None) == (relay is None), "a relay needs both a gateway URL and a relay name")
        self.api_key = _token(api_key)
        require(type(timeout) in (int, float) and math.isfinite(timeout) and 1 <= timeout <= MAX_TIMEOUT, "invalid search timeout")
        if relay is None:
            self.target, self.path, self.via = ("https", SEARCH_HOST, 443), "/search", "tavily"
            self.headers = {"Authorization": "Bearer " + self.api_key}
        else:
            require(isinstance(relay, str) and RELAY.fullmatch(relay) is not None, "invalid relay name")
            self.target, self.path, self.via = gateway_origin(relay_url), f"/relay/{relay}/search", "bifrost_relay"
            self.headers = {"x-bf-vk": self.api_key}
        self.transport = transport if transport is not None else post
        require(getattr(self.transport, "is_scripted", False) or allow_network is True, "search access requires explicit network opt-in")
        self.scripted = bool(getattr(self.transport, "is_scripted", False))
        self.timeout = float(timeout)

    def search(self, query, domains, *, max_results=3):
        """One bounded search restricted to `domains`; returns normalized rows and the credits the provider reported."""
        require(isinstance(query, str) and 0 < len(query) <= 300 and query == query.strip(), "invalid search query")
        require(isinstance(domains, (list, tuple)) and 1 <= len(domains) <= 10 and all(isinstance(d, str) and d for d in domains), "invalid search domains")
        require(type(max_results) is int and 1 <= max_results <= MAX_RESULTS, "invalid result count")
        body = json_bytes({"query": query, "topic": "general", "search_depth": "basic", "max_results": max_results,
                           "include_domains": list(domains), "include_domains_mode": "restrict", "auto_parameters": False,
                           "include_answer": False, "include_raw_content": False, "include_images": False,
                           "include_usage": True, "include_published_date": True})
        try:
            response = self.transport(self.target, self.path, body, headers=self.headers, timeout=self.timeout, max_bytes=MAX_SEARCH_RESPONSE)
        except SearchError:
            raise
        except ValidationError:
            if self.scripted:
                raise
            raise SearchError("search transport failed; not retried") from None
        except Exception:
            raise SearchError("search transport failed; not retried") from None
        require(isinstance(response, Response) and type(response.status) is int and isinstance(response.body, bytes), "invalid search transport response")
        if response.status != 200:
            raise SearchError(f"search HTTP {response.status}", status=response.status)
        if len(response.body) > MAX_SEARCH_RESPONSE:
            raise SearchError("search response exceeds byte bound")
        try:
            data = json.loads(response.body.decode("utf-8"))
            rows = data.get("results") if isinstance(data, dict) else None
            require(isinstance(rows, list) and len(rows) <= MAX_RESULTS, "search results are missing or exceed the count bound")
        except (UnicodeError, ValueError, TypeError, RecursionError):
            raise SearchError("invalid search response contract") from None
        results = []
        for row in rows:
            if not isinstance(row, dict) or any(isinstance(v, str) and self.api_key in v for v in row.values()):
                continue  # Provider values are untrusted; a reflected credential discards the row.
            url, content = row.get("url"), row.get("content")
            if not (isinstance(url, str) and URL_CHARS.fullmatch(url) and isinstance(content, str) and content.strip()):
                continue
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
                continue
            title = row.get("title") if isinstance(row.get("title"), str) and row["title"].strip() else url
            results.append({"url": url, "title": title[:300], "content": content[:MAX_EXCERPT_CHARS], "published_date": _date(row.get("published_date"))})
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        credits = usage.get("credits")
        credits = credits if type(credits) in (int, float) and math.isfinite(credits) and credits >= 0 else None
        return {"results": results, "credits": credits}
