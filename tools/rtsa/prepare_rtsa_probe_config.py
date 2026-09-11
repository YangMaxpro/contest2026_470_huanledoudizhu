#!/usr/bin/env python3
"""Generate an isolated probe config from the baseline without modifying it."""
import argparse
import pathlib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--baseline", type=pathlib.Path, required=True)
parser.add_argument("--output", type=pathlib.Path, required=True)
args = parser.parse_args()
overrides = {
    "CONFIG_NET_LOOPBACK": "y",
    "CONFIG_PTHREAD_MUTEX_TYPES": "y",
    "CONFIG_XIAOPAI_RTSA_PROBE": "y",
    "CONFIG_XIAOPAI_MIMO": "n",
    "CONFIG_XIAOPAI_VOICE": "n",
}
lines = []
for line in args.baseline.read_text().splitlines():
    key = line.removeprefix("# ").split("=", 1)[0].split(" ", 1)[0]
    if key not in overrides:
        lines.append(line)
lines.extend(key + "=" + value for key, value in overrides.items())
args.output.mkdir(parents=True, exist_ok=False)
(args.output / "defconfig").write_text("\n".join(lines) + "\n")
(args.output / "Make.defs").write_text("# Isolated CMake RTSA probe configuration.\n")
print(args.output)
