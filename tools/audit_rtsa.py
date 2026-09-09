#!/usr/bin/env python3
"""Read-only vendor archive audit; never links libraries into board firmware."""
import argparse
import hashlib
import json
import pathlib
import subprocess
import tempfile


def inspect(libs, prefix):
    archives = [libs / name for name in
                ("librtsa.a", "libahpl.a", "libagora-cjson.a")]
    for archive in archives:
        if not archive.is_file():
            raise FileNotFoundError(archive)

    def run(tool, *args):
        return subprocess.check_output([prefix + tool, *map(str, args)], text=True)

    with tempfile.TemporaryDirectory(prefix="rtsa-audit-") as tmp:
        combined = pathlib.Path(tmp) / "combined.o"
        run("ld", "-r", "--whole-archive", *archives,
            "--no-whole-archive", "-o", combined)
        unresolved = sorted({line.split()[-1] for line in
                             run("nm", "-u", combined).splitlines()
                             if line.split()})
        attributes = run("readelf", "-A", combined)
    groups = {
        "network": [s for s in unresolved if s.startswith("lwip_") or
                    s in ("bk_netif_trigger_loopnetif_msg", "ipaddr_addr")],
        "thread_and_sync": [s for s in unresolved if s.startswith(
            ("pthread_", "rtos_", "xTask", "agora_create_thread"))],
        "memory": [s for s in unresolved if s in
                   ("psram_malloc_debug", "os_free_debug", "realloc")],
    }
    return {
        "archives": {a.name: hashlib.sha256(a.read_bytes()).hexdigest()
                     for a in archives},
        "elf_attributes": attributes,
        "external_symbols": unresolved,
        "porting_groups": groups,
        "runtime_compatible": "NOT VERIFIED",
        "required_checks": [
            "pthread mutex/condition/attribute storage, constants and lifetime",
            "sockaddr, addrinfo, fd_set, socket option and errno translation",
            "enum width, float calling convention and time structure layout",
            "allocation/free/realloc share the same owning heap",
            "FreeRTOS task identity, priority and deletion semantics",
            "full-duplex audio and AEC reference synchronization",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("libraries", type=pathlib.Path)
    parser.add_argument("--tool-prefix", default="arm-none-eabi-")
    args = parser.parse_args()
    print(json.dumps(inspect(args.libraries, args.tool_prefix), indent=2))
