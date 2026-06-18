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
