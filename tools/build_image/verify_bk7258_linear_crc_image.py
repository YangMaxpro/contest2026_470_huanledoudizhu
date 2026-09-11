#!/usr/bin/env python3
"""Read-only verification of a CP/AP image against its base and raw inputs."""
import argparse
import hashlib
from pathlib import Path

import make_bk7258_linear_crc_image as pack


def verify_partition(image, path, start, size):
    raw = path.read_bytes()
    encoded = pack.encode_partition(raw)
    if len(encoded) > size:
        raise ValueError(f"partition too large: {path}")
    expected = encoded + b"\xff" * (size - len(encoded))
    if image[start:start + size] != expected:
        raise ValueError(f"partition content/CRC/padding mismatch: {path}")
    print(f"verified {path.name}: raw={len(raw)} encoded={len(encoded)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "ap", "image"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--cp", type=Path, help="omit when preserving base CP")
    parser.add_argument("--update", type=Path, help="verify CP/AP-only slice for 0x11000")
    args = parser.parse_args()
    base = args.base.read_bytes()
    image = args.image.read_bytes()
    if len(base) != pack.FLASH_SIZE or len(image) != pack.FLASH_SIZE:
        raise ValueError("base and image must both be exactly 8 MiB")
    if image[:pack.BOOT_END] != base[:pack.BOOT_END]:
        raise ValueError("bootloader changed")
    end = pack.AP_START + pack.AP_SIZE
    if image[end:] != base[end:]:
        raise ValueError("data outside CP/AP changed")
    if args.cp:
        verify_partition(image, args.cp, pack.CP_START, pack.CP_SIZE)
    elif image[pack.CP_START:pack.CP_START + pack.CP_SIZE] != base[pack.CP_START:pack.CP_START + pack.CP_SIZE]:
        raise ValueError("CP was not preserved")
    verify_partition(image, args.ap, pack.AP_START, pack.AP_SIZE)
    print("bootloader and all bytes outside CP/AP: unchanged")
    print(f"SHA256={hashlib.sha256(image).hexdigest()}")
    if args.update:
        update = args.update.read_bytes()
        if update != image[pack.BOOT_END:end]:
            raise ValueError("partial update does not match CP/AP range")
        print(f"update verified: start=0x{pack.BOOT_END:x} end=0x{end:x} bytes={len(update)} SHA256={hashlib.sha256(update).hexdigest()}")


if __name__ == "__main__":
    main()
