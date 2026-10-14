#!/usr/bin/env python3
"""codex-image-gen.py — gpt-image-2 via the Codex/ChatGPT OAuth subscription.

Technique ported from NousResearch/hermes-agent plugins/image_gen/openai-codex
(forwarded by @izik_winner, 2026-05-27). Generates images with OpenAI's
gpt-image-2 by routing through the Codex Responses API `image_generation` tool
using our existing Codex OAuth token — NO OPENAI_API_KEY, no Higgsfield credits.

Endpoint: POST https://chatgpt.com/backend-api/codex/responses (SSE stream).
Auth: Bearer access_token from ~/.codex/auth.json (tokens.access_token).
Cloudflare gating: originator=codex_cli_rs + codex_cli_rs UA + ChatGPT-Account-ID
(decoded from the JWT). The VPS (non-residential IP) hits an INTERMITTENT CF
challenge (200 OK + empty stream); the residential proxy occasionally drops the
long stream. The tool retries across both routes (direct first, proxy fallback)
so a burst on one route does not fail the call — pass --proxy / CODEX_IMAGE_PROXY
so the fallback route is available.

Usage:
  codex-image-gen.py --prompt "..." [--quality low|medium|high]
                     [--aspect square|landscape|portrait] [--out PATH]
                     [--proxy URL] [--retries N]

Exit: 0 ok (prints saved path to stdout), non-zero on failure (reason to stderr).
The OAuth token is never printed or passed via argv.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_MIN_PNG_BYTES = 2048  # a real gpt-image-2 PNG is ~1MB; anything tiny is junk
_MAX_REF_IMAGES = 4
_MAX_REF_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB per reference — keeps payload sane
_ALLOWED_REF_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
# Patterns scrubbed from any error text before it reaches stderr.
_REDACT_RE = re.compile(
    r"(Bearer\s+[\w.\-]+)"            # Authorization header value
    r"|(eyJ[\w\-]+\.[\w\-]+\.[\w\-]+)"  # JWT-shaped strings
    r"|(access_token\"?\s*[:=]\s*\"?[\w.\-]+)"
    r"|([a-zA-Z][\w+.\-]*://[^/@\s]+:[^/@\s]+@)",  # proxy creds user:pass@ (any scheme: http, socks5, ...)
    re.IGNORECASE,
)

# First-16-byte signatures of the reference-image types we accept.
_IMG_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")  # PNG, JPEG


def _looks_like_image(head: bytes) -> bool:
    """True if the leading bytes match an allowed image type (PNG/JPEG/WEBP)."""
    if head.startswith(_IMG_MAGIC):
        return True
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"  # WEBP


def _redact(text: str) -> str:
    return _REDACT_RE.sub("[REDACTED]", str(text))


def _env_int(name: str, default: int) -> int:
    """Read a positive int from the environment, falling back on absent/garbage."""
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default

log = logging.getLogger("codex_image_gen")

AUTH_PATH = Path(os.environ.get("CODEX_AUTH_PATH", str(Path.home() / ".codex" / "auth.json")))

# Optional auto-refresh helper (same dir). Absence degrades to reading the
# stored token verbatim — keeps the script working even if the lib is missing.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from codex_token import ensure_fresh_token as _ensure_fresh_token
    from codex_token import TokenRevoked as _TokenRevoked
except Exception:  # noqa: BLE001
    _ensure_fresh_token = None

    class _TokenRevoked(Exception):
        pass

BASE_URL = "https://chatgpt.com/backend-api/codex"
CHAT_MODEL = "gpt-6-astra"      # host model that calls the image_generation tool
API_MODEL = "gpt-image-2"        # the actual image model
DEFAULT_OUT_DIR = Path.home() / ".codex-images"

SIZES = {"landscape": "1536x1024", "square": "1024x1024", "portrait": "1024x1536"}
INSTRUCTIONS = (
    "You are an assistant that must fulfill image generation requests by "
    "using the image_generation tool when provided."
)


def _read_stored_token() -> Optional[str]:
    try:
        d = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
        tok = (d.get("tokens") or {}).get("access_token")
        return tok.strip() if isinstance(tok, str) and tok.strip() else None
    except (OSError, ValueError) as exc:
        log.error("cannot read auth.json: %s", _redact(exc))
        return None


def _read_access_token() -> Optional[str]:
    """Return a fresh access_token, auto-refreshing near expiry via codex_token.

    Falls back to the stored token if the helper is missing or hits a transient
    error; returns None (with a clear hint) only when the grant is revoked and
    interactive re-login is required.
    """
    if _ensure_fresh_token is not None:
        try:
            return _ensure_fresh_token()
        except _TokenRevoked as exc:
            log.error(
                "Codex OAuth grant revoked (%s) — re-login: codex login --device-auth",
                _redact(exc),
            )
            return None
        except Exception as exc:  # noqa: BLE001 — degrade to stored token
            log.warning("token auto-refresh skipped (%s); using stored token", _redact(exc))
    return _read_stored_token()


def _cloudflare_headers(access_token: str) -> dict[str, str]:
    """Match codex-rs CLI so Cloudflare does not 403 the request."""
    headers = {
        "User-Agent": "codex_cli_rs/0.0.0 (Hermes Agent)",
        "originator": "codex_cli_rs",
    }
    try:
        parts = access_token.split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload_b64))
            acct = claims.get("https://api.openai.com/auth", {}).get("chatgpt_account_id")
            if isinstance(acct, str) and acct:
                headers["ChatGPT-Account-ID"] = acct
    except Exception:
        pass
    return headers


def _ref_data_url(raw: bytes, ext: str) -> str:
    """Return a base64 data URL for input_image from already-read bytes."""
    mime = "jpeg" if ext in ("jpg", "jpeg") else (ext or "png")
    return f"data:image/{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _build_payload(prompt: str, size: str, quality: str,
                   ref_blobs: Optional[list[tuple[bytes, str]]] = None) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    for raw, ext in (ref_blobs or []):
        content.append({"type": "input_image", "image_url": _ref_data_url(raw, ext)})
    return {
        "model": CHAT_MODEL,
        "store": False,
        "instructions": INSTRUCTIONS,
        "input": [{
            "type": "message",
            "role": "user",
            "content": content,
        }],
        "tools": [{
            "type": "image_generation",
            "model": API_MODEL,
            "size": size,
            "quality": quality,
            "output_format": "png",
            "background": "opaque",
            "partial_images": 1,
        }],
        "tool_choice": {
            "type": "allowed_tools",
            "mode": "required",
            "tools": [{"type": "image_generation"}],
        },
        "stream": True,
    }


def _extract_final_b64(value: Any) -> Optional[str]:
    """Return ONLY a completed image (image_generation_call.result).

    Partial frames (partial_image_b64) are deliberately ignored — a partial must
    not satisfy success, or a truncated stream would write a half image and exit 0.
    """
    found: Optional[str] = None
    if isinstance(value, dict):
        if value.get("type") == "image_generation_call":
            result = value.get("result")
            if isinstance(result, str) and result:
                found = result
        for child in value.values():
            nested = _extract_final_b64(child)
            if nested:
                found = nested
    elif isinstance(value, list):
        for child in value:
            nested = _extract_final_b64(child)
            if nested:
                found = nested
    return found


def _extract_error(value: Any) -> Optional[str]:
    """Return a sanitized error message if the event signals a failed response."""
    if isinstance(value, dict):
        etype = value.get("type")
        if isinstance(etype, str) and etype in (
            "response.failed", "response.error", "error", "response.incomplete",
        ):
            err = value.get("error") if isinstance(value.get("error"), dict) else value
            msg = err.get("message") if isinstance(err, dict) else None
            return _redact(msg or json.dumps(err)[:300])
        err_obj = value.get("error")
        if isinstance(err_obj, dict):
            msg = err_obj.get("message")
            return _redact(msg or json.dumps(err_obj)[:300])
        for child in value.values():
            nested = _extract_error(child)
            if nested:
                return nested
    elif isinstance(value, list):
        for child in value:
            nested = _extract_error(child)
            if nested:
                return nested
    return None


def _iter_sse_json(response: Any):
    event_name: Optional[str] = None
    data_lines: list[str] = []

    def flush():
        nonlocal event_name, data_lines
        if not data_lines:
            event_name = None
            return None
        raw = "\n".join(data_lines).strip()
        event = event_name
        event_name = None
        data_lines = []
        if not raw or raw == "[DONE]":
            return None
        try:
            payload = json.loads(raw)
        except ValueError:
            # Malformed data: frame — surface it (redacted) instead of hiding it,
            # so a backend failure isn't indistinguishable from "no image".
            log.warning("malformed SSE data frame: %s", _redact(raw[:200]))
            return None
        if isinstance(payload, dict) and event and "type" not in payload:
            payload["type"] = event
        return payload

    for line in response.iter_lines():
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        line = str(line)
        if line == "":
            payload = flush()
            if payload is not None:
                yield payload
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip())
    payload = flush()
    if payload is not None:
        yield payload


class _TransientGenError(Exception):
    """A retryable failure: CF challenge (200 + empty stream), proxy/stream drop,
    HTTP 429/5xx, or a corrupt result. Distinct from permanent failures (bad
    request, revoked auth, invalid input) which must NOT be retried."""


def _one_attempt(*, headers: dict[str, str], payload: dict[str, Any],
                 timeout: Any, proxy: Optional[str]) -> bytes:
    """Run ONE generation request; return validated PNG bytes.

    Raises _TransientGenError for retryable failures (empty stream = CF challenge,
    dropped stream, HTTP 403/408/429/5xx, corrupt result) and SystemExit for
    permanent ones (HTTP 400/401 — malformed request / revoked auth).
    """
    import httpx

    client_kw: dict[str, Any] = {"timeout": timeout, "headers": headers}
    if proxy:
        client_kw["proxy"] = proxy

    final_b64: Optional[str] = None
    stream_error: Optional[str] = None
    try:
        with httpx.Client(**client_kw) as http:
            with http.stream("POST", f"{BASE_URL}/responses", json=payload) as resp:
                if resp.status_code != 200:
                    resp.read()
                    sc = resp.status_code
                    body = _redact(resp.text[:400])
                    # 403 is usually a Cloudflare challenge; 408/425/429 and any 5xx are transient.
                    if sc in (403, 408, 425, 429) or 500 <= sc < 600:
                        raise _TransientGenError(f"HTTP {sc}: {body}")
                    raise SystemExit(f"HTTP {sc}: {body}")
                for event in _iter_sse_json(resp):
                    got = _extract_final_b64(event)
                    if got:
                        final_b64 = got
                    if stream_error is None:
                        stream_error = _extract_error(event)
    except SystemExit:
        raise                       # permanent (4xx) — propagate, do not retry
    except _TransientGenError:
        raise                       # already classified transient (non-200) — propagate to retry loop
    except Exception as exc:        # noqa: BLE001
        # Any other failure at the request boundary — httpx transport/proxy/URL/decode error,
        # or a client-construction error on a bad proxy URL. Redact (a socks5://user:pass@ URL
        # in the message must NOT leak) and treat as retryable so the other route can cover it.
        raise _TransientGenError(f"request error: {_redact(exc)}")

    if not final_b64:
        # 200 OK but no image = Cloudflare interstitial / transient backend miss.
        detail = f": {stream_error}" if stream_error else " (empty stream, likely CF challenge)"
        raise _TransientGenError(f"no completed image result{detail}")

    # Validate the bytes before declaring success — never write a silent junk file.
    try:
        raw = base64.b64decode(final_b64, validate=True)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise _TransientGenError(f"result is not valid base64: {_redact(exc)}")
    if len(raw) < _MIN_PNG_BYTES or not raw.startswith(_PNG_MAGIC):
        raise _TransientGenError(f"result is not a valid PNG (len={len(raw)})")
    return raw


def generate(prompt: str, *, quality: str, aspect: str, proxy: Optional[str],
             ref_images: Optional[list[Path]] = None, retries: int = 5) -> str:
    import httpx

    token = _read_access_token()
    if not token:
        raise SystemExit("no Codex OAuth token (run `codex login` / check ~/.codex/auth.json)")

    refs = ref_images or []
    if len(refs) > _MAX_REF_IMAGES:
        raise SystemExit(f"too many reference images ({len(refs)} > {_MAX_REF_IMAGES})")
    ref_blobs: list[tuple[bytes, str]] = []
    for ref in refs:
        if ref.suffix.lower() not in _ALLOWED_REF_EXTS:
            raise SystemExit(f"unsupported reference image type: {ref.suffix}")
        # Read each reference exactly ONCE, inside the protected block, and build the
        # payload from these bytes — so a delete/permission change after validation
        # can't surface as an uncaught traceback later in _build_payload.
        try:
            if not ref.is_file():
                raise SystemExit(f"reference image not found: {ref}")
            if ref.stat().st_size > _MAX_REF_IMAGE_BYTES:
                raise SystemExit(f"reference image too large: {ref} ({ref.stat().st_size} bytes)")
            raw = ref.read_bytes()
        except OSError as exc:
            raise SystemExit(f"cannot read reference image {ref}: {_redact(exc)}")
        # Sniff the actual bytes — a right extension over wrong content wastes a full
        # 1-2 min round-trip that the server rejects; catch it locally as permanent.
        if not _looks_like_image(raw[:16]):
            raise SystemExit(f"reference image content is not a supported image (PNG/JPEG/WEBP): {ref}")
        ref_blobs.append((raw, ref.suffix.lower().lstrip(".")))

    size = SIZES.get(aspect, SIZES["square"])
    headers = _cloudflare_headers(token)
    headers.update({
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    payload = _build_payload(prompt, size, quality, ref_blobs=ref_blobs)
    # read=180: a healthy gen (even `high`, ~2 min) streams SSE events continuously, so the
    # gap between reads stays small; a 180s silent gap means the stream stalled (dead proxy /
    # dropped CF conn) — fail fast so the alternating direct/proxy plan cycles to the next
    # route instead of burning up to 5 min on one hung attempt.
    timeout = httpx.Timeout(300.0, connect=30.0, read=180.0, write=30.0, pool=30.0)

    # Both routes fail in bursts: the direct VPS path hits an intermittent Cloudflare
    # challenge (200 + empty stream), the residential proxy occasionally drops the long
    # (~1-2 min) SSE stream. Retry across them so a burst on one route doesn't fail the
    # call. Direct first (free, no shared-proxy load); fall back to the proxy when given.
    attempts = max(1, retries)
    if proxy:
        plan = [(None if i % 2 == 0 else proxy) for i in range(attempts)]
    else:
        plan = [None] * attempts

    raw: Optional[bytes] = None
    last_err: Optional[str] = None
    for i, use_proxy in enumerate(plan):
        route = "proxy" if use_proxy else "direct"
        try:
            log.info("attempt %d/%d via %s", i + 1, len(plan), route)
            raw = _one_attempt(headers=headers, payload=payload, timeout=timeout,
                               proxy=use_proxy)
            break
        except _TransientGenError as exc:
            last_err = str(exc)
            if i + 1 < len(plan):
                backoff = min(2 + i * 2, 10)
                log.warning("attempt %d/%d (%s) failed: %s — retrying in %ds",
                            i + 1, len(plan), route, last_err, backoff)
                time.sleep(backoff)
            else:
                log.error("attempt %d/%d (%s) failed: %s", i + 1, len(plan), route, last_err)

    if raw is None:
        raise SystemExit(f"image generation failed after {len(plan)} attempts: {last_err}")

    out_dir = Path(os.environ.get("CODEX_IMAGE_OUT_DIR", str(DEFAULT_OUT_DIR)))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"codex_{API_MODEL}_{quality}_{time.time_ns()}_{uuid.uuid4().hex[:8]}.png"
    # Atomic write: temp in the same dir then os.replace (no half-written reads,
    # no same-second filename collision between concurrent callers).
    tmp = out.with_suffix(".png.tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, out)
    return str(out)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--quality", choices=["low", "medium", "high"], default="medium")
    ap.add_argument("--aspect", choices=["square", "landscape", "portrait"], default="square")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--proxy", default=None,
                    help="residential proxy if CF challenges the VPS IP; or set CODEX_IMAGE_PROXY "
                         "(env keeps user:pass out of argv/ps)")
    ap.add_argument("--ref-image", action="append", type=Path, default=None,
                    help="reference image (face/style) for image-to-image; repeatable")
    ap.add_argument("--retries", type=int, default=_env_int("CODEX_IMAGE_RETRIES", 5),
                    help="total attempts across direct/proxy on transient failures "
                         "(CF challenge / dropped stream); default 5 or CODEX_IMAGE_RETRIES")
    args = ap.parse_args(argv)

    prompt = (args.prompt or "").strip()
    if not prompt:
        print("empty prompt", file=sys.stderr)
        return 2

    proxy = args.proxy or os.environ.get("CODEX_IMAGE_PROXY") or None

    t0 = time.time()
    saved = generate(prompt, quality=args.quality, aspect=args.aspect, proxy=proxy,
                     ref_images=args.ref_image, retries=args.retries)
    if args.out:
        dest = Path(args.out)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Unique temp in the same dir → concurrent callers targeting the same
        # --out can't clobber each other's temp or race os.replace.
        tmp = dest.with_suffix(dest.suffix + f".{time.time_ns()}.{uuid.uuid4().hex[:8]}.tmp")
        tmp.write_bytes(Path(saved).read_bytes())
        os.replace(tmp, dest)
        saved = str(dest)
    log.info("ok: %s (%.1fs, %s, %s)", saved, time.time() - t0, args.quality, args.aspect)
    print(saved)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
