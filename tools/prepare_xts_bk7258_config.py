#!/usr/bin/env python3
"""Generate an isolated BK7258 XTS core-test configuration."""
import argparse
import pathlib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--baseline", type=pathlib.Path, required=True)
parser.add_argument("--output", type=pathlib.Path, required=True)
args = parser.parse_args()

overrides = {
    "CONFIG_ARCH_SETJMP_H": "y",
    "CONFIG_BUILTIN": "y",
    "CONFIG_CM_MM_TEST": "y",
    "CONFIG_CM_SCHED_TEST": "y",
    "CONFIG_CM_SYSCALL_TEST": "y",
    "CONFIG_EXAMPLES_HELLO": "y",
    "CONFIG_FS_LINKS": "y",
    "CONFIG_FS_TMPFS": "y",
    "CONFIG_LIBC_EXECFUNCS": "y",
    "CONFIG_LIBC_FLOATINGPOINT": "y",
    "CONFIG_LIBC_LONG_LONG": "y",
    "CONFIG_LIBC_REGEX": "y",
    "CONFIG_LIBC_SCANSET": "y",
    "CONFIG_NET": "y",
    "CONFIG_NETDEV_LATEINIT": "y",
    "CONFIG_NET_ICMP": "y",
    "CONFIG_NET_LOCAL": "y",
    "CONFIG_NET_SOCKOPTS": "y",
    "CONFIG_NET_TCP": "y",
    "CONFIG_NET_UDP": "y",
    "CONFIG_NSH_BUILTIN_APPS": "y",
    "CONFIG_PIPES": "y",
    "CONFIG_PSEUDOFS_SOFTLINKS": "y",
    "CONFIG_SCHED_HAVE_PARENT": "y",
    "CONFIG_SCHED_LPWORK": "y",
    "CONFIG_TESTING_CMOCKA": "y",
    "CONFIG_TESTING_GETPRIME": "y",
    "CONFIG_TESTING_MM": "y",
    "CONFIG_TESTING_OSTEST": "y",
    "CONFIG_TESTING_SCANFTEST": "y",
    "CONFIG_TESTS_TESTSUITES": "y",
    "CONFIG_TESTS_TESTSUITES_STACKSIZE": "16384",
    "CONFIG_XIAOPAI_MIMO": "n",
    "CONFIG_XIAOPAI_RTSA_PROBE": "n",
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
(args.output / "Make.defs").write_text("# Isolated BK7258 XTS core-test configuration.\n")
print(args.output)
