import base64
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import Mock
import zlib

import control
from tokens import TokenIssuer, load_official_builder


class Tests(unittest.TestCase):
    def setUp(self):
        self.config = control.read_json(Path(__file__).with_name("studio.json"))
        # Deliberately fake project credentials, never the user's certificate.
        self.config["app_id"] = "a" * 32
        self.certificate = "b" * 32

    def test_separate_identities_and_relative_expiry(self):
        builder = Mock()
        builder.build_token_with_rtm.side_effect = ["007fake-device", "007fake-agent"]
        result = TokenIssuer(self.config, self.certificate, builder).issue("test", "1001", "2001")
        calls = builder.build_token_with_rtm.call_args_list
        self.assertEqual(calls[0].args[2:], ("test", "1001", 1, 900, 900))
        self.assertEqual(calls[1].args[2:], ("test", "2001", 1, 900, 900))
        self.assertNotEqual(result["device_token"], result["agent_token"])
        self.assertEqual(result["expires_at"] - result["issued_at"], 900)
        self.assertNotIn("certificate", result)

    def test_invalid_inputs(self):
        for ttl in (0, 86400, True):
            with self.assertRaises(control.ControlError):
                TokenIssuer(self.config, self.certificate, Mock(), ttl)
        with self.assertRaises(control.ControlError):
            TokenIssuer(self.config, "bad", Mock())
        issuer = TokenIssuer(self.config, self.certificate, Mock())
        with self.assertRaises(control.ControlError):
            issuer.issue("test", "1", "1")

    def test_builder_failure(self):
        builder = Mock()
        builder.build_token_with_rtm.return_value = ""
        with self.assertRaises(control.ControlError):
            TokenIssuer(self.config, self.certificate, builder).issue("test", "1", "2")

    @unittest.skipUnless(os.environ.get("AGORA_TOKEN_BUILDER_DIR"), "Official builder source not selected")
    def test_official_builder_offline(self):
        builder = load_official_builder(os.environ["AGORA_TOKEN_BUILDER_DIR"])
        result = TokenIssuer(self.config, self.certificate, builder).issue("offline-test", "1001", "2001")
        for key, uid in (("device_token", b"1001"), ("agent_token", b"2001")):
            blob = zlib.decompress(base64.b64decode(result[key][3:]))
            position = 0

            def number(fmt):
                nonlocal position
                value, = struct.unpack_from(fmt, blob, position)
                position += struct.calcsize(fmt)
                return value

            def string():
                nonlocal position
                size = number("<H")
                value = blob[position:position + size]
                position += size
                return value

            self.assertEqual(len(string()), 32)
            self.assertEqual(string(), b"a" * 32)
            self.assertGreaterEqual(number("<I"), result["issued_at"])
            self.assertEqual(number("<I"), 900)
            number("<I")  # Salt
            self.assertEqual(number("<H"), 2)
            for service in (1, 2):
                self.assertEqual(number("<H"), service)
                privileges = {}
                for _ in range(number("<H")):
                    privilege = number("<H")
                    privileges[privilege] = number("<I")
                self.assertEqual(privileges, {1: 900, 2: 900, 3: 900, 4: 900} if service == 1 else {1: 900})
                if service == 1:
                    self.assertEqual(string(), b"offline-test")
                self.assertEqual(string(), uid)
            self.assertEqual(position, len(blob))


if __name__ == "__main__":
    unittest.main()
