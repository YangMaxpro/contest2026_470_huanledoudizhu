#!/usr/bin/env python3
"""Compile shims and partially link private SDK imports, without modifying SDKs.

This is an ABI/link audit, NOT an executable firmware or an RTC smoke test.
"""
import argparse
import json
import pathlib
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--libs", type=pathlib.Path, required=True)
parser.add_argument("--port", type=pathlib.Path, required=True)
parser.add_argument("--nuttx", type=pathlib.Path, required=True)
parser.add_argument("--build", type=pathlib.Path, required=True)
parser.add_argument("--tool-prefix", required=True)
parser.add_argument("--object", type=pathlib.Path, help="Retain the partial object for isolated native-link auditing")
parser.add_argument("--report", type=pathlib.Path, help="Write generated JSON audit report")
parser.add_argument("--replace-object", action="store_true", help="Allow build-system replacement of its generated object")
args = parser.parse_args()


def run(tool, *params):
    return subprocess.check_output([args.tool_prefix + tool, *map(str, params)], text=True)


def symbols(path, defined):
    flags = ["-g", "--defined-only"] if defined else ["-u"]
    return {line.split()[-1] for line in run("nm", *flags, path).splitlines() if line.split()}


with tempfile.TemporaryDirectory(prefix="rtsa-port-link-") as tmp:
    root = pathlib.Path(tmp)
    objects = []
    exports = set()
    for name in ("rtsa_sync", "rtsa_net", "rtsa_runtime", "rtsa_memory", "rtsa_hal_thread",
                 "rtsa_libc", "rtsa_loopback", "rtsa_tree"):
        obj = root / (name + ".o")
        run("gcc", "-c", "-mcpu=cortex-m33", "-mthumb", "-mfpu=fpv5-sp-d16",
            "-mfloat-abi=hard", "-D__NuttX__", "-Wall", "-Wextra", "-Werror",
            "-I"+str(args.build / "include"), "-I"+str(args.nuttx / "include"),
            "-I"+str(args.nuttx / "net"),
            args.port / (name + ".c"), "-o", obj)
        objects.append(obj)
        exports.update(symbols(obj, True))
    vendor = root / "vendor.o"
    libraries = [args.libs / name for name in ("librtsa.a", "libahpl.a", "libagora-cjson.a")]
    run("ld", "-r", "--whole-archive", *libraries, "--no-whole-archive", "-o", vendor)
    imports = symbols(vendor, False)
    rename = {}
    for symbol in imports:
        target = "rtsa_errno" if symbol == "__errno" else "rtsa_" + symbol
        if target in exports:
            rename[symbol] = target
    # Mapping is derived from actual exports, not blanket global interposition.
    # Retain vendor code for auditing but let the strong replacement resolve
    # k_thread_create's relocation. Do not weaken or wrap native OS symbols.
    if "k_os_thread_create" not in symbols(vendor, True):
        raise RuntimeError("Audited vendor thread HAL symbol missing")
    replacements = ["k_os_thread_create", "ahpl_rb_traverse_ldr", "k_lock_lock",
                    "k_rwlock_wrlock"]
    if not set(replacements) <= symbols(vendor, True):
        raise RuntimeError("Audited vendor replacement symbol missing")
    params = ["--weaken-symbol=" + name for name in replacements]
    for original, replacement in sorted(rename.items()):
        params.extend(["--redefine-sym", original + "=" + replacement])
    patched = root / "vendor-private.o"
    run("objcopy", *params, vendor, patched)
    combined = root / "combined.o"
    run("ld", "-r", patched, *objects, "-o", combined)
    remaining = symbols(combined, False)
    table = run("nm", "-g", "--defined-only", combined)
    for name in replacements:
        if not any(line.split()[1:] == ["T", name] for line in table.splitlines()):
            raise RuntimeError("Strong replacement did not link: " + name)
    vendor_remaining = sorted(s for s in remaining if s in imports and s not in rename)
    if args.object:
        if args.object.exists() and not args.replace_object:
            raise RuntimeError("Refusing to overwrite retained object")
        shutil.copyfile(combined, args.object)
    report = {"renamed_imports": rename,
                      "replaced_vendor_definitions": replacements,
                      "remaining_original_imports": vendor_remaining,
                      "all_unresolved": sorted(remaining),
                      "firmware_ready": False,
                      "note": "Partial link only; native libc/OS dependencies require executable-link validation"}
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.write_text(encoded)
    print(encoded)
