# ZHA Network Topology Visualizer

This add-on provides an interactive visualization of your Zigbee mesh network topology, showing device connections, signal quality, and mesh relationships.

## Features

- **Interactive D3.js Visualization**: Explore your Zigbee network with a force-directed graph
- **Signal Quality Indicators**: Color-coded LQI values show connection strength
- **Device Types**: Easily identify coordinators, routers, and end devices
- **Neighbor Tables**: Click any device to see its complete neighbor list
- **Draggable Nodes**: Arrange devices manually and save positions
- **Auto-Refresh**: Optionally refresh data automatically at configured intervals
- **Filters**: Filter by device type or last-seen time

## Installation

1. Navigate to **Settings** → **Add-ons** → **Add-on Store**
2. Click the three-dot menu in the top right corner
3. Select **Repositories**
4. Add the repository URL: `https://github.com/scottswaaley/hass-zha-topology`
5. Click **Add** and refresh the page
6. Find "ZHA Network Topology Visualizer" and click **Install**

## Configuration

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `auto_refresh_minutes` | 0 | Minutes between automatic refreshes. Set to 0 to disable. |
| `use_zha_toolkit` | true | Actively scan every router for live routes & neighbour LQIs via zha-toolkit on each refresh. Requires the zha-toolkit integration; falls back to cached data if unavailable. |
| `zha_toolkit_timeout` | 300 | Max seconds to wait for the active scan. Increase (toward 600) for large networks that time out. |

> **Optional dependency:** `use_zha_toolkit` needs the **zha-toolkit** custom
> integration ([install via HACS](https://github.com/mdeweerd/zha-toolkit)).
> Without it the add-on still works, but link LQIs come from the coordinator's
> cached neighbour tables (on TI Z-Stack, many router-to-router LQIs read as
> "not reported").

### Example Configuration

```yaml
auto_refresh_minutes: 30
use_zha_toolkit: true
zha_toolkit_timeout: 240
```

## Usage

### Accessing the Visualization

After starting the add-on, access the visualization at:
```
http://<your-home-assistant-ip>:8099
```

Or click **Open Web UI** from the add-on page.

### Understanding the Visualization

#### Node Colors
- **Cyan**: Coordinator (your Zigbee stick)
- **Green**: Router (powered devices that extend the mesh)
- **Yellow**: End Device (battery-powered sensors, etc.)

#### Connection Types
Connections are grouped by how confident we are in them:
- **Cyan (Route, confirmed)**: parent taken from the device's route table — the most authoritative source.
- **Green (Parent, confirmed)**: parent taken from a reported Parent/Child relationship.
- **Orange dashed (Estimated)**: best guess from signal strength — no relationship was reported.
- **Gray dashed (Unknown)**: attachment could not be determined; the node is drawn at the coordinator for layout only.
- **Faint dashed (Sibling)**: router-to-router mesh links (hidden by default).
- **Dashed (Stale)**: the reporting device hasn't been heard from in over 24h.

#### LQI Values (signal of the last hop to the coordinator)
- **Green (150+)**: Excellent signal
- **Light Green (100-149)**: Good signal
- **Yellow (50-99)**: Fair signal
- **Red (<50)**: Weak signal
- **Gray (not reported)**: no measurement — common for router-to-router links on TI Z-Stack coordinators. This means "unknown", **not** "bad".

> Note: the per-device LQI badge is the quality of the **last hop into the
> coordinator**, not the device's own first-hop link. A multi-hop device can show
> a low badge even when its own link is strong.

### Controls

- **Refresh Data**: Actively re-measure the network (scans every router for fresh routes & neighbour LQIs via zha-toolkit when enabled), then reload. Takes 1-5 minutes.
- **Scan Network**: Ask ZHA to rebuild its own topology cache. Usually unnecessary now that Refresh scans actively.
- **Reset Layout**: Reset node positions to auto-layout
- **Save Positions**: Save current node arrangement
- **Show/Hide End Devices**: Toggle visibility of end devices
- **Time Filter**: Show only devices seen recently
- **Zoom Controls**: Zoom in/out and reset view

### Interacting with Nodes

- **Hover**: View device details (name, LQI, manufacturer, model)
- **Click**: Select a device and highlight its connections
- **Drag**: Move nodes to rearrange the layout
- **Click neighbor badge**: View the full neighbor table

## Troubleshooting

### Add-on won't start
- Ensure ZHA integration is properly configured and working
- Check the add-on logs for error messages

### Empty visualization
- Click "Refresh Data" to fetch topology data
- The active scan can take 1-5 minutes on larger networks

### Missing neighbor data
- Increase `zha_toolkit_timeout` in the configuration
- Install the zha-toolkit integration and keep `use_zha_toolkit` enabled for fresh router LQIs
- Some battery devices may not report neighbors until they wake up

### Slow refresh
- Active scans query every router, which takes time
- Large networks (50+ devices) may take several minutes; raise `zha_toolkit_timeout`

### Connection shows "Unknown"
- The device's attachment couldn't be determined and it's shown at the coordinator for layout only
- This is normal for newly added devices, sleepy battery devices, or after power outages

### Many links show "not reported"
- On TI Z-Stack coordinators, router-to-router link LQIs are frequently not populated
- Enable `use_zha_toolkit` (with the zha-toolkit integration installed) to actively query them

## Technical Details

The add-on uses the Home Assistant WebSocket API to:
1. Trigger a ZHA topology scan
2. Fetch all ZHA device data including neighbor tables
3. Retrieve device registry information
4. Build an interactive visualization

Data is stored in `/data/` within the add-on container and persists across restarts.

## Support

For issues and feature requests, please visit:
https://github.com/scottswaaley/hass-zha-topology/issues
