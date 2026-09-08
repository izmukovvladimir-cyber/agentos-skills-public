"""Minimal stdlib JSON-RPC client for gbrain MCP streamable-http endpoints.

Verified pattern (mirrors ``scripts/task-board-gbrain.sh::_call_mcp``):

- Single JSON-RPC POST to the ``/<service>/mcp`` URL. NO ``initialize``
  handshake — the gbrain servers run ``FASTMCP_STATELESS_HTTP=1``, so a lone
  ``tools/list`` or ``tools/call`` request works.
- Headers: ``Content-Type: application/json``,
  ``Accept: application/json, text/event-stream``,
  ``Authorization: Bearer <token>``.
- Body: ``{"jsonrpc":"2.0","id":1,"method":<method>,"params":<params>}``.
- Response may be plain JSON OR Server-Sent Events. We scan for the first
  ``data: <json>`` frame; otherwise parse the whole body as JSON.
- ``result.isError`` truthy -> treated as a failed call; the first
  ``content[].text`` is surfaced as the (redacted) error message.
- On success we prefer ``result.structuredContent``; else we parse / collect
  the ``result.content[].text`` payloads.

Security: the token is never logged. Every exception message is passed
through :func:`redact.redact` so a token echoed in an error body never leaks.
"""

from __future__ import annotations

import json
import logging
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from typing import Any

import redact

logger = logging.getLogger("gbrain_doctor.mcp")


