# Changelog

All notable changes to this project will be documented in this file.

## [1.3.1] - 2026-06-28

### Changed
- **LQI color bands recalibrated for TI Z-Stack.** The coordinator (a TI CC2652) computes LQI on a compressed scale that rarely exceeds ~110, so the generic 150/100/50 bands left most devices stuck in "fair" amber with the "excellent" green band unreachable. New bands — validated against the live network's full device-LQI distribution (range 18–105, mean 73, max 105) — are: **90+ excellent, 65+ good, 45+ fair, <45 weak**. Applies to the device badge, link colors, link thickness, and the legend. (Note: device LQI is measured by the coordinator, so this scaling applies to every device regardless of make.)

## [1.3.0] - 2026-06-28

### Added
- **"Rescan this router" button** in the device detail card (routers/coordinator only). It actively rescans just that one device via zha-toolkit (fast), then reloads with fresh routes/neighbour LQIs for it — no full network scan needed. Backed by a new `/rescan` endpoint.

### Changed
- **Clicking empty space now closes the detail card** (in addition to clearing the selection).

## [1.2.0] - 2026-06-28

### Added
- **Live refresh progress.** The Refresh button and the loading page now show real progress (e.g. "Scanning Front Door (12/23)" → "Fetching device data…" → "Building visualization…"), polled from a new `progress` field on `/status`.

### Changed
- **Per-router active scan.** Instead of one bulk `all_routes_and_neighbours` call (all-or-nothing, which timed out on larger networks and discarded everything), the scan now queries each router individually via `get_routes_and_neighbours`. Benefits: real "X of N" progress, and a single slow/dead router just times out and is skipped (30s each, capped by `zha_toolkit_timeout`) instead of failing the whole scan — so routers that respond still get fresh LQIs.

## [1.1.3] - 2026-06-28

### Fixed
- **Version/UI now updates immediately after an add-on update.** 1.1.2's per-request page cache had a side effect: after updating the add-on, the old `topology.html` (from the previous version) survived in `/data` and kept being served, so the header showed the old version until a manual refresh. The visualization is now always regenerated on startup, so a new version applies on the first load. (Workaround on older builds: click "Regenerate UI" or "Refresh Data".)

## [1.1.2] - 2026-06-28

### Changed
- **Node details are now a pinned corner card** instead of a tooltip that follows the cursor — it sits fixed in the top-right (a bottom card on phones), scrolls if long, and **can no longer be clipped off-screen**. It updates on hover and on tap (so it finally works on touch devices), with a close button.
- **Raised the active-scan timeout default** (`zha_toolkit_timeout`) from 180s to 300s, since larger networks (20+ routers) were timing out and silently falling back to cached link data. Raise toward 600 if scans still time out.

## [1.1.1] - 2026-06-28

### Fixed
- **Page no longer hangs on load.** The web server is now multi-threaded (`ThreadingHTTPServer`), so a slow refresh/scan or page render no longer blocks other requests (status polls, health checks, other tabs).
- **No more full rebuild on every page load.** `topology.html` is now regenerated only when the underlying export actually changes (mtime check); ordinary loads serve the cached file instantly.
- **Atomic file writes.** `topology.html` and `positions.json` are written via a temp file + rename under a lock, so a page load can never read a half-written file (the intermittent "stuck loading, fixed by reload" bug).

## [1.1.0] - 2026-06-27

### Added
- **Active scan via zha-toolkit** (`use_zha_toolkit`, on by default): each refresh now queries every router for its live route + neighbour tables (Mgmt_Rtg_req / Mgmt_Lqi_req), so link LQIs are fresh and populated instead of the coordinator's stale cached snapshot. Falls back to cached data if zha-toolkit is absent or the scan fails.
- `zha_toolkit_timeout` option (default 180s) for the active scan.
- Network-health summary in the header (weak / offline / unknown-attachment counts) plus the Zigbee channel.
- Power source (mains/battery) and online/offline status surfaced in the device tooltip.
- Distinct **"not reported"** rendering for unknown LQIs (neutral grey), separate from a measured-weak link.

