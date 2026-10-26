"""로컬·Render·Docker용 실행 파일 (외부 패키지 없음).

    python server.py        → http://localhost:7860

Vercel에서는 이 파일 대신 api/*.py 가 같은 WSGI 앱(carebridge.web.app)을 실행한다.
"""
from __future__ import annotations

import os
import sys
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from carebridge.llm import resolve_provider
from carebridge.web import app


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, fmt, *args):  # 본문은 남기지 않고 요청 줄만
        sys.stderr.write("%s\n" % (self.requestline.split(" HTTP")[0]))


def main():
    port = int(os.environ.get("PORT", "7860"))
    prov, model = resolve_provider()
    print(f"CareBridge  http://0.0.0.0:{port}  (AI: {prov} / {model})", flush=True)
    with make_server("0.0.0.0", port, app, server_class=ThreadingWSGIServer, handler_class=QuietHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