class McpError(Exception):
    """An MCP call failed at the HTTP, URL, protocol, or tool level.

    Attributes:
        message: Redacted, human-readable error detail.
        status_code: HTTP status when the failure was an HTTP error, else
            ``None`` (URL/socket/protocol/tool-level failures).
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        # The message is redacted defensively so even a caller passing a raw
        # server error body cannot leak a token through ``str(McpError)``.
        safe = redact.redact(message)
        super().__init__(safe)
        self.message: str = safe
        self.status_code: int | None = status_code


def _parse_body(body: str) -> dict[str, Any]:
    """Parse an MCP HTTP body that may be plain JSON or SSE.

    Args:
        body: The decoded response body text.

    Returns:
        The decoded JSON-RPC envelope as a dict.

    Raises:
        McpError: When no parseable JSON / ``data:`` frame is found.
    """
    # SSE path: find the first ``data: <json>`` frame.
    for line in body.splitlines():
        if line.startswith("data: "):
            frame = line[6:].strip()
            if not frame:
                continue
            try:
                return json.loads(frame)
            except json.JSONDecodeError as exc:
                raise McpError(f"malformed SSE data frame: {exc}") from exc

    # Plain JSON path.
    text = body.strip()
    if not text:
        raise McpError("empty response body")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise McpError(f"non-JSON, non-SSE response: {exc}") from exc


def _extract_result(envelope: dict[str, Any]) -> dict[str, Any]:
    """Validate a JSON-RPC envelope and return its ``result`` object.

    Args:
        envelope: The decoded JSON-RPC response.

    Returns:
        The ``result`` object (a dict).

    Raises:
        McpError: On JSON-RPC ``error``, ``result.isError``, or a missing /
            malformed ``result``.
    """
    if "error" in envelope and envelope["error"]:
        err = envelope["error"]
        if isinstance(err, dict):
            detail = err.get("message") or json.dumps(err, default=str)
        else:
            detail = str(err)
        raise McpError(f"JSON-RPC error: {detail}")

    result = envelope.get("result")
    if not isinstance(result, dict):
        raise McpError("response missing 'result' object")

    if result.get("isError"):
        content = result.get("content") or []
        msg = "unknown tool error"
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                msg = first.get("text") or msg
        raise McpError(f"tool error: {msg}")

    return result


# Per-endpoint MCP session cache. Stateful streamable-http servers (the
# default unless ``FASTMCP_STATELESS_HTTP=1``) reject calls with HTTP 400
# "Missing session ID" until an ``initialize`` handshake is performed. We do
# the handshake lazily on the first such rejection and reuse the returned
# session id. Stateless servers never trigger this path, so the original
# single-shot behaviour is preserved for them.
_SESSIONS: dict[str, str] = {}
_SESSION_LOCK = threading.Lock()
_PROTOCOL_VERSION = "2025-06-18"


def _post_once(
    server_url: str,
    token: str,
    body_obj: dict,
    timeout: float,
    session_id: str | None = None,
) -> tuple[str, dict[str, str]]:
    """POST one JSON-RPC message. Return ``(body_text, lowercased_headers)``.

    Raises:
        McpError: On HTTP/URL/socket/TLS failure (message redacted).
    """
    payload = json.dumps(body_obj).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = urllib.request.Request(
        server_url, data=payload, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return text, resp_headers
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001 — error-body read is best-effort
            detail = ""
        raise McpError(f"HTTP {exc.code}: {detail}", status_code=exc.code) from exc
    except urllib.error.URLError as exc:
        raise McpError(f"URL error: {exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise McpError(f"timeout after {timeout}s: {exc}") from exc
    except ssl.SSLError as exc:
        raise McpError(f"TLS error: {exc}") from exc


def _handshake(server_url: str, token: str, timeout: float) -> str:
    """Open a stateful MCP session and return its id (also cached).

    Performs ``initialize`` (capturing the ``Mcp-Session-Id`` response header)
    then the ``notifications/initialized`` ack.

    Raises:
        McpError: When the server returns no ``Mcp-Session-Id`` header.
    """
    init_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "gbrain-doctor", "version": "0.1"},
        },
    }
    _, resp_headers = _post_once(server_url, token, init_body, timeout)
    session_id = (resp_headers.get("mcp-session-id") or "").strip()
    if not session_id:
        raise McpError(
            "server requires a session but returned no Mcp-Session-Id header"
        )
    # Ack initialization (a notification: no id, no result). Best-effort —
    # the session is already usable, so a non-fatal ack failure is ignored.
    try:
        _post_once(
            server_url,
            token,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            timeout,
            session_id=session_id,
        )
    except McpError:
        pass
    _SESSIONS[server_url] = session_id
    return session_id


def mcp_call(
    server_url: str,
    token: str,
    method: str,
    params: dict,
    timeout: float = 15.0,
) -> tuple[dict, float]:
    """Issue a JSON-RPC call to an MCP streamable-http URL.

    Works against both stateless (``FASTMCP_STATELESS_HTTP=1``) and stateful
    servers: the first attempt is session-less; if a stateful server rejects
    it with HTTP 400 "Missing session ID", an ``initialize`` handshake runs
    once and the call is retried with the session header. Subsequent calls to
    the same endpoint reuse the cached session.

    Args:
        server_url: The full ``/<service>/mcp`` endpoint URL.
        token: Raw Bearer token (never logged).
        method: JSON-RPC method, e.g. ``"tools/list"`` or ``"tools/call"``.
        params: JSON-RPC params object.
        timeout: Socket timeout in seconds.

    Returns:
        A tuple of ``(result_obj, latency_ms)`` where ``result_obj`` is the
        validated JSON-RPC ``result`` dict.

    Raises:
        McpError: On HTTP error, URL/socket error, timeout, protocol error,
            JSON-RPC error, or ``result.isError``. The message is redacted.
    """
    body_obj = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}

    start = time.monotonic()
    session_id = _SESSIONS.get(server_url)
    try:
        body, _ = _post_once(server_url, token, body_obj, timeout, session_id=session_id)
    except McpError as exc:
        # Stateful server with no (or stale) session — handshake once, retry.
        # Stateless servers never emit this error, so they skip the handshake.
        # Match the specific session-id wording (FastMCP: "Missing session
        # ID"; header form "Mcp-Session-Id") rather than a bare "session"
        # substring, to avoid misclassifying unrelated endpoint errors while
        # still catching every spelling of the missing/stale-session message.
        _m = exc.message.lower()
        needs_session = exc.status_code in (400, 404) and (
            "session id" in _m or "session-id" in _m
        )
        if not needs_session:
            raise
        # Serialize handshakes per process; if a concurrent caller already
        # refreshed the session while we waited, reuse theirs instead of
        # opening a second one.
        with _SESSION_LOCK:
            cached = _SESSIONS.get(server_url)
            if cached and cached != session_id:
                session_id = cached
            else:
                session_id = _handshake(server_url, token, timeout)
        body, _ = _post_once(server_url, token, body_obj, timeout, session_id=session_id)

    latency_ms = (time.monotonic() - start) * 1000.0
    envelope = _parse_body(body)
    result = _extract_result(envelope)
    return result, latency_ms


def tools_list(
    server_url: str, token: str, timeout: float = 15.0
) -> tuple[list[dict], float]:
    """List the tools exposed by an MCP endpoint.

    Args:
        server_url: The ``/<service>/mcp`` endpoint URL.
        token: Raw Bearer token.
        timeout: Socket timeout in seconds.

    Returns:
        A tuple of ``(tools, latency_ms)`` where ``tools`` is the list of
        tool descriptor dicts (possibly empty).

    Raises:
        McpError: As per :func:`mcp_call`.
    """
    result, latency_ms = mcp_call(server_url, token, "tools/list", {}, timeout)
    tools = result.get("tools")
    if tools is None:
        # Some stateless servers return tools nested in structuredContent.
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            tools = structured.get("tools")
    if not isinstance(tools, list):
        tools = []
    return tools, latency_ms


def tool_call(
    server_url: str,
    token: str,
    name: str,
    arguments: dict,
    timeout: float = 15.0,
) -> tuple[dict, float]:
    """Invoke a single MCP tool and return its decoded payload.

    Args:
        server_url: The ``/<service>/mcp`` endpoint URL.
        token: Raw Bearer token.
        name: Tool name, e.g. ``"stats"``.
        arguments: Tool arguments object.
        timeout: Socket timeout in seconds.

    Returns:
        A tuple of ``(payload, latency_ms)``. ``payload`` is
        ``result.structuredContent`` when present; otherwise a dict
        ``{"content": [<parsed-or-raw texts>]}`` built from
        ``result.content[].text``.

    Raises:
        McpError: As per :func:`mcp_call`.
    """
    result, latency_ms = mcp_call(
        server_url,
        token,
        "tools/call",
        {"name": name, "arguments": arguments},
        timeout,
    )

    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured, latency_ms

    # Fall back to assembling content[].text, parsing JSON where possible.
    collected: list[Any] = []
    for chunk in result.get("content", []) or []:
        if not isinstance(chunk, dict):
            continue
        text = chunk.get("text")
        if text is None:
            continue
        try:
            collected.append(json.loads(text))
        except (json.JSONDecodeError, TypeError):
            collected.append(text)

    # Single decoded JSON object is the common case — return it directly so
    # callers get the natural shape rather than a wrapper list.
    if len(collected) == 1 and isinstance(collected[0], dict):
        return collected[0], latency_ms
    return {"content": collected}, latency_ms
