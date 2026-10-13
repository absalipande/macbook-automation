# macOS Caps Lock Delay Remover

Automatically removes the built-in macOS Caps Lock delay at login.

macOS can reset this setting after shutdown or restart. This LaunchAgent runs the following command whenever you log in:

```sh
hidutil property --set '{"CapsLockDelayOverride":0}'
```

## Install

Clone this repository, then run:

```sh
cp com.local.set-capslock-delay.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.local.set-capslock-delay.plist
launchctl kickstart -k gui/$(id -u)/com.local.set-capslock-delay
```

The setting will now be applied automatically each time you log in.

## Verify

Check that the LaunchAgent is installed:

```sh
launchctl print gui/$(id -u)/com.local.set-capslock-delay
```

You can also check the latest command output:

```sh
cat /tmp/com.local.set-capslock-delay.out
```

Expected output:

```text
CapsLockDelayOverride:0
```

## Uninstall

```sh
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.local.set-capslock-delay.plist
rm ~/Library/LaunchAgents/com.local.set-capslock-delay.plist
```

## Notes

- This only affects the current macOS user.
- No background process keeps running. The LaunchAgent runs once at login and exits.
- The setting may need to be applied again after shutdown or restart, which is why this LaunchAgent exists.

## Next.js cache checker

`com.local.check-next-caches.plist` runs a cache scan at login and every 24
hours while logged in. It scans `~/Work`, `~/.codex/worktrees`, and `~/veyra`,
skipping dependencies, Git metadata, and symlinks. It reports `.next/dev` and
`.next/cache` sizes, and flags directories at least 5 GiB or whose newest file
modification is at least 7 days old.

The LaunchAgent passes `--delete`, which removes a flagged `.next/dev` or
`.next/cache` directory only when both are true:

- No running Next.js process (`next dev`, `next build`, `next-server`, ...) has
  its working directory in, above, or below that project, or names the project
  in its command line. If processes can't be listed, nothing is deleted.
- Nothing in the cache was modified in the last 60 minutes
  (`--min-idle-minutes`).

Skipped caches stay in the report with the reason. Deleted caches are rebuilt
by Next.js on the next `npm run dev` or `npm run build`, which is slower the
first time. The checker never stops Node processes and does not free RAM held
by a running dev server; restart the dev server for that. Without `--delete`
the script only reports.

macOS privacy protection (TCC) blocks LaunchAgents from reading `~/Documents`,
`~/Desktop`, and `~/Downloads` without Full Disk Access. So the scheduled job
runs an installed copy from `~/.local/bin`, writes to
`~/Library/Logs/check-next-caches`, and does not scan `~/Documents` by default.

Run manually:

```sh
/usr/bin/python3 scripts/check-next-caches.py --report ~/Library/Logs/check-next-caches/report.json
# add --delete to also remove flagged caches that are not in use
```

Override scan roots or thresholds with repeated `--root /absolute/path`,
`--large-gb 5`, and `--old-days 7`. Results are in
`~/Library/Logs/check-next-caches/report.json`, with scheduled output in
`checker.log` and errors in `checker.err` in the same folder.
Review `scan_errors` and `read_errors` for inaccessible files.

Install (the plist contains absolute paths for this user; update them if your
home directory differs):

```sh
mkdir -p ~/.local/bin ~/Library/Logs/check-next-caches ~/Library/LaunchAgents
cp scripts/check-next-caches.py ~/.local/bin/
cp com.local.check-next-caches.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.local.check-next-caches.plist
```

After editing the script, copy it to `~/.local/bin` again. Verify with
`launchctl print gui/$(id -u)/com.local.check-next-caches` (look for
`last exit code = 0`). To uninstall:

```sh
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.local.check-next-caches.plist
rm ~/Library/LaunchAgents/com.local.check-next-caches.plist ~/.local/bin/check-next-caches.py
```

## Next.js dev server memory watchdog

`com.local.next-memory-watchdog.plist` checks every 3 minutes how much memory
each running `next dev` process tree uses (as Activity Monitor counts it,
including compressed memory). At 6 GB it shows a macOS notification, repeated
at most every 30 minutes. At 9 GB it stops that dev server (SIGTERM to the
`next dev` process and its children) and notifies you; run `npm run dev` again.
Pass `--stop-gb 0` to only warn. Actions are logged to
`~/Library/Logs/next-memory-watchdog/watchdog.log`.

Install:

```sh
mkdir -p ~/.local/bin ~/Library/Logs/next-memory-watchdog ~/Library/LaunchAgents
cp scripts/next-memory-watchdog.py ~/.local/bin/
cp com.local.next-memory-watchdog.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.local.next-memory-watchdog.plist
```

To uninstall:

```sh
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.local.next-memory-watchdog.plist
rm ~/Library/LaunchAgents/com.local.next-memory-watchdog.plist ~/.local/bin/next-memory-watchdog.py
```
