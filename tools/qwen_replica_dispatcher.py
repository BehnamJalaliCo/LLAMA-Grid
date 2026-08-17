#!/usr/bin/env python3
"""Small stdlib-only HTTP dispatcher for independent llama-server replicas.

Each request is sent to one complete model replica.  This is intentionally a
request-level dispatcher: it does not split a single decode across workers.
"""

from __future__ import annotations

import argparse
import hmac
import http.client
import json
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


DEFAULT_BACKENDS = ("10.50.0.21:8080", "10.50.0.22:8080")
MODEL_NAME = "qwen3-coder-next"
PROXY_PATHS = {"/completion", "/v1/completions", "/v1/chat/completions"}
OPENAI_PROXY_PATHS = {"/v1/completions", "/v1/chat/completions"}
PUBLIC_PATHS = {"/health", "/ready"}
REQUEST_ID_RE = re.compile(r"[^A-Za-z0-9_.:-]")


class DispatcherState:
    def __init__(self, backends: tuple[str, ...], timeout: float, health_interval: float) -> None:
        self.backends = backends
        self.timeout = timeout
        self.health_interval = health_interval
        self.condition = threading.Condition()
        self.inflight = {backend: 0 for backend in backends}
        self.healthy = {backend: False for backend in backends}
        self.next_backend = 0
        self.stop_event = threading.Event()
        self.health_thread: threading.Thread | None = None
        self.metrics_lock = threading.Lock()
        self.metrics = {
            "requests": 0,
            "errors": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    def start(self) -> None:
        self.refresh_health()
        self.health_thread = threading.Thread(target=self._health_loop, name="backend-health", daemon=True)
        self.health_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.health_thread is not None:
            self.health_thread.join(timeout=2.0)

    def _health_loop(self) -> None:
        while not self.stop_event.wait(self.health_interval):
            self.refresh_health()

    def refresh_health(self) -> list[dict[str, object]]:
        statuses = [self.backend_health(backend) for backend in self.backends]
        with self.condition:
            for status in statuses:
                self.healthy[status["backend"]] = bool(status["ok"])
            self.condition.notify_all()
        return statuses

    def backend_health(self, backend: str) -> dict[str, object]:
        host, port = split_backend(backend)
        started = time.monotonic()
        conn = None
        try:
            conn = http.client.HTTPConnection(host, port, timeout=3.0)
            conn.request("GET", "/health")
            response = conn.getresponse()
            response.read()
            return {
                "backend": backend,
                "ok": response.status == 200,
                "status": response.status,
                "ms": round((time.monotonic() - started) * 1000, 2),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "backend": backend,
                "ok": False,
                "error": str(exc),
                "ms": round((time.monotonic() - started) * 1000, 2),
            }
        finally:
            if conn is not None:
                conn.close()

    def acquire(self) -> str:
        # Select the least-loaded healthy replica.  A single request is never
        # split across replicas.
        with self.condition:
            while True:
                healthy = [backend for backend in self.backends if self.healthy.get(backend, False)]
                if healthy:
                    least = min(self.inflight[backend] for backend in healthy)
                    candidates = [backend for backend in healthy if self.inflight[backend] == least]
                    backend = candidates[self.next_backend % len(candidates)]
                    self.next_backend += 1
                    self.inflight[backend] += 1
                    return backend
                self.condition.wait(timeout=1.0)

    def release(self, backend: str) -> None:
        with self.condition:
            self.inflight[backend] -= 1
            self.condition.notify_all()

    def mark_unhealthy(self, backend: str) -> None:
        with self.condition:
            self.healthy[backend] = False
            self.condition.notify_all()

    def snapshot(self) -> dict[str, int]:
        with self.condition:
            return dict(self.inflight)

    def health_snapshot(self) -> dict[str, bool]:
        with self.condition:
            return dict(self.healthy)

    def record_request(self, status: int, input_tokens: int | None, output_tokens: int | None) -> None:
        with self.metrics_lock:
            self.metrics["requests"] += 1
            if status >= 400:
                self.metrics["errors"] += 1
            if input_tokens is not None:
                self.metrics["input_tokens"] += input_tokens
            if output_tokens is not None:
                self.metrics["output_tokens"] += output_tokens

    def metrics_text(self) -> str:
        with self.metrics_lock:
            metrics = dict(self.metrics)
        healthy = self.health_snapshot()
        inflight = self.snapshot()
        lines = [
            "# HELP llamagrid_requests_total Total proxied API requests.",
            "# TYPE llamagrid_requests_total counter",
            f"llamagrid_requests_total {metrics['requests']}",
            "# HELP llamagrid_request_errors_total Total proxied API requests with HTTP status >= 400.",
            "# TYPE llamagrid_request_errors_total counter",
            f"llamagrid_request_errors_total {metrics['errors']}",
            "# HELP llamagrid_input_tokens_total Input tokens reported by backends.",
            "# TYPE llamagrid_input_tokens_total counter",
            f"llamagrid_input_tokens_total {metrics['input_tokens']}",
            "# HELP llamagrid_output_tokens_total Output tokens reported by backends.",
            "# TYPE llamagrid_output_tokens_total counter",
            f"llamagrid_output_tokens_total {metrics['output_tokens']}",
        ]
        for backend in self.backends:
            label = backend.replace('"', '')
            lines.append(f'llamagrid_backend_healthy{{backend="{label}"}} {int(healthy.get(backend, False))}')
            lines.append(f'llamagrid_backend_inflight{{backend="{label}"}} {inflight.get(backend, 0)}')
        return "\n".join(lines) + "\n"


def split_backend(backend: str) -> tuple[str, int]:
    host, sep, port = backend.rpartition(":")
    if not sep:
        return backend, 8080
    return host, int(port)


class DispatcherHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    state: DispatcherState

    def log_message(self, fmt: str, *args: object) -> None:
        # All request logs are emitted as structured JSON by the handlers.
        return

    def request_id(self) -> str:
        supplied = self.headers.get("X-Request-ID", "")[:128]
        value = REQUEST_ID_RE.sub("_", supplied) if supplied else uuid.uuid4().hex
        return value or uuid.uuid4().hex

    def authorized(self) -> bool:
        expected = os.environ.get("LLAMAGRID_API_KEY", "")
        value = self.headers.get("Authorization", "")
        scheme, separator, token = value.partition(" ")
        return bool(expected and separator and scheme.lower() == "bearer" and hmac.compare_digest(token, expected))

    def require_auth(self) -> bool:
        if self.authorized():
            return True
        self.send_json(
            401,
            {"error": {"message": "Missing or invalid API key", "type": "authentication_error"}},
            {"WWW-Authenticate": "Bearer", "X-Request-ID": self.request_id()},
        )
        return False

    def do_GET(self) -> None:  # noqa: N802
        request_id = self.request_id()
        if self.path == "/health":
            self.send_json(
                200,
                {
                    "status": "ok",
                    "backends": list(self.state.backends),
                    "mode": "least_inflight",
                    "inflight": self.state.snapshot(),
                    "healthy": self.state.health_snapshot(),
                },
                {"X-Request-ID": request_id},
            )
            return
        if self.path == "/ready":
            statuses = self.state.refresh_health()
            code = 200 if all(item["ok"] for item in statuses) else 503
            self.send_json(code, {"status": "ok" if code == 200 else "degraded", "backends": statuses}, {"X-Request-ID": request_id})
            return
        if self.path == "/metrics":
            if not self.require_auth():
                return
            payload = self.state.metrics_text().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Request-ID", request_id)
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/v1/models":
            if not self.require_auth():
                return
            self.send_json(
                200,
                {
                    "object": "list",
                    "data": [{"id": MODEL_NAME, "object": "model", "created": int(time.time()), "owned_by": "beyra-ai"}],
                },
                {"X-Request-ID": request_id},
            )
            return
        self.send_error(404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path not in PROXY_PATHS:
            self.send_error(404, "not found")
            return
        if not self.require_auth():
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
        stream_requested = False
        if path in OPENAI_PROXY_PATHS:
            try:
                request_json = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.send_json(400, {"error": {"message": "Request body must be valid JSON", "type": "invalid_request_error"}})
                return
            if not isinstance(request_json, dict):
                self.send_json(400, {"error": {"message": "Request body must be a JSON object", "type": "invalid_request_error"}})
                return
            model = request_json.get("model")
            if model is not None and model != MODEL_NAME:
                self.send_json(404, {"error": {"message": f"Model '{model}' is not available", "type": "invalid_request_error"}})
                return
            request_json["model"] = MODEL_NAME
            stream_requested = bool(request_json.get("stream", False))
            body = json.dumps(request_json, separators=(",", ":")).encode("utf-8")

        request_id = self.request_id()
        backend = self.state.acquire()
        host, port = split_backend(backend)
        started = time.monotonic()
        conn = None
        status = 502
        input_tokens = None
        output_tokens = None
        try:
            conn = http.client.HTTPConnection(host, port, timeout=self.state.timeout)
            forward_headers = {
                "Content-Type": self.headers.get("Content-Type", "application/json"),
                "Accept": "text/event-stream" if stream_requested else self.headers.get("Accept", "application/json"),
                "Content-Length": str(len(body)),
                "Connection": "close",
            }
            conn.request("POST", self.path, body=body, headers=forward_headers)
            response = conn.getresponse()
            status = response.status
            is_stream = self.headers.get("Accept", "").lower().find("text/event-stream") >= 0
            is_stream = is_stream or response.getheader("Content-Type", "").lower().startswith("text/event-stream")
            is_stream = is_stream or stream_requested

            if is_stream:
                self.send_response(response.status)
                self.send_header("Content-Type", response.getheader("Content-Type", "text/event-stream"))
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("X-Backend", backend)
                self.send_header("X-Request-ID", request_id)
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                stream_buffer = bytearray()
                while True:
                    chunk = response.read1(8192) if hasattr(response, "read1") else response.read(8192)
                    if not chunk:
                        break
                    input_tokens, output_tokens = update_stream_tokens(stream_buffer, chunk, input_tokens, output_tokens)
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
                self.send_header("X-Request-ID", request_id)
                self.end_headers()
                self.wfile.write(payload)
                try:
                    value = json.loads(payload.decode("utf-8"))
                    input_tokens, output_tokens = extract_tokens(value)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass
            elapsed = time.monotonic() - started
            if response.status >= 500:
                self.state.mark_unhealthy(backend)
            self.state.record_request(response.status, input_tokens, output_tokens)
            log_request(request_id, self.path, backend, response.status, elapsed, input_tokens, output_tokens)
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started
            self.state.mark_unhealthy(backend)
            self.state.record_request(502, None, None)
            log_request(request_id, self.path, backend, 502, elapsed, None, None, error=type(exc).__name__)
            if not self.wfile.closed:
                self.send_error(502, f"backend unavailable: {exc}")
        finally:
            self.state.release(backend)
            if conn is not None:
                conn.close()

    def send_json(self, code: int, value: object, extra_headers: dict[str, str] | None = None) -> None:
        payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        for name, header_value in (extra_headers or {}).items():
            self.send_header(name, header_value)
        self.end_headers()
        self.wfile.write(payload)


def extract_tokens(value: object) -> tuple[int | None, int | None]:
    if not isinstance(value, dict):
        return None, None
    usage = value.get("usage")
    if isinstance(usage, dict):
        return usage.get("prompt_tokens"), usage.get("completion_tokens")
    timings = value.get("timings")
    if isinstance(timings, dict):
        return timings.get("prompt_n"), timings.get("predicted_n")
    return value.get("tokens_evaluated"), value.get("tokens_predicted")


def update_stream_tokens(buffer: bytearray, chunk: bytes, input_tokens: int | None,
                         output_tokens: int | None) -> tuple[int | None, int | None]:
    """Inspect SSE usage without delaying or buffering bytes sent to the client."""
    buffer.extend(chunk)
    while b"\n" in buffer:
        line, _, remainder = buffer.partition(b"\n")
        buffer[:] = remainder
        if not line.startswith(b"data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == b"[DONE]":
            continue
        try:
            parsed = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        current_input, current_output = extract_tokens(parsed)
        if current_input is not None:
            input_tokens = current_input
        if current_output is not None:
            output_tokens = current_output
    return input_tokens, output_tokens


def log_request(request_id: str, path: str, backend: str, status: int, elapsed: float,
                input_tokens: int | None, output_tokens: int | None, error: str | None = None) -> None:
    record: dict[str, object] = {
        "event": "request",
        "request_id": request_id,
        "path": path.split("?", 1)[0],
        "worker": backend,
        "status": status,
        "latency_ms": round(elapsed * 1000.0, 2),
    }
    if input_tokens is not None:
        record["input_tokens"] = input_tokens
    if output_tokens is not None:
        record["output_tokens"] = output_tokens
    if error is not None:
        record["error"] = error
    print(json.dumps(record, separators=(",", ":")), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", default="10.50.0.2")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--backend", action="append", dest="backends", default=[])
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--health-interval", type=float, default=5.0)
    args = parser.parse_args()
    backends = tuple(args.backends) if args.backends else DEFAULT_BACKENDS
    if not backends:
        raise SystemExit("at least one --backend is required")
    if not os.environ.get("LLAMAGRID_API_KEY"):
        raise SystemExit("LLAMAGRID_API_KEY is required")
    state = DispatcherState(backends, args.timeout, args.health_interval)
    DispatcherHandler.state = state
    state.start()
    server = ThreadingHTTPServer((args.listen, args.port), DispatcherHandler)
    print(json.dumps({"event": "listening", "listen": f"{args.listen}:{args.port}", "backends": list(backends), "healthy": state.health_snapshot()}, separators=(",", ":")), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        state.stop()
        server.server_close()


if __name__ == "__main__":
    main()
