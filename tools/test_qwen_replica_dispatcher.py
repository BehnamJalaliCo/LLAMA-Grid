#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).with_name("qwen_replica_dispatcher.py")
spec = importlib.util.spec_from_file_location("qwen_replica_dispatcher", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class DispatcherHealthTests(unittest.TestCase):
    def state(self):
        state = module.DispatcherState(("127.0.0.1:1",), "m", "o", 10.0, 5.0)
        state.healthy["127.0.0.1:1"] = True
        return state

    def test_busy_transport_probe_failure_preserves_healthy_backend(self):
        state = self.state()
        state.inflight["127.0.0.1:1"] = 1
        state.backend_health = lambda backend: {"backend": backend, "ok": False, "error": "timed out"}
        statuses = state.refresh_health()
        self.assertTrue(state.healthy["127.0.0.1:1"])
        self.assertTrue(statuses[0]["preserved_busy"])

    def test_idle_transport_probe_failure_marks_backend_unhealthy(self):
        state = self.state()
        state.backend_health = lambda backend: {"backend": backend, "ok": False, "error": "timed out"}
        state.refresh_health()
        self.assertFalse(state.healthy["127.0.0.1:1"])

    def test_explicit_http_health_failure_marks_busy_backend_unhealthy(self):
        state = self.state()
        state.inflight["127.0.0.1:1"] = 1
        state.backend_health = lambda backend: {"backend": backend, "ok": False, "status": 503}
        state.refresh_health()
        self.assertFalse(state.healthy["127.0.0.1:1"])


if __name__ == "__main__":
    unittest.main()
