# ZHA Network Topology Visualizer

Home Assistant add-on for visualizing your Zigbee mesh network topology.

![Zigbee Topology](https://img.shields.io/badge/Zigbee-Topology-blue)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Add--on-41BDF5)

## About

This add-on creates an interactive visualization of your ZHA (Zigbee Home Automation) network, showing:

- All Zigbee devices and their connections
- Signal quality (LQI) between devices
- Mesh network relationships
- Device types (coordinator, routers, end devices)

## Features

- **Interactive D3.js visualization** with draggable nodes
- **Real-time signal quality** indicators
- **Neighbor table inspection** for any device
- **Configurable auto-refresh** (optional)
- **Position persistence** - your layout is saved
- **Filter options** by device type and activity

## Installation

Add this repository to your Home Assistant Add-on Store:

[![Open your Home Assistant instance and show the add-on store.](https://my.home-assistant.io/badges/supervisor_store.svg)](https://my.home-assistant.io/redirect/supervisor_store/)

Then add this repository URL:
```
https://github.com/scottswaaley/hass-zha-topology
```

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `auto_refresh_minutes` | 0 | Auto-refresh interval (0 = disabled) |
| `topology_scan_wait` | 60 | Topology scan timeout in seconds |

## Usage

Access the visualization at `http://<your-ha-ip>:8099` after starting the add-on.

## Requirements

- Home Assistant with Supervisor
- ZHA integration configured and running
- Zigbee coordinator connected

## License

MIT License - See LICENSE file for details.
