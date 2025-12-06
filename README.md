# Home Assistant ZHA Topology Add-on Repository

This repository contains the ZHA Network Topology Visualizer add-on for Home Assistant.

## Add-ons

### ZHA Network Topology Visualizer

Interactive visualization of your Zigbee mesh network.

![Supports aarch64 Architecture](https://img.shields.io/badge/aarch64-yes-green)
![Supports amd64 Architecture](https://img.shields.io/badge/amd64-yes-green)
![Supports armv7 Architecture](https://img.shields.io/badge/armv7-yes-green)
![Supports i386 Architecture](https://img.shields.io/badge/i386-yes-green)

**Features:**
- Interactive D3.js network visualization
- Signal quality (LQI) indicators
- Device connection mapping
- Neighbor table inspection
- Configurable auto-refresh
- Draggable nodes with position saving

## Installation

1. Add this repository to your Home Assistant Add-on Store:

   [![Add Repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%scottswaaley%2Fhass-zha-topology)

   Or manually add: `https://github.com/scottswaaley/hass-zha-topology`

2. Refresh the add-on store
3. Install "ZHA Network Topology Visualizer"
4. Start the add-on
5. Access at `http://<your-ha-ip>:8099`

## Requirements

- Home Assistant OS or Supervised installation
- ZHA integration configured and running

## Documentation

See the [add-on documentation](zha-topology-visualizer/DOCS.md) for detailed usage instructions.

## Support

- [Report an issue](https://github.com/scottswaaley/hass-zha-topology/issues)
- [Home Assistant Community](https://community.home-assistant.io/)

## License

MIT License