### Changed
- **Truthfulness overhaul:** the map now distinguishes *confirmed* (route/parent) from *estimated* (best-guess) and *unknown* (fallback) connections — guessed router parents are dashed like end-device guesses, and "Unknown" links are dashed/faint instead of solid lines to the coordinator.
- Legend regrouped into Device / Signal / Connection, with an explicit note that the LQI badge is the last hop to the coordinator.
- Bidirectional link LQI now shows two genuinely independent directional measurements (`?` when a direction wasn't reported) instead of repeating one value.
- Tooltip "Depth" relabelled "Hops (est.)"; "Data as of" relabelled "Data fetched".
- Refresh button now performs the active re-measure; UI poll window extended to 5 minutes.

### Fixed
- **Route-based parent inference** was silently broken for multi-hop devices (NWK lookup keyed by hex string but queried by int); the authoritative route parent is now resolved correctly.
- **Timezone bug:** export timestamp is now UTC-aware, so staleness/age/last-seen math is no longer off by the browser's UTC offset.
- "Open in Home Assistant" device link now resolves (device registry id is populated from the registry).

### Removed
- Dead `topology_scan_wait` option (ignored since 1.0.21) and the unused `share:rw` mapping.
- Dead code: the unused tree builder in `build_hierarchy`, the always-null `rssi` field, and the unused/incorrect neighbour-`depth` field.

## [1.0.33] - 2024-12-24

### Added
- "Oldest seen" indicator in header showing when the oldest device was last seen by ZHA
- Color-coded freshness: green (<6h), yellow (6-24h), red (>24h)
- Helps identify stale neighbor data that may need a topology scan refresh

## [1.0.32] - 2024-12-24

### Fixed
- Refresh button now properly waits for data refresh to complete before reloading
- Added polling mechanism to track refresh progress (shows elapsed seconds)
- Better error logging for WebSocket connection failures
- Errors during refresh are now properly displayed to user

### Changed
- Refresh button shows progress countdown while waiting for data

## [1.0.30] - 2024-12-24

### Added
- Feet-based coordinate system (72 SVG units = 1 foot)
- Toggleable 10ft grid overlay for visual positioning reference
- Server-side position storage (positions persist across browser cache clears)
- Position display in device tooltip (shows feet coordinates when floorplan active)

### Changed
- Node positions now saved to server (/data/positions.json) instead of browser localStorage
- Positions auto-save with debounce (500ms after last drag) for better performance
- Position coordinates stored in feet for consistent placement across screen sizes

### Removed
- localStorage-based position storage (replaced by server-side storage)

## [1.0.28] - 2024-12-24

### Changed
- Floorplan SVG now uses fixed 1:1 scale with graph coordinates
- Floorplan and nodes maintain consistent relative sizes when zooming

## [1.0.27] - 2024-12-24

### Fixed
- Floorplan SVG now visible (removed dark background when floorplan active)
- Increased floorplan opacity from 0.3 to 0.8

### Added
- Bundled floorplan CSS for proper SVG styling

## [1.0.26] - 2024-12-24

### Changed
- Floorplan SVG now bundled directly in add-on (no longer requires external file)
- Removed `floorplan_svg` configuration option
- Removed `config:ro` mapping (no longer needed)

## [1.0.25] - 2024-12-24

### Fixed
- Floorplan path now uses correct `/config/www/` mount point (from `config:ro` mapping)
- Previously was incorrectly using `/homeassistant_config/www/`

## [1.0.24] - 2024-12-24

### Added
- Extensive debug logging for floorplan loading to diagnose mount issues
- Log shows whether /homeassistant_config mount exists and its contents

## [1.0.23] - 2024-12-24

### Fixed
- Use correct `homeassistant_config` mapping type per HA add-on documentation
- Floorplan path now correctly maps to `/homeassistant_config/www/`

## [1.0.22] - 2024-12-24

### Fixed
- Floorplan SVG now loads correctly from /local/ paths
- Added config:ro mapping to access Home Assistant www folder
- Floorplan loaded from filesystem instead of HTTP API (more reliable)

## [1.0.21] - 2024-12-24

### Changed
- Skip topology scan wait entirely - ZHA already maintains neighbor data
- topology_scan_wait setting now ignored (fixes WebSocket timeout issues)
- Data refresh now completes in seconds instead of 60+ seconds

## [1.0.20] - 2024-12-24

### Fixed
- WebSocket connection no longer times out during topology scan wait
- Send periodic pings to keep connection alive during 60s scan wait

## [1.0.19] - 2024-12-24

### Fixed
- Data refresh no longer hangs after topology scan wait
- Topology scan now uses simple sleep instead of consuming WebSocket messages

### Added
- Version number now displayed in startup log

## [1.0.18] - 2024-12-24

### Fixed
- Entity states now fetched for all entities (not just those with 'zha' in ID)
- ZHA entities like `light.kitchen` now properly matched via registry chain

## [1.0.17] - 2024-12-24

### Fixed
- Entity-to-device matching now uses device registry and entity registry
- Entities properly linked to ZHA devices via IEEE address from device identifiers
- Entity names now searchable and displayed in device tooltips

### Added
- Fetch entity registry (step 8/8) for proper entity-to-device mapping

## [1.0.16] - 2024-12-24

### Fixed
- Skip cluster fetching entirely (was causing hangs, not needed for visualization)
- Data refresh now completes reliably

## [1.0.15] - 2024-12-24

### Fixed
- Data refresh no longer hangs on step 6/7 (cluster fetching)
- Added 2-minute overall timeout for cluster fetching
- Reduced per-request timeout from 10s to 5s
- Shows progress: "done (X devices, Y errors)" after cluster fetch

## [1.0.14] - 2024-12-24

### Added
- Timestamps on all log entries for easier debugging
- "Data as of" display in header now shows relative time (e.g., "2 hours ago")
- Data age updates every minute without page refresh
- Debug logging for entity-to-device matching

### Fixed
- Improved entity matching diagnostics

## [1.0.13] - 2024-12-24

### Added
- Entities now displayed in device tooltip with friendly names and current state
- Show up to 5 entities per device in tooltip (with count indicator for more)
- Entity state color coding (green for on, gray for off)

### Fixed
- Entity search now works correctly by matching entities from Home Assistant REST API
- Entities properly linked to devices via IEEE address matching
- Added server-side debug logging for floorplan SVG detection

### Changed
- Entity extraction now uses Home Assistant entity states API for accurate friendly names

## [1.0.12] - 2024-12-24

### Fixed
- Entity names now searchable (includes friendly names and entity IDs)
- Version display now correctly shows add-on version (was showing "vunknown")
- Added browser console logging for floorplan debugging

### Changed
- Improved entity data extraction from ZHA devices

## [1.0.11] - 2024-12-23

### Added
- Auto-regenerate UI on every page load (no full data refresh needed for UI updates)
- "Regenerate UI" button for quick UI refresh without data fetch
- Floorplan SVG background layer support
- Search bar filtering by device name, entity names, and NWK ID
- Depth field in device tooltip
- NWK address in device tooltip
- Full routing path display in tooltip (Device —(LQI)→ Router —(LQI)→ Coordinator)
- Version number display in UI header

### Changed
- Tooltip width now responsive
- Improved position persistence with floorplan-relative coordinates

## [1.0.0] - 2024-12-05

### Added
- Initial release
- Interactive D3.js network visualization
- Real-time ZHA data export via WebSocket API
- Signal quality (LQI) indicators with color coding
- Device type identification (Coordinator, Router, End Device)
- Neighbor table inspection overlay
- Draggable nodes with position persistence
- Connection type visualization (route, parent, neighbor, sibling)
- Configurable auto-refresh interval
- Time-based device filtering
- Zoom and pan controls
- Health check endpoint (`/health`)
- Status endpoint (`/status`)
