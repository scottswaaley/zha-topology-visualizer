# Changelog

All notable changes to this project will be documented in this file.

## [1.7.1] - 2026-11-13

### Added
- **Espressif ESP32-C6/H2 LQI formulas** in the conversion table, ready for DIY routers:
  - **esp-zigbee-sdk 1.x (ZBOSS):** LQI is recomputed from RSSI, linear from −80 to −30 dBm (`esp_zb_rssi_to_lqi`, esp-zigbee-lib 1.6.8).
  - **SDK 2.x:** reports the Zigbee R23 link quality assessment, about −101 to +8 dBm (median of the last 3 frames).

  Not auto-assigned yet, because ZHA doesn't expose which SDK a device's firmware uses.

## [1.7.0] - 2026-11-13

### Changed
- **LQI is converted to dBm per radio chip, using each vendor's real formula.** LQI is not standardised: each chip vendor computes it differently, so raw values aren't comparable across devices. Most stacks compute it as a clamped straight line from the packet's RSSI, so each device's readings now convert back to dBm with its own chip's constants. This replaces the 1.6.5 rescaling heuristic. The coverage estimate, signal-vs-distance layer and signal radar now work in dBm. LQI numbers on lines, badges and the neighbour overlay stay raw.

  | Chip family | LQI → dBm | Source |
  |---|---|---|
  | TI CC26xx/CC13xx (SDK ≥ 5.30) | −90 + LQI × 70/255 | TI SimpleLink SDK `mac_radio_defs.h` |
  | TI CC2530 | −87 + LQI × 97/255 | TI Z-Stack 3.0.2 `mac_radio_defs.h` |
  | Telink TLSR825x (SDK 2021+) | −99 + LQI × 84/255 | Telink Zigbee SDK `drv_radio.h` |
  | Silicon Labs EFR32 | −100 + LQI / 4 | Silicon Labs knowledge base |
  | NXP JN516x | (7 × LQI − 1970) / 20 (approximate) | NXP internal docs, via Contiki |
  | Unknown (NXP JN518x, Bouffalo BL702, others) | −100 + LQI × 80/255 (generic estimate) | none published |

  The chip is identified from the IEEE address prefix (OUI), with model-specific overrides (e.g. SONOFF S31 Lite zb = CC2530). The device card shows each device's radio family and conversion. On this network, converting cut the median disagreement between the two directions of a link from about 7 dB (raw LQI) to 4.8 dB over 65 links measured from both ends.
- **Coverage** thresholds are now in dBm: the 10-step absolute scale runs from −92 to −65 dBm, the summary bands are good ≥ −75 and fair ≥ −85 dBm, and Combined treats −88 dBm as a 50% delivery chance.
- **Signal radar** rings are at −85 / −75 / −65 dBm.

## [1.6.5] - 2026-11-13

### Fixed
- **Coverage and signal-vs-distance no longer penalise the coordinator for its LQI scale.** Chip vendors report LQI on different scales: on this network, routers such as the Third Reality Night Light, SONOFF MINI-ZB2GS, GL-G-003P and Inovelli report up to 222–255, while the TI coordinator tops out at 90. One distance fit across all of them made the coordinator's honest readings look like heavy losses in every direction, so the map showed red around it. For these models only, each device whose readings run clearly above 100 (by its own 90th percentile, with at least 5 readings) is scaled down to a common ~100 ceiling; devices are never scaled up, so genuinely weak ones stay weak. In a simulated mixed-vendor mesh, this cut the coordinator's false penalty from −45 to −10 LQI. Displayed LQI numbers stay raw; the distance-layer tooltip shows rescaled values with the original.

## [1.6.4] - 2026-11-13

### Fixed
- **Neighbour-table LQI of 1 or 2 is now treated as "not reported", like 0.** TI Z-Stack fills entries it hasn't heard from recently with these placeholders; the coordinator's table, for example, listed seven routers at LQI 1. Read as real measurements, they made the coordinator look nearly deaf, so the coverage map showed red around it, the distance fit was skewed, and those links drew as very weak. They now show as "?" and are left out of every calculation. Applies to existing data on the next page load; no refresh needed.

## [1.6.3] - 2026-11-13

### Fixed
- **Combined coverage no longer turns the whole house green.** With many strong routers nearly every spot scored "certain" and hit the cap, so the relative scale could not tell spots apart. Three changes:
  - Combined now counts only the **3 strongest routers in range** (the realistic set of fallback parents).
  - It is computed in log space, so very likely spots no longer round to exactly certain and tie.
  - The relative scale ranks the uncapped scores.

  The cap at LQI 120 now applies only to the Absolute scale and to the numbers shown.

## [1.6.2] - 2026-11-13

