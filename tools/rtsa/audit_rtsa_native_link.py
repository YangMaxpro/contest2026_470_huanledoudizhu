#!/usr/bin/env python3
"""Link RTSA against built NuttX libraries in temporary output, never package/run.

Use only with a trusted existing build directory. The baseline ELF/map/config
are untouched, and successful linkage does not establish runtime compatibility.
"""
import argparse
import json
import pathlib
import shlex
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--build", type=pathlib.Path, required=True)
parser.add_argument("--object", type=pathlib.Path, required=True)
parser.add_argument("--report", type=pathlib.Path, help="Write generated JSON audit report")
args = parser.parse_args()
build = args.build.resolve()
obj = args.object.resolve()
if not obj.is_file():
    parser.error("Retained RTSA partial object not found")
commands = subprocess.check_output(["ninja", "-C", str(build), "-t", "commands", "nuttx"], text=True)
tokens = shlex.split(commands.splitlines()[-1])
if tokens[:2] != [":", "&&"] or tokens[-2:] != ["&&", ":"]:
    raise RuntimeError("Unexpected Ninja link command wrapper; inspect manually")
command = tokens[2:-2]
if any(token in (";", "&&", "||", "|", ">", "<") for token in command):
    raise RuntimeError("Refusing a composed shell command")
output = command.index("-o") + 1
if command[output] != "nuttx" or command.count("-Wl,-Map=nuttx.map") != 1:
    raise RuntimeError("Unexpected output paths; baseline will not be touched")
with tempfile.TemporaryDirectory(prefix="rtsa-native-link-") as tmp:
    root = pathlib.Path(tmp)
    command[output] = str(root / "audit.elf")
    command[command.index("-Wl,-Map=nuttx.map")] = "-Wl,-Map=" + str(root / "audit.map")
    command[1:1] = [str(obj), "-Wl,-u,agora_rtc_init", "-Wl,-u,agora_rtc_create_connection",
                    "-Wl,-u,agora_rtc_join_channel", "-Wl,-u,agora_rtc_leave_channel",
                    "-Wl,-u,agora_rtc_fini"]
    result = subprocess.run(command, cwd=build, capture_output=True, text=True)
    report = {"native_link_exit": result.returncode,
                      "diagnostics": (result.stdout + result.stderr)[-16000:],
                      "baseline_unchanged": True, "firmware_ready": False,
                      "note": "Temporary link only. No execution, image packaging or board validation."}
    if result.returncode == 0:
        size_tool = command[0].removesuffix("gcc") + "size"
        report["size"] = subprocess.check_output([size_tool, str(root / "audit.elf")], text=True)
    encoded = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.write_text(encoded)
    print(encoded)
    raise SystemExit(0 if result.returncode == 0 else 1)
