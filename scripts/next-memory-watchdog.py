#!/usr/bin/python3
"""Warn when a Next.js dev server uses too much memory; stop it past a hard limit."""
import argparse
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path

NEXT_DEV = re.compile(r"(^|[\s/])next\s+dev(\s|$)")
UNITS = {"B": 1 / 1024**2, "K": 1 / 1024, "M": 1, "G": 1024, "T": 1024**2}

def run(args):
    return subprocess.run(args, capture_output=True, text=True).stdout

def processes():
    procs = {}
    for line in run(["/bin/ps", "-Ao", "pid=,ppid=,rss=,command="]).splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            pid, ppid, rss, command = parts
            procs[int(pid)] = dict(ppid=int(ppid), mb=int(rss) / 1024, command=command)
    return procs

def footprints():
    """Memory per pid as Activity Monitor counts it (includes compressed memory), in MB."""
    sizes = {}
    for line in run(["/usr/bin/top", "-l", "1", "-stats", "pid,mem"]).splitlines():
        match = re.fullmatch(r"\s*(\d+)\s+([\d.]+)([BKMGT])\+?-?\s*", line)
        if match:
            sizes[int(match[1])] = float(match[2]) * UNITS[match[3]]
    return sizes

def descendants(root, procs):
    tree, frontier = {root}, [root]
    while frontier:
        parent = frontier.pop()
        children = [pid for pid, p in procs.items() if p["ppid"] == parent and pid not in tree]
        tree.update(children)
        frontier.extend(children)
    return tree

def cwd(pid):
    out = run(["/usr/sbin/lsof", "-a", "-d", "cwd", "-Fn", "-p", str(pid)])
    return next((line[1:] for line in out.splitlines() if line.startswith("n")), "?")

def notify(title, message):
    script = f"display notification {json.dumps(message)} with title {json.dumps(title)} sound name \"Funk\""
    subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warn-gb", type=float, default=6)
    parser.add_argument("--stop-gb", type=float, default=9, help="0 disables stopping")
    parser.add_argument("--renotify-minutes", type=float, default=30)
    parser.add_argument("--state", type=Path, default=Path.home() / "Library/Logs/next-memory-watchdog/state.json")
    args = parser.parse_args()

    procs = processes()
    sizes = footprints()
    roots = [pid for pid, p in procs.items()
             if NEXT_DEV.search(p["command"]) and not NEXT_DEV.search(procs.get(p["ppid"], {}).get("command", ""))]
    try:
        state = json.loads(args.state.read_text())
    except (OSError, ValueError):
        state = {}
    now = time.time()
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    new_state = {}
    for root in roots:
        tree = descendants(root, procs)
        gb = sum(sizes.get(pid, procs[pid]["mb"]) for pid in tree) / 1024
        project = Path(cwd(root)).name
        if args.stop_gb and gb >= args.stop_gb:
            for pid in sorted(tree, reverse=True):
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            notify("Dev server stopped", f"{project} dev server hit {gb:.1f} GB (limit {args.stop_gb:g} GB). Run npm run dev again.")
            print(f"{stamp} STOPPED {project} pid {root}: {gb:.2f} GB")
        elif gb >= args.warn_gb:
            last = state.get(str(root), 0)
            if now - last >= args.renotify_minutes * 60:
                notify("Dev server using a lot of memory", f"{project} dev server is at {gb:.1f} GB. Restart it soon (auto-stop at {args.stop_gb:g} GB).")
                print(f"{stamp} WARNED {project} pid {root}: {gb:.2f} GB")
                last = now
            new_state[str(root)] = last
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps(new_state))

if __name__ == "__main__":
    main()
