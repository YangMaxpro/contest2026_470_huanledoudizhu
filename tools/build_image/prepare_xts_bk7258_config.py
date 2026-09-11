#!/usr/bin/env python3
"""Generate an isolated BK7258 XTS core-test configuration."""
import argparse
import pathlib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--baseline", type=pathlib.Path, required=True)
parser.add_argument("--output", type=pathlib.Path, required=True)
args = parser.parse_args()

overrides = {
    "CONFIG_ALLOW_MIT_COMPONENTS": "y",
    "CONFIG_ARCH_SETJMP_H": "y",
    "CONFIG_BOARDCTL_RESET": "y",
    "CONFIG_BUILTIN": "y",
    "CONFIG_CM_MM_TEST": "y",
    "CONFIG_CM_SCHED_TEST": "y",
    "CONFIG_CM_SYSCALL_TEST": "y",
    "CONFIG_CXX_EXCEPTION": "y",
    "CONFIG_CXX_RTTI": "y",
    "CONFIG_EXAMPLES_HELLOXX": "y",
    "CONFIG_EXAMPLES_HELLO": "y",
    "CONFIG_EXAMPLES_PIPE": "y",
    "CONFIG_EXAMPLES_POPEN": "y",
    "CONFIG_FS_LINKS": "y",
    "CONFIG_FS_TEST": "y",
    "CONFIG_FS_TEST_EDONLY": "y",
    "CONFIG_FS_TMPFS": "y",
    "CONFIG_HAVE_CXX": "y",
    "CONFIG_LIBC_EXECFUNCS": "y",
    "CONFIG_LIBC_FLOATINGPOINT": "y",
    "CONFIG_LIBC_LONG_LONG": "y",
    "CONFIG_LIBC_REGEX": "y",
    "CONFIG_LIBC_SCANSET": "y",
    "CONFIG_LIBCXX": "y",
    "CONFIG_NET": "y",
    "CONFIG_NETDEV_LATEINIT": "y",
    "CONFIG_NET_ICMP": "y",
    "CONFIG_NET_LOCAL": "y",
    "CONFIG_NET_SOCKOPTS": "y",
    "CONFIG_NET_TCP": "y",
    "CONFIG_NET_UDP": "y",
    "CONFIG_NAME_MAX": "64",
    "CONFIG_NSH_BUILTIN_APPS": "y",
    "CONFIG_PIPES": "y",
    "CONFIG_PSEUDOFS_SOFTLINKS": "y",
    "CONFIG_SCHED_HAVE_PARENT": "y",
    "CONFIG_SCHED_LPWORK": "y",
    "CONFIG_SYSTEM_POPEN": "y",
    "CONFIG_TESTING_CMOCKA": "y",
    "CONFIG_TESTING_CXXTEST": "y",
    "CONFIG_TESTING_CXXTEST_EXCEPTION": "n",
    "CONFIG_TESTING_CXXTEST_STACKSIZE": "32768",
    "CONFIG_TESTING_FSTEST": "y",
    "CONFIG_TESTING_GETPRIME": "y",
    "CONFIG_TESTING_MM": "y",
    "CONFIG_TESTING_OSTEST": "y",
    "CONFIG_TESTING_RAMTEST": "y",
    "CONFIG_TESTING_SCANFTEST": "y",
    "CONFIG_TESTS_TESTCASES": "y",
    "CONFIG_TESTS_TESTSUITES": "y",
    "CONFIG_TESTS_TESTSUITES_STACKSIZE": "16384",
    "CONFIG_TLS_NELEM": "4",
    "CONFIG_TLS_TASK_NELEM": "4",
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
