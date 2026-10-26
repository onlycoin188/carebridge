"""WSGI 앱 (표준 라이브러리만 사용).

같은 `app` 하나를
  - Vercel: api/*.py 에서 불러 서버리스 함수로 실행 (정적 파일은 public/ 을 Vercel이 직접 제공)
  - 로컬·Render·Docker: server.py 가 public/ 정적 파일과 함께 실행
에서 그대로 쓴다. 서버는 메모 원문을 저장하거나 로그에 남기지 않는다.
"""
from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from . import pipeline
from .llm import LLMError, resolve_provider

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
RATE = int(os.environ.get("RATE_LIMIT_PER_HOUR", "40"))
MAX_BODY = 64_000
_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def _allowed(ip: str) -> bool:
    """IP당 시간당 요청 제한 (서버리스에서는 인스턴스별로 적용되는 느슨한 보호막)."""
    now = time.time()
    with _lock:
        q = _hits[ip]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= RATE:
            return False
        q.append(now)
        return True


def _client_ip(environ) -> str:
    for h in ("HTTP_X_VERCEL_FORWARDED_FOR", "HTTP_X_FORWARDED_FOR", "HTTP_X_REAL_IP"):
        v = environ.get(h)
        if v:
            return v.split(",")[0].strip()
    return environ.get("REMOTE_ADDR", "")


_SEC = [("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer")]


def _json(start_response, code: int, obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    status = {200: "200 OK", 400: "400 Bad Request", 404: "404 Not Found", 405: "405 Method Not Allowed",
              413: "413 Payload Too Large", 429: "429 Too Many Requests", 502: "502 Bad Gateway"}[code]
    start_response(status, [("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store"),
                            ("Content-Length", str(len(body)))] + _SEC)
    return [body]


def _static(start_response, path: str):
    if path in ("", "/"):
        path = "/index.html"
    target = (PUBLIC / path.lstrip("/")).resolve()
    if not str(target).startswith(str(PUBLIC)) or not target.is_file():
        return _json(start_response, 404, {"error": "찾는 페이지가 없습니다."})
    ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
        ctype += "; charset=utf-8"
    body = target.read_bytes()
    start_response("200 OK", [("Content-Type", ctype), ("Content-Length", str(len(body))),
                              ("Cache-Control", "no-cache")] + _SEC)
    return [body]


def app(environ, start_response):
    path = environ.get("PATH_INFO", "/") or "/"
    method = environ.get("REQUEST_METHOD", "GET").upper()

    if path.rstrip("/") == "/api/health":
        prov, model = resolve_provider()
        return _json(start_response, 200, {"ok": True, "provider": prov, "model": model,
                                           "mode": "demo" if prov == "mock" else "ai"})

    if path.rstrip("/") in ("/api/analyze", "/api/reply"):
        if method != "POST":
            return _json(start_response, 405, {"error": "POST로 요청해 주세요."})
        if not _allowed(_client_ip(environ)):
            return _json(start_response, 429, {"error": "요청이 많아 잠시 쉬어 갑니다. 한 시간 뒤 다시 시도해 주세요."})
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
            if length > MAX_BODY:
                return _json(start_response, 413, {"error": "요청이 너무 큽니다."})
            raw = environ["wsgi.input"].read(length) if length else b""
            body = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            return _json(start_response, 400, {"error": "요청 형식이 올바르지 않습니다."})
        try:
            if path.rstrip("/") == "/api/analyze":
                names = body.get("registered_names") or []
                ctx = body.get("context") if isinstance(body.get("context"), dict) else {}
                out = pipeline.analyze(str(body.get("memo", "")), ctx, names if isinstance(names, list) else [])
            else:
                out = pipeline.translate_reply(str(body.get("message", "")), str(body.get("target_lang", "en")))
            return _json(start_response, 200, out)
        except ValueError as e:
            return _json(start_response, 400, {"error": str(e)})
        except LLMError as e:
            return _json(start_response, 502, {"error": "AI 분석에 실패했습니다. 잠시 뒤 다시 시도해 주세요.",
                                               "detail": str(e)[:300]})

    if path.startswith("/api/"):
        return _json(start_response, 404, {"error": "없는 주소입니다."})
    if method != "GET":
        return _json(start_response, 405, {"error": "허용되지 않는 요청입니다."})
    return _static(start_response, path)