### Changed
- **Coverage colours auto-calibrate by default.** With a fixed LQI scale, a well-meshed house came out green almost everywhere. The new default **Relative (auto)** scale spreads the 10 colours across the scores actually found around your placed routers (deciles over the box they span), so the weakest areas always stand out. **Absolute LQI** is still available from the Scale selector. The summary message gives the real LQI range the colours cover, and falls back to the fixed scale when scores are nearly uniform.
- **The Combined score is capped at LQI 120** (TI's practical ceiling), so many strong routers no longer produce impossible values.

## [1.6.1] - 2026-11-13

### Changed
- **Coverage measure selector.** Under the Coverage toggle, choose how routers in range combine at each spot:
  - **Combined** (default): the chance at least one router link works, shown on the LQI scale. Each router's predicted LQI becomes a rough delivery chance (50 ≈ 50%, 70 ≈ 92%, 35 ≈ 13%), so two decent routers beat one, but many weak ones don't add up to a strong one.
  - **Best router:** the strongest single router, which is what Zigbee would pick as the parent.
  - **Backup (2nd best):** what's left if that router fails.
- **10-step colour ramp** (deep red to deep green, with a gradient key in the legend) instead of three bands. Spots with no router in range are grey, since that means "no data", not "weak".

## [1.6.0] - 2026-11-13

### Added
- **Coverage estimate** (legend toggle, off by default). For devices placed on the floorplan, colours every 2 ft cell by the best LQI any router or the coordinator is predicted to give there: green ≥ 65, amber 45–65, red < 45 or out of range. Each router's prediction starts from the signal-vs-distance fit of your measured links and is corrected per direction by how that router's own links in that direction compare with the fit, so a wall it can't see through darkens everything behind it. Range is capped at your longest measured link (max 60 ft) so it never extrapolates past the evidence. It uses the best router at each spot rather than a sum, so dense clusters of weak routers don't read as "strong". A summary toast gives the share of the area in each band, and warns when your links show too little drop-off with distance for the estimate to mean much. Re-toggle after moving devices. This is a model, not a measurement.

## [1.5.5] - 2026-11-13

### Fixed
- **Radar shapes no longer collapse into stray slivers.** The shape was a smooth curve through the neighbours in angle order; when neighbours clustered in a few directions (e.g. two opposite sides of a hallway) it became a thin sliver that could miss the device entirely. It is now an envelope over 16 fixed compass sectors: each sector takes its strongest neighbour, empty sectors pinch to the centre. The shape always surrounds the device, and gaps mean "nothing heard that way". Dots still mark each neighbour's true direction.

## [1.5.4] - 2026-11-13

### Changed
- **Radar colours are easier to read.** The outgoing shape now has a transparent amber fill, not just a dashed outline, and the area where incoming and outgoing overlap is drawn in its own green (a clip of one shape by the other), so it reads clearly on both the dark background and the floorplan. Cyan = incoming only, amber = outgoing only, green = both.

## [1.5.3] - 2026-11-13

### Changed
- **The signal radar is drawn on the map, around the device itself,** so each spoke points at the real neighbour. Clicking a device draws a large one with scale rings at LQI 45 / 65 / 90 and a dot per neighbour. A new legend toggle, **Signal shape on every device**, draws a small one around every device at once for comparing coverage. Filled cyan = incoming (how the device receives each neighbour); dashed amber = outgoing (how each neighbour receives it). The card no longer draws its own copy.

## [1.5.2] - 2026-11-13

### Changed
- **The tree choice is a segmented control,** "Tree from: [Best evidence | Neighbour tables]", instead of a single button whose label flipped. The highlighted side is the one in use; clicking it again does nothing.

## [1.5.1] - 2026-11-13

### Changed
- **The signal radar is a continuous shape.** A smooth closed curve runs through the neighbours in direction order: filled cyan = how this device hears them, dashed amber outline = how they hear it. Dots and spokes stay on top. Needs at least 3 known values per direction; fewer falls back to dots only.

## [1.5.0] - 2026-11-13

### Changed
- **New legend, grouped by the question each mark answers:** what is this device / who is its parent / how good is that hop / which way does traffic go / what needs attention. It replaces the single mixed row, and a **Legend** button collapses it (remembered per browser).
- **The legend is the filter panel.** Square boxes show or hide a layer: each tree-line source, all stored/cached lines at once, LQI numbers, route paths, router-load badges, end devices, router-to-router links. Round boxes focus on one problem (conflict, flapping, silent, no route, offline), dimming everything else; each shows its count. The separate Routes, LQI Labels and Show End Devices buttons are gone.
- **Line style now means one thing each.** Dashed = stored or cached source (startup route records, route tables not read this refresh). A device not heard in 24 h fades its line instead of dashing it.
- **The parent-field colour is now teal,** so it no longer matches the router node green.

### Added
- **Flapping replay.** Focusing on Flapping draws, for each flapping device, a faint line to every hop it has recently used, and steps a highlight through its recent route history in order. Respects reduced-motion settings.
- **Signal radar in the device card.** One spoke per neighbour, pointing where that neighbour sits on the map, with its length set by LQI: ● how this device hears it, ○ how it hears this device; dotted = not reported. Weak or missing directions (walls, metal boxes) stand out.
- **Signal vs distance layer** (legend toggle, off by default). For devices you have placed on the map, fits LQI against distance across every measured link (LQI ≈ a + b·ln distance) and colours each link by how it compares: red/orange = weaker than its distance predicts (likely an obstruction), grey = as expected, blue = stronger. Hover a link for the distance, both LQIs and the expected value.

### Changed (flapping)
- **Flapping is now measured per report:** a device is flapping when more than 25% of its route reports show a new path (minimum 10 reports). The old changes-per-hour rule penalised devices that simply report often. The card shows "Path changes: N of M reports (X%)".

## [1.4.2] - 2026-11-11

### Changed
- **Bigger arrowhead on the LQI hover arrow** (9 → 16 px), with its tip ending at the edge of the receiving node so the direction reads at a glance.

### Fixed
- **Arrowheads were missing whenever the floorplan was loaded.** Both the route-layer arrows (since 1.4.0) and the LQI hover arrow (1.4.1) put their markers into the floorplan SVG's own `<defs>`, where they never render. They now use a dedicated `<defs>` on the graph.

## [1.4.1] - 2026-11-11

### Added
- **Both LQI directions on every tree line.** Each tree line now carries two numbers: child → parent (measured by the parent) and parent → child (measured by the child), each placed on the side of the node that measured it; "?" = not reported. Hover a number to draw an arrow along the line in the direction it was measured, with a tooltip naming who measured it. Hovering the line itself shows both. An **LQI Labels** button hides them. LQI stays off the magenta route lines, since route records carry no link quality.

- **Next-hop evidence in the device card.** Each device lists every source for its next hop toward the coordinator, side by side with its age: live route record, route table (marked "scanned this refresh" or "cached"), startup route record, parent relationship. Each is marked used / agrees / alternating / differs (stale) / conflicts, with an overall verdict.
- **Conflict detection.** A conflict is two *current* sources pointing at different next hops, where the other hop isn't in the device's recent route history. Shown as a dashed amber line to the other hop, a ⚠ on the node, and a count in the route header line. Normal path switching shows as "alternating" and stale data as "differs (stale)"; neither raises an alarm.
- **Scan tracking.** A refresh now records which routers answered the zha-toolkit scan (`scan` in the export), so a route table read this refresh can be told apart from ZHA's cached copy.

### Changed
- **"Tree: Best evidence" replaces "Tree: Routes".** Each device hangs from its most trusted next hop: live route record > route table scanned this refresh > parent reported by a scanned router > startup route record > cached route table > other parent data > estimated/unknown. Startup-only route records draw dashed. "Tree: Neighbour tables" is the v1.3 view, unchanged.
- **"Route (confirmed)" is now "Route table"** in the legend and card, next to "Route record".
- **Tree line thickness uses the weaker known direction.** A hop needs both directions (data one way, acknowledgement the other), so the weaker one is the honest summary. Previously it used child → parent and fell back to parent → child.
- **The card's Path line shows both directions per hop** (`82 → / ← 108`), matching "Connected via". Previously it showed whichever direction was to hand, unlabelled.
- **Router load counts live routes only.** The badge and busiest-router ring now count devices that sent a route record since `zha_routes` started listening. Routes known only from startup data (age unknown) are listed separately in the card, e.g. "15 live, 7 startup only". A router with only stale routes through it no longer looks busy.

### Fixed
- **The route layer no longer covers the click-to-show neighbour lines and their LQI numbers.** It is now drawn underneath them.

## [1.4.0] - 2026-11-11

### Added
- **Source-route layer (optional, needs the `zha_routes` custom integration).** Each refresh now also reads `zha_routes/snapshot` (read-only) and stores it under `routes` in the export. When present:
  - **Routes toggle** draws each device's real path (device → relays → coordinator) as directed magenta segments. Segments shared by several devices merge into one line whose thickness scales with the number of paths; hover a segment to see which devices use it. Paths known only from startup (database) data are dashed.
  - **Device detail** shows the named route, hop count, live vs startup source, time since the last route report, route changes since listening started (with rate), and the recent change history. Clicking a device highlights its full path.
  - **Router load**: a purple badge on each router with the number of device paths through it (counted from relays, not names); the busiest router gets a gold ring.
  - **Flags**: ↯ flapping (more than `FLAP_CHANGES_PER_HOUR` = 5 changes/hour), z silent (startup route only, or no report for `SILENT_HOURS` = 6h), ∅ no route. Thresholds are named constants in `visualize.py`.
  - **Tree: Routes / Neighbours** toggle. With routes present the tree defaults to route records (parent = first relay; direct devices hang off the coordinator; devices without a route fall back to the v1.3 method). The neighbour-based tree is one click away.
  - A header line shows when `zha_routes` started listening and the total live reports, plus flag counts.
- Without `zha_routes` (unknown command, error or timeout) the add-on logs one line, sets `routes` to null, and the page renders exactly as in 1.3.1.

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
