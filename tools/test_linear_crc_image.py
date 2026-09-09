#!/usr/bin/env python3
"""Host-only regression tests for the R1 image packager."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import make_bk7258_linear_crc_image as pack


class ImageTests(unittest.TestCase):
    def test_crc_vector(self):
        self.assertEqual(pack.crc16(b"123456789"), 0xAEE7)

    def test_padding(self):
        payload = b"AP" + b"\xff" * 30
        self.assertEqual(pack.encode_partition(b"AP"),
                         payload + pack.crc16(payload).to_bytes(2, "big"))

    def test_overflow_does_not_modify_base(self):
        base = bytearray(b"\x55" * 100)
        with self.assertRaises(ValueError):
            pack.replace_partition(base, 10, 33, b"x" * 32)
        self.assertEqual(base, b"\x55" * 100)

    def test_ap_only_preserves_cp_boot_and_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = bytes(range(256)) * (pack.FLASH_SIZE // 256)
            factory = root / "base.bin"
            ap = root / "ap.bin"
            output = root / "test.bin"
            update = root / "update.bin"
            factory.write_bytes(base)
            ap.write_bytes(b"AP test payload")
            command = [sys.executable, str(Path(pack.__file__)),
                       "--factory", str(factory), "--ap", str(ap),
                       "--output", str(output), "--update-output", str(update)]
            subprocess.run(command, check=True, capture_output=True)
            image = output.read_bytes()
            self.assertEqual(len(image), pack.FLASH_SIZE)
            self.assertEqual(image[:pack.AP_START], base[:pack.AP_START])
            end = pack.AP_START + pack.AP_SIZE
            self.assertEqual(image[end:], base[end:])
            self.assertEqual(update.read_bytes(), image[pack.BOOT_END:end])
            encoded = pack.encode_partition(ap.read_bytes())
            self.assertEqual(image[pack.AP_START:end], encoded +
                             b"\xff" * (pack.AP_SIZE - len(encoded)))
            result = subprocess.run(command, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), image)
            verify = [sys.executable, str(Path(pack.__file__).with_name("verify_bk7258_linear_crc_image.py")),
                      "--base", str(factory), "--ap", str(ap), "--image", str(output), "--update", str(update)]
            subprocess.run(verify, check=True, capture_output=True)
            update.write_bytes(b"bad")
            self.assertNotEqual(subprocess.run(verify, capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
