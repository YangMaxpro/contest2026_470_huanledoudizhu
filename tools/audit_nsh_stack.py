#!/usr/bin/env python3
"""Recompile selected units in a temporary directory for GCC stack reports."""
import json
import pathlib
import shlex
import subprocess
import sys
import tempfile


def main():
    entries = json.loads(pathlib.Path(sys.argv[1]).read_text())
    selected = ('/nshlib/', '/system/nsh/', '/fs/procfs/', '/libc/stdio/',
                '/libc/stream/', '/fs/vfs/fs_read', '/sched/task/task_argvstr.c',
                '/sched/sched/sched_get_stateinfo.c')
    with tempfile.TemporaryDirectory(prefix='nsh-stack-audit-') as tmp:
        root = pathlib.Path(tmp)
        for index, entry in enumerate(entries):
            if not any(part in entry['file'] for part in selected):
                continue
            args = entry.get('arguments') or shlex.split(entry['command'])
            clean = []
            skip = False
            for arg in args:
                if skip:
                    skip = False
                elif arg in ('-o', '-MF', '-MT', '-MQ'):
                    skip = True
                elif arg not in ('-MD', '-MMD', '-MP'):
                    clean.append(arg)
            clean += ['-fstack-usage', '-o', str(root / f'{index}.o')]
            subprocess.run(clean, cwd=entry['directory'], check=True,
                           stdout=subprocess.DEVNULL)
        records = []
        for report in root.glob('*.su'):
            for line in report.read_text().splitlines():
                location, size, kind = line.split('\t')
                records.append((int(size), location, kind))
        for size, location, kind in sorted(records, reverse=True):
            print(f'{size:5} {kind:16} {location}')


if __name__ == '__main__':
    main()
