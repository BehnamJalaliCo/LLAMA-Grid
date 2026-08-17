#!/usr/bin/env python3
"""Small stdlib-only HTTP dispatcher for independent llama-server replicas.

Each request is sent to one complete model replica.  This is intentionally a
request-level dispatcher: it does not split a single decode across workers.
"""

from __future__ import annotations

import argparse
import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterable


DEFAULT_BACKENDS = ("10.50.0.21:8080", "10.50.0.22:8080")
PROXY_PATHS = {"/completion", "/v1/completions", "/v1/chat/completions"}


class DispatcherState:
    def __init__(self, backends: tuple[str, ...], timeout: float) -> None:
        self.backends = backends
        self.timeout = timeout
        self.lock = threading.Lock()
        self.next_backend = 0

    def select(self) -> str:
        with self.lock:
            backend = self.backends[self.next_backend % len(self.backends)]
            self.next_backend += 1
            return backend


def split_backend(backend: str) -> tuple[str, int]:
    host, sep, port = backend.rpartition(":")
    if not sep:
        return backend, 8080
    return host, int(port)


class DispatcherHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    state: DispatcherState

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep the service log useful without logging prompts or responses.
        super().log_message(fmt, *args)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_json(
                200,
                {
                    "status": "ok",
                    "backends": list(self.state.backends),
                    "mode": "request_round_robin",
                },
            )
            return
        if self.path == "/ready":
            statuses = []
            for backend in self.state.backends:
                statuses.append(self.backend_health(backend))
            code = 200 if all(item["ok"] for item in statuses) else 503
            self.send_json(code, {"status": "ok" if code == 200 else "degraded", "backends": statuses})
            return
        self.send_error(404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path not in PROXY_PATHS:
            self.send_error(404, "not found")
            return

        length_header = self.headers.get("Content-Length")
        if length_header is None:
            self.send_error(411, "Content-Length required")
            return
        try:
            length = int(length_header)
            if length < 0 or length > 64 * 1024 * 1024:
                raise ValueError
        except ValueError:
            self.send_error(413, "invalid request size")
            return

        body = self.rfile.read(length)
        backend = self.state.select()
        host, port = split_backend(backend)
        started = time.monotonic()
        try:
            conn = http.client.HTTPConnection(host, port, timeout=self.state.timeout)
            forward_headers = {
                "Content-Type": self.headers.get("Content-Type", "application/json"),
                "Accept": self.headers.get("Accept", "application/json"),
                "Content-Length": str(len(body)),
                "Connection": "close",
            }
            conn.request("POST", self.path, body=body, headers=forward_headers)
            response = conn.getresponse()
            is_stream = self.headers.get("Accept", "").lower().find("text/event-stream") >= 0
            is_stream = is_stream or response.getheader("Content-Type", "").lower().startswith("text/event-stream")

            if is_stream:
                self.send_response(response.status)
                self.send_header("Content-Type", response.getheader("Content-Type", "text/event-stream"))
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("X-Backend", backend)
                self.end_headers()
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
                    self.wfile.write(chunk)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            else:
                payload = response.read()
                self.send_response(response.status)
                content_type = response.getheader("Content-Type")
                if content_type:
                    self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.send_header("X-Backend", backend)
                self.end_headers()
                self.wfile.write(payload)
            elapsed = time.monotonic() - started
            print(f"backend={backend} status={response.status} bytes={len(body)} elapsed={elapsed:.3f}s", flush=True)
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started
            print(f"backend={backend} error={exc!r} elapsed={elapsed:.3f}s", flush=True)
            if not self.wfile.closed:
                self.send_error(502, f"backend unavailable: {exc}")
        finally:
            try:
                conn.close()
            except UnboundLocalError:
                pass

    def backend_health(self, backend: str) -> dict[str, object]:
        host, port = split_backend(backend)
        started = time.monotonic()
        try:
            conn = http.client.HTTPConnection(host, port, timeout=3.0)
            conn.request("GET", "/health")
            response = conn.getresponse()
            response.read()
            return {"backend": backend, "ok": response.status == 200, "status": response.status, "ms": round((time.monotonic() - started) * 1000, 2)}
        except Exception as exc:  # noqa: BLE001
            return {"backend": backend, "ok": False, "error": str(exc), "ms": round((time.monotonic() - started) * 1000, 2)}
        finally:
            try:
                conn.close()
            except UnboundLocalError:
                pass

    def send_json(self, code: int, value: object) -> None:
        payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", default="10.50.0.2")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--backend", action="append", dest="backends", default=[])
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()
    backends = tuple(args.backends) if args.backends else DEFAULT_BACKENDS
    if not backends:
        raise SystemExit("at least one --backend is required")
    state = DispatcherState(backends, args.timeout)
    DispatcherHandler.state = state
    server = ThreadingHTTPServer((args.listen, args.port), DispatcherHandler)
    print(f"listening={args.listen}:{args.port} backends={','.join(backends)}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
