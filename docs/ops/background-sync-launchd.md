# Background Sync (launchd) + Presets

This repo includes two sync presets for safe day/night operation:

- `fast-daytime` — lower latency, bounded resume runs.
- `overnight-safe` — slower, safer full refresh (`--force-refetch`) with adaptive throttling.

## Preset runner

```bash
# Optional preflight migration check
xdocs migrate-schema --docs-dir ./cex-docs

# Fast daytime refresh (resume mode)
scripts/run_sync_preset.sh fast-daytime ./cex-docs

# Overnight safe full refresh
scripts/run_sync_preset.sh overnight-safe ./cex-docs
```

You can pass normal `sync` flags after the preset arguments:

```bash
scripts/run_sync_preset.sh fast-daytime ./cex-docs --exchange binance --section spot
```

## launchd sample

Sample plist:

- `ops/launchd/com.cexapidocs.sync.overnight.plist`

Install:

```bash
mkdir -p ~/Library/LaunchAgents
cp ops/launchd/com.cexapidocs.sync.overnight.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.cexapidocs.sync.overnight.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.cexapidocs.sync.overnight.plist
```

Verify:

```bash
launchctl list | rg cexapidocs
tail -f logs/launchd-sync.log
```

## Notes

- Edit the absolute repo path inside the plist command before loading it.
- launchd jobs run independently, so you can keep working while sync runs.
- Adaptive delay and Retry-After support are enabled by default in both presets.
