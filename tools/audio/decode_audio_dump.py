#!/usr/bin/env python3
"""Validate an explicit PCM16 serial export and create an unmodified mono WAV.

No serial access, networking, normalization or playback. A corrupt/incomplete
capture is rejected, not repaired. The output path must not already exist.
"""
import argparse
import math
import pathlib
import re
import struct
import wave
import zlib

HEADER = "PCM16 BEGIN rate=16000 samples=16000 format=s16le"
DATA = re.compile(r"PCM16 DATA ([0-9]{5}) ([0-9a-f]{128})")
END = re.compile(r"PCM16 END crc32=([0-9a-f]{8})")


def decode(text):
    captures = []
    pending = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = line.find("PCM16 ")
        if marker < 0:
            continue
        line = line[marker:].strip()
        if line == HEADER:
            if pending is not None:
                raise ValueError(f"line {number}: interrupted capture")
            pending = bytearray()
        elif (match := DATA.fullmatch(line)) is not None:
            if pending is None:
                raise ValueError(f"line {number}: data without header")
            offset = int(match[1])
            if offset != len(pending) // 2 or offset >= 16000:
                raise ValueError(f"line {number}: missing/duplicate/out-of-order samples")
            pending.extend(bytes.fromhex(match[2]))
        elif (match := END.fullmatch(line)) is not None:
            if pending is None or len(pending) != 32000:
                raise ValueError(f"line {number}: incomplete capture")
            if zlib.crc32(pending) != int(match[1], 16):
                raise ValueError(f"line {number}: CRC mismatch")
            captures.append(bytes(pending))
            pending = None
        else:
            raise ValueError(f"line {number}: malformed PCM16 record")
    if pending is not None:
        raise ValueError("capture has no END record")
    if not captures:
        raise ValueError("no complete PCM16 capture found")
    return captures


def statistics(pcm):
    samples = struct.unpack("<16000h", pcm)
    dc = sum(samples) / len(samples)
    rms = math.sqrt(sum(x * x for x in samples) / len(samples))
    frames = [math.sqrt(sum(x * x for x in samples[i:i + 320]) / 320)
              for i in range(0, len(samples), 320)]
    return (f"samples=16000 nominal_rate=16000 dc={dc:.2f} rms={rms:.2f} "
            f"peak={max(abs(x) for x in samples)} "
            f"clipped={sum(x in (-32768, 32767) for x in samples)}\n"
            "20ms frame RMS: " + " ".join(f"{x:.1f}" for x in frames))


def write_wav(path, pcm):
    with pathlib.Path(path).open("xb") as stream:
        with wave.open(stream, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(pcm)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--index", type=int, default=1,
                        help="one-based capture index (default: 1)")
    args = parser.parse_args()
    try:
        if args.log.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("log exceeds 4 MiB; use a dedicated short capture log")
        captures = decode(args.log.read_text(encoding="utf-8", errors="replace"))
        if not 1 <= args.index <= len(captures):
            raise ValueError(f"index must be 1..{len(captures)}")
        pcm = captures[args.index - 1]
        write_wav(args.output, pcm)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Audio decode failed: {error}\n")
    print(f"CRC verified; capture {args.index}/{len(captures)} -> {args.output}")
    print(statistics(pcm))
    print("Original amplitude preserved; sample rate is configured, not measured.")


if __name__ == "__main__":
    main()
