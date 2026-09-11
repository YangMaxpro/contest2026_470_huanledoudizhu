#!/usr/bin/env python3
"""Test strict framing, CRC, signed PCM and lossless WAV generation."""
import pathlib
import struct
import tempfile
import unittest
import wave
import zlib
from decode_audio_dump import HEADER, decode, statistics, write_wav


class AudioDumpTest(unittest.TestCase):
    def setUp(self):
        self.pcm = struct.pack("<16000h", *([-32768, -1, 0, 32767] * 4000))
        self.lines = [HEADER]
        for offset in range(0, 16000, 32):
            self.lines.append(f"PCM16 DATA {offset:05d} "
                              + self.pcm[offset * 2:offset * 2 + 64].hex())
        self.lines.append(f"PCM16 END crc32={zlib.crc32(self.pcm):08x}")

    def test_roundtrip_and_multiple(self):
        log = "nsh> \x1b[K" + "\r\n".join(self.lines) + "\r\nnsh> "
        self.assertEqual(decode(log), [self.pcm])
        self.assertEqual(decode(log + "\n" + log), [self.pcm, self.pcm])
        self.assertIn("peak=32768 clipped=8000", statistics(self.pcm))
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "clip.wav"
            write_wav(path, self.pcm)
            with wave.open(str(path), "rb") as audio:
                self.assertEqual(audio.getnchannels(), 1)
                self.assertEqual(audio.getsampwidth(), 2)
                self.assertEqual(audio.getframerate(), 16000)
                self.assertEqual(audio.getnframes(), 16000)
                self.assertEqual(audio.readframes(16000), self.pcm)
            with self.assertRaises(FileExistsError):
                write_wav(path, self.pcm)

    def test_reject_corrupt_or_incomplete(self):
        variants = [[], self.lines[1:], self.lines[:-1],
                    self.lines[:5] + self.lines[6:],
                    self.lines[:5] + [self.lines[4]] + self.lines[5:],
                    self.lines[:5] + [HEADER] + self.lines[5:],
                    self.lines[:-1] + ["PCM16 END crc32=00000000"],
                    [HEADER.replace("16000", "8000")] + self.lines[1:],
                    self.lines[:1] + [self.lines[1] + "injected log"] + self.lines[2:]]
        for lines in variants:
            with self.subTest(lines=len(lines)), self.assertRaises(ValueError):
                decode("\n".join(lines))


if __name__ == "__main__":
    unittest.main()
