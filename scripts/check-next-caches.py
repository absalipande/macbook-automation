#!/usr/bin/python3
"""Report Next.js cache disk usage; with --delete, remove flagged caches not in use by a Next.js process."""
import argparse
import json
import os
import re
import shutil
import subprocess
import time
import tempfile
from pathlib import Path

SKIP = {"node_modules", ".git", ".venv", "venv", "vendor", "Library"}
NEXT_COMMAND = re.compile(r"(^|[\s/])next(\s|-server|/dist|$)")

def next_processes():
    """Return (pid, command, cwd) for running Next.js processes, or None if they can't be listed."""
    try:
        ps = subprocess.run(["/bin/ps", "-Ao", "pid=,command="], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    commands = {}
    for line in ps.splitlines():
        pid, _, command = line.strip().partition(" ")
        if NEXT_COMMAND.search(command) and int(pid) != os.getpid():
            commands[pid] = command
    if not commands:
        return []
    try:
        # lsof exits 1 if a process vanished mid-scan; its output is still usable.
        out = subprocess.run(["/usr/sbin/lsof", "-a", "-d", "cwd", "-Fpn", "-p", ",".join(commands)], capture_output=True, text=True).stdout
    except OSError:
        return None
    cwds, pid = {}, None
    for line in out.splitlines():
        if line.startswith("p"):
            pid = line[1:]
        elif line.startswith("n") and pid:
            cwds[pid] = line[1:]
    if set(commands) - set(cwds):
        return None  # a Next.js process whose cwd is unknown could be using any cache
    return [(pid, commands[pid], cwds[pid]) for pid in commands]

def in_use_by(project, processes):
    for pid, command, cwd in processes:
        cwd = Path(cwd)
        if cwd == project or project in cwd.parents or cwd in project.parents or str(project) in command:
            return pid
    return None

def inspect(path):
    size, newest, errors = 0, 0, 0
    for base, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if not Path(base, d).is_symlink()]
        for name in files:
            try:
                item = Path(base, name)
                if item.is_symlink():
                    continue
                stat = item.stat()
                size += stat.st_size
                newest = max(newest, stat.st_mtime)
            except OSError:
                errors += 1
    if not newest:
        newest = path.stat().st_mtime
    return size, newest, errors

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", type=Path)
    parser.add_argument("--large-gb", type=float, default=5)
    parser.add_argument("--old-days", type=float, default=7)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--delete", action="store_true", help="delete flagged caches that no running Next.js process is using")
    parser.add_argument("--min-idle-minutes", type=float, default=60, help="never delete a cache modified more recently than this")
    args = parser.parse_args()
    home = Path.home()
    roots = args.root or [home / "Work", home / ".codex/worktrees", home / "veyra"]
    results, scan_errors, seen = [], [], set()
    now = time.time()
    def onerror(error):
        scan_errors.append(str(error))
    for root in roots:
        if not root.exists():
            continue
        for base, dirs, _ in os.walk(root, followlinks=False, onerror=onerror):
            if ".next" in dirs:
                next_dir = Path(base, ".next")
                if not next_dir.is_symlink():
                    for name in ("dev", "cache"):
                        target = next_dir / name
                        if not target.is_dir() or target.is_symlink():
                            continue
                        identity = str(target.resolve())
                        if identity in seen:
                            continue
                        seen.add(identity)
                        size, newest, errors = inspect(target)
                        age = (now - newest) / 86400
                        flags = []
                        if size >= args.large_gb * 1024**3:
                            flags.append("large")
                        if age >= args.old_days:
                            flags.append("old")
                        results.append(dict(path=identity, bytes=size, age_days=round(age, 2), flags=flags, read_errors=errors))
                dirs.remove(".next")
            dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".") and not Path(base, d).is_symlink()]
    results.sort(key=lambda row: row["bytes"], reverse=True)
    processes = next_processes() if args.delete else []
    for row in results:
        if not args.delete or not row["flags"]:
            continue
        project = Path(row["path"]).parent.parent
        pid = in_use_by(project, processes) if processes is not None else None
        if processes is None:
            row["action"] = "skipped: could not check for running Next.js processes"
        elif pid:
            row["action"] = f"skipped: in use by Next.js process {pid}"
        elif row["age_days"] * 1440 < args.min_idle_minutes:
            row["action"] = f"skipped: modified within {args.min_idle_minutes:g} minutes"
        else:
            try:
                shutil.rmtree(row["path"])
                row["action"] = "deleted"
            except OSError as error:
                row["action"] = f"delete failed: {error}"
    report = dict(checked_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"), roots=[str(r) for r in roots], large_gb=args.large_gb, old_days=args.old_days, delete=args.delete, caches=results, scan_errors=scan_errors)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=args.report.parent, prefix="next-cache-", suffix=".tmp", delete=False) as handle:
        handle.write(json.dumps(report, indent=2) + "\n")
        temporary = Path(handle.name)
    temporary.replace(args.report)
    print(f"Checked {len(results)} caches; {sum(bool(r['flags']) for r in results)} flagged; report: {args.report}")
    for row in results:
        print(f"{row['bytes'] / 1024**3:.2f} GiB | {row['age_days']:.1f} days | {','.join(row['flags']) or 'OK'} | {row['path']}" + (f" | {row['action']}" if "action" in row else ""))

if __name__ == "__main__":
    main()
