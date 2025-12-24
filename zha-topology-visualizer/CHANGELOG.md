# Changelog

All notable changes to this project will be documented in this file.

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
