#!/usr/bin/env python3
"""Build an 8 MiB BK7258 image from a factory image and OpenVela CP/AP bins.

BK7258 images with flash CRC enabled store every 32 payload bytes followed by
one big-endian CRC16.  The factory bootloader is copied unchanged because it
is already in the format expected by the R1 board.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


FLASH_SIZE = 0x800000
BOOT_END = 0x11000
CP_START, CP_SIZE = 0x11000, 0x154000
AP_START, AP_SIZE = 0x165000, 0x121000


def crc16(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x8005) if crc & 0x8000 else (crc << 1)
    return crc & 0xFFFF


def encode_partition(raw: bytes) -> bytes:
    encoded = bytearray()
    for offset in range(0, len(raw), 32):
        chunk = raw[offset : offset + 32]
        chunk += b"\xff" * (32 - len(chunk))
        encoded += chunk
        encoded += crc16(chunk).to_bytes(2, "big")
    return bytes(encoded)


def replace_partition(image: bytearray, start: int, size: int, raw: bytes) -> int:
    encoded = encode_partition(raw)
    if len(encoded) > size:
        raise ValueError(f"encoded partition at 0x{start:x} exceeds 0x{size:x}")
    image[start : start + size] = b"\xff" * size
    image[start : start + len(encoded)] = encoded
    return len(encoded)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--factory", type=Path, required=True)
    parser.add_argument("--cp", type=Path,
                        help="raw CP binary; omit to preserve the base CP")
    parser.add_argument("--ap", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--update-output", type=Path,
                        help="optional CP/AP-only update for address 0x11000")
    args = parser.parse_args()

    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    if args.update_output is not None:
        if args.update_output.exists() or args.update_output.resolve() == args.output.resolve():
            raise FileExistsError("update output must be a distinct new file")

    factory = args.factory.read_bytes()
    if len(factory) != FLASH_SIZE:
        raise ValueError(f"factory image must be exactly {FLASH_SIZE} bytes")
    image = bytearray(factory)
    cp_len = "preserved"
    if args.cp is not None:
        cp_len = replace_partition(image, CP_START, CP_SIZE,
                                   args.cp.read_bytes())
    ap_len = replace_partition(image, AP_START, AP_SIZE, args.ap.read_bytes())
    if image[:BOOT_END] != factory[:BOOT_END]:
        raise AssertionError("factory bootloader was modified")
    if image[AP_START + AP_SIZE:] != factory[AP_START + AP_SIZE:]:
        raise AssertionError("data outside firmware partitions was modified")
    args.output.write_bytes(image)
    if args.output.stat().st_size != FLASH_SIZE:
        raise AssertionError("output is not exactly 8 MiB")
    print(f"output={args.output} size={args.output.stat().st_size}")
    print(f"cp_encoded={cp_len} ap_encoded={ap_len} bootloader=preserved")
    print(f"image_sha256={hashlib.sha256(image).hexdigest()}")
    if args.update_output is not None:
        update = image[BOOT_END:AP_START + AP_SIZE]
        with args.update_output.open("xb") as stream:
            stream.write(update)
        print(f"update={args.update_output} start=0x{BOOT_END:x} end=0x{AP_START + AP_SIZE:x} size={len(update)}")
        print(f"update_sha256={hashlib.sha256(update).hexdigest()}")


if __name__ == "__main__":
    main()
