import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import control


class Response:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status

    def read(self, limit):
        return self.body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Opener:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def open(self, request, timeout):
        self.calls.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class Tests(unittest.TestCase):
    def setUp(self):
        self.config = control.read_json(Path(__file__).with_name("studio.json"))

    def test_template(self):
        control.validate(self.config)
        self.assertFalse(self.config["properties"]["parameters"]["enable_dump"])

    def test_payload_isolated(self):
        old = copy.deepcopy(self.config)
        payload = control.build_payload(self.config, "board-test", "1001", "2001", "fake-token")
        self.assertEqual(payload["properties"]["remote_rtc_uids"], ["1001"])
        self.assertEqual(payload["properties"]["agent_rtc_uid"], "2001")
        self.assertEqual(self.config, old)
        self.assertNotIn("token", self.config["properties"])

    def test_invalid_identity(self):
        for channel, device, agent in (("../bad", "1", "2"), ("ok", "1", "1"),
                                       ("ok", "0", "2"), ("ok", "4294967296", "2")):
            with self.subTest(channel=channel, device=device, agent=agent):
                with self.assertRaises(control.ControlError):
                    control.build_payload(self.config, channel, device, agent, "fake-token")

    def test_no_secret_template(self):
        self.config["properties"]["tts"]["params"]["api_key"] = "secret"
        with self.assertRaises(control.ControlError):
            control.validate(self.config)

    def test_no_redirect_or_custom_host(self):
        self.assertIsNone(control.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test"))
        self.config["api_origin"] = "http://api.sd-rtn.com"
        with self.assertRaises(control.ControlError):
            control.validate(self.config)

    def test_join_leave(self):
        opener = Opener(Response(b'{"agent_id":"agent-test","status":"RUNNING"}'))
        client = control.Client(self.config, "fake-token", opener)
        payload = control.build_payload(self.config, "test", "1", "2", "agent-token")
        self.assertEqual(client.start(payload)["agent_id"], "agent-test")
        self.assertTrue(opener.calls[0].full_url.endswith("/join"))
        self.assertEqual(json.loads(opener.calls[0].data), payload)
        opener.result = Response(b'{}')
        client.stop("agent-test")
        self.assertTrue(opener.calls[-1].full_url.endswith("/agents/agent-test/leave"))

    def test_errors_never_retry_or_echo_secrets(self):
        for result in (TimeoutError("secret"), Response(b"secret"), Response(b"[]"),
                       Response(b"{}"), Response(b"x" * (1024 * 1024 + 1)),
                       urllib.error.HTTPError("https://test", 403, "secret", {}, None)):
            opener = Opener(result)
            with self.subTest(result=type(result).__name__):
                with self.assertRaises(control.ControlError) as error:
                    control.Client(self.config, "fake-token", opener).start({})
                self.assertNotIn("secret", str(error.exception))
                self.assertEqual(len(opener.calls), 1)

    def test_offline_default(self):
        with patch.object(control.Client, "post") as post, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(control.main(["validate"]), 0)
            self.assertEqual(control.main(["start", "--channel", "test"]), 1)
            post.assert_not_called()

    def test_reserved_state_survives_failed_creation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "CONVOAI_AUTH_TOKEN": "fake-auth", "CONVOAI_AGENT_TOKEN": "fake-agent"
        }), contextlib.redirect_stdout(io.StringIO()):
            state = Path(tmp) / "session.json"
            args = ["start", "--live", "--channel", "test", "--state", str(state)]
            with patch.object(control.Client, "start", side_effect=control.ControlError("unknown")) as start:
                self.assertEqual(control.main(args), 1)
                self.assertEqual(control.main(args), 1)
                self.assertEqual(start.call_count, 1)
            saved = state.read_text()
            self.assertNotIn("fake-auth", saved)
            self.assertNotIn("fake-agent", saved)
            self.assertEqual(json.loads(saved)["status"], "creation_unknown")

    def test_session_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "CONVOAI_AUTH_TOKEN": "fake-auth", "CONVOAI_AGENT_TOKEN": "fake-agent"
        }), contextlib.redirect_stdout(io.StringIO()):
            state = Path(tmp) / "session.json"
            with patch.object(control.Client, "start", return_value={"agent_id": "test-agent", "status": "created"}):
                self.assertEqual(control.main(["start", "--live", "--channel", "test", "--state", str(state)]), 0)
            with patch.object(control.Client, "stop") as stop:
                args = ["stop", "--live", "--state", str(state)]
                self.assertEqual(control.main(args), 0)
                self.assertEqual(control.main(args), 0)
                stop.assert_called_once_with("test-agent")
            self.assertEqual(control.read_json(state)["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
