import http.client
from http.server import HTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

import control
from server import Service, make_handler


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = control.read_json(Path(__file__).with_name("studio.json"))
        self.issuer = Mock()
        self.issuer.issue.return_value = {"device_token": "fake-device", "agent_token": "fake-agent", "expires_at": 1234567890}
        self.client = Mock()
        self.client.start.return_value = {"agent_id": "agent-test", "status": "created"}
        self.factory = Mock(return_value=self.client)
        self.path = Path(self.tmp.name) / "state.json"
        self.service = Service(self.config, self.issuer, self.path, self.factory, True)

    def start_body(self, device):
        return {key: device[key] for key in ("channel_name", "uid", "agent_uid")}

    def test_provision_start_stop(self):
        device = self.service.dispatch("/device", {})
        self.assertNotIn("agent_token", device)
        self.factory.assert_not_called()
        self.assertEqual(self.service.dispatch("/device", {})["channel_name"], device["channel_name"])
        body = self.start_body(device)
        for _ in range(2):
            self.assertEqual(self.service.dispatch("/agent/start", body)["agent_id"], "agent-test")
        self.client.start.assert_called_once()
        for _ in range(2):
            self.assertEqual(self.service.dispatch("/agent/stop", {"agent_id": "agent-test"}), {"status": "stopped"})
        self.client.stop.assert_called_once_with("agent-test")
        self.assertNotEqual(self.service.dispatch("/device", {})["channel_name"], device["channel_name"])
        self.assertNotIn("fake-device", self.path.read_text())
        self.assertNotIn("fake-agent", self.path.read_text())

    def test_unknown_creation_blocks_retry_after_restart(self):
        device = self.service.dispatch("/device", {})
        self.client.start.side_effect = control.ControlError("unknown")
        with self.assertRaises(control.ControlError):
            self.service.dispatch("/agent/start", self.start_body(device))
        restarted = Service(self.config, self.issuer, self.path, self.factory, True)
        with self.assertRaises(control.ControlError):
            restarted.dispatch("/agent/start", self.start_body(device))
        self.client.start.assert_called_once()
        with self.assertRaises(control.ControlError):
            restarted.dispatch("/device", {})

    def test_identity_and_live_gate(self):
        device = self.service.dispatch("/device", {})
        bad = self.start_body(device)
        bad["uid"] = "3333"
        with self.assertRaises(control.ControlError):
            self.service.dispatch("/agent/start", bad)
        self.service.allow_live = False
        with self.assertRaises(control.ControlError):
            self.service.dispatch("/agent/start", self.start_body(device))
        self.client.start.assert_not_called()

    def test_stop_failure_retains_session(self):
        device = self.service.dispatch("/device", {})
        self.service.dispatch("/agent/start", self.start_body(device))
        self.client.stop.side_effect = control.ControlError("unknown")
        with self.assertRaises(control.ControlError):
            self.service.dispatch("/agent/stop", {"agent_id": "agent-test"})
        self.assertEqual(control.read_json(self.path)["status"], "created")

    def test_http_auth_and_provision_loopback_only(self):
        secret = "offline-test-secret-" + "x" * 32
        server = HTTPServer(("127.0.0.1", 0), make_handler(self.service, secret))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def call(headers, raw=b"{}"):
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                try:
                    conn.request("POST", "/device", raw, headers)
                    response = conn.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    conn.close()

            self.assertEqual(call({})[0], 401)
            headers = {"Authorization": "Bearer " + secret, "Content-Type": "application/json"}
            status, result = call(headers)
            self.assertEqual(status, 200)
            self.assertEqual(result["token"], "fake-device")
            self.assertNotIn("agent_token", result)
            self.assertEqual(call(headers, b"[")[0], 400)
            self.assertEqual(call(headers, b"x" * 8193)[0], 413)
            self.factory.assert_not_called()
        finally:
            server.shutdown()
            thread.join(3)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
