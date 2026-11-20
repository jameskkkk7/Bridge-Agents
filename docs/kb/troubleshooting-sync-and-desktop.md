# Troubleshooting desktop sync

Widget Pro keeps a local copy of boards so it can work offline, then syncs
changes when a connection is available. Most sync complaints fall into a small
number of categories.

## The app says "offline" but the network is fine

1. Open **Settings → Sync status** and check the last successful sync time.
2. Confirm the workspace is active and the signed-in account still has access;
   revoked members and expired licences cannot sync.
3. Check the firewall and proxy allow-list. The desktop app needs HTTPS access
   to `sync.widget.example` and the licence service; TLS inspection proxies must
   trust the Widget certificate chain.
4. If the app cannot reach the licence service, it keeps working offline only
   for the remaining cached licence period (up to 30 days after the last
   successful check). Sign out and back in once connectivity returns.

## Boards are stuck on "Syncing" or show old content

- Retry from the sync status panel before reinstalling.
- Restart the app; a background sync can continue without showing progress.
- Confirm the local clock is correct. A clock more than five minutes off makes
  licence and sync requests fail validation.
- Clear the local cache from **Settings → Advanced → Reset cache**. This removes
  local copies and downloads fresh data. Unsynchronised local edits are listed
  before confirming; export them first if they matter.

## Edits made offline conflict with server changes

If the same board was edited on another device while offline, the app keeps the
local version as a copy named "Conflicted copy" instead of overwriting content.
Review the copy, copy anything useful into the current board, then delete the
conflicted copy. There is no automatic merge for board layout changes.

## Installer and update problems

- **Signature error:** clear the download cache and fetch the installer again
  from the portal. Do not bypass operating-system signature checks.
- **Windows requires a restart:** complete the restart; the sync service may not
  start correctly before it.
- **macOS blocks the app:** use Open from the context menu the first time, or
  allow the app in **System Settings → Privacy & Security**.
- **Linux AppImage does not launch:** make the downloaded file executable
  (`chmod +x`) and ensure FUSE is available on the distribution.
- **Auto-update fails behind a proxy:** configure the system proxy; the updater
  inherits it. Manual installers are always available from the portal.

## Logs and escalation

Desktop logs are under the app data directory: `%APPDATA%\Widget Pro\logs` on
Windows, `~/Library/Logs/Widget Pro` on macOS and `~/.config/widget-pro/logs` on
Linux. Attach the most recent log file, the app version and the local clock time
to a support request. Avoid pasting full logs publicly; they can contain board
names and account identifiers.

## System requirements

Windows 10 or newer, macOS 12 or newer, or a recent 64-bit Linux desktop; 4 GB
of memory and 500 MB of free disk space; a Widget Cloud account on Standard or
higher. Older operating systems are not supported.
