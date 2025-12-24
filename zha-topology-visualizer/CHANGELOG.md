# Changelog

All notable changes to this project will be documented in this file.

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
