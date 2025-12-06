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
| `topology_scan_wait` | 60 | Seconds to wait for topology scan. Increase for large networks. |

### Example Configuration

```yaml
auto_refresh_minutes: 30
topology_scan_wait: 90
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
- **Cyan lines**: Connection determined from route table (most accurate)
- **Green lines**: Parent relationship
- **Yellow lines**: Strongest neighbor connection
- **Gray lines**: Fallback connection to coordinator
- **Dashed lines**: Sibling mesh connections (hidden by default)

#### LQI Values
- **Green (150+)**: Excellent signal
- **Light Green (100-149)**: Good signal
- **Yellow (50-99)**: Fair signal
- **Red (<50)**: Weak signal

### Controls

- **Refresh Data**: Fetch fresh topology data from ZHA
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
- Wait for the topology scan to complete (60+ seconds)

### Missing neighbor data
- Increase `topology_scan_wait` in the configuration
- Some battery devices may not report neighbors until they wake up

### Slow refresh
- Topology scans take time to gather data from all devices
- Large networks (50+ devices) may take 2-3 minutes

### Connection shows "Fallback"
- The device's actual route couldn't be determined
- This is normal for newly added devices or after power outages

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
