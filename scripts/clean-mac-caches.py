#!/usr/bin/python3
"""Report reclaimable temp and cache space; with --delete, remove what is old or oversized."""
import argparse
import json
import os
import shutil
import subprocess
import stat as statmod
import time
from pathlib import Path

HOME = Path.home()
# Tool caches are cleaned by the tools themselves below, not by age.
# ms-playwright holds the browsers veyra's e2e tests need.
CACHES_SKIP = {"pnpm", "go-build", "Homebrew", "ms-playwright"}
PATH = os.pathsep.join(["/usr/local/bin", "/opt/homebrew/bin", str(HOME / "sdk/go1.26.3/bin"), "/usr/bin", "/bin"])

def size_of(path):
    total = 0
    for base, dirs, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                total += Path(base, name).lstat().st_size
            except OSError:
                pass
    return total

def newest_mtime(path):
    newest = path.lstat().st_mtime
    for base, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            try:
                newest = max(newest, Path(base, name).lstat().st_mtime)
            except OSError:
                pass
    return newest

def stat_is_socket(mode):
    return statmod.S_ISSOCK(mode)

def clean_tmpdir(tmp, cutoff, delete):
    """Files neither modified nor read since cutoff, then the directories they leave empty."""
    freed, errors = 0, 0
    for base, dirs, files in os.walk(tmp, topdown=False, followlinks=False):
        for name in files:
            item = Path(base, name)
            try:
                stat = item.lstat()
                if stat.st_mtime < cutoff and stat.st_atime < cutoff and not stat_is_socket(stat.st_mode):
                    if delete:
                        item.unlink()
                    freed += stat.st_size
            except OSError:
                errors += 1
        if delete and Path(base) != tmp:
            try:
                if Path(base).lstat().st_mtime < cutoff:
                    Path(base).rmdir()  # only succeeds when empty
            except OSError:
                pass
    return freed, errors

def clean_caches(caches, cutoff, min_mb, delete):
    """Whole app cache folders nothing has touched since cutoff. Running apps keep theirs fresh.

    Folders under min_mb are left alone: many belong to macOS daemons without a com.apple. prefix,
    and together they hold too little to be worth disturbing them."""
    freed, removed, errors = 0, [], 0
    for entry in sorted(caches.iterdir()):
        if entry.name in CACHES_SKIP or entry.name.startswith("com.apple.") or entry.is_symlink():
            continue
        try:
            if newest_mtime(entry) >= cutoff:
                continue
            size = size_of(entry)
            if size < min_mb * 1024**2:
                continue
            if delete:
                shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
            freed += size
            removed.append(entry.name)
        except OSError:
            errors += 1
    return freed, removed, errors

def run_tools(npm_max_gb, delete):
    env = dict(os.environ, PATH=PATH)
    npm_cache = HOME / ".npm/_cacache"
    npm_gb = size_of(npm_cache) / 1024**3 if npm_cache.exists() else 0
    commands = [["brew", "cleanup", "--prune=7"], ["pnpm", "store", "prune"], ["go", "clean", "-cache"]]
    if npm_gb >= npm_max_gb:
        commands.append(["npm", "cache", "clean", "--force"])
    results = []
    for command in commands:
        if not shutil.which(command[0], path=PATH):
            results.append(dict(command=" ".join(command), status="not installed"))
            continue
        if not delete:
            results.append(dict(command=" ".join(command), status="would run"))
            continue
        done = subprocess.run(command, capture_output=True, text=True, env=env)
        results.append(dict(command=" ".join(command), status="ok" if done.returncode == 0 else f"exit {done.returncode}",
                            stderr=done.stderr.strip()[-500:]))
    return npm_gb, results

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete", action="store_true", help="actually delete; without it, only report")
    parser.add_argument("--old-days", type=float, default=7)
    parser.add_argument("--min-cache-mb", type=float, default=50, help="skip Library/Caches folders smaller than this")
    parser.add_argument("--npm-max-gb", type=float, default=3, help="clear the npm cache at or above this size")
    parser.add_argument("--report", type=Path, default=HOME / "Library/Logs/clean-mac-caches/report.json")
    args = parser.parse_args()

    cutoff = time.time() - args.old_days * 86400
    tmp = Path(os.environ.get("TMPDIR") or subprocess.run(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], capture_output=True, text=True).stdout.strip())
    tmp_freed, tmp_errors = clean_tmpdir(tmp, cutoff, args.delete)
    cache_freed, cache_removed, cache_errors = clean_caches(HOME / "Library/Caches", cutoff, args.min_cache_mb, args.delete)
    npm_gb, tools = run_tools(args.npm_max_gb, args.delete)

    verb = "freed" if args.delete else "reclaimable"
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {'DELETE' if args.delete else 'REPORT'}")
    print(f"  TMPDIR: {tmp_freed / 1024**3:.2f} GB {verb} ({tmp_errors} unreadable)")
    print(f"  Library/Caches: {cache_freed / 1024**3:.2f} GB {verb} from {len(cache_removed)} folders ({cache_errors} errors)")
    print(f"  npm cache: {npm_gb:.2f} GB (cleared at {args.npm_max_gb:g} GB)")
    for tool in tools:
        print(f"  {tool['command']}: {tool['status']}")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(dict(checked_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"), delete=args.delete, old_days=args.old_days,
                                           tmpdir=str(tmp), tmp_bytes=tmp_freed, caches_bytes=cache_freed, caches_removed=cache_removed,
                                           npm_cache_gb=round(npm_gb, 2), tools=tools), indent=2))

if __name__ == "__main__":
    main()
