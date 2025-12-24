"""
Home Assistant ZHA Data Exporter for Add-on Environment
Downloads all Zigbee device data, network topology, and mesh info from ZHA.
Uses Supervisor API for authentication.
"""

import asyncio
import aiohttp
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def log(message: str, end: str = '\n', flush: bool = False):
    """Print a log message with timestamp."""
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}", end=end, flush=flush)


# Configuration from environment (provided by Home Assistant Supervisor)
SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN')
INTERNAL_API_URL = "http://supervisor/core"
WS_URL = "ws://supervisor/core/websocket"

# Data directory for persistence
DATA_DIR = Path('/data')

# Timeouts - can be overridden by environment variable
WS_COMMAND_TIMEOUT = 30  # seconds per command
TOPOLOGY_SCAN_WAIT = int(os.environ.get('TOPOLOGY_SCAN_WAIT', 60))  # seconds to wait after triggering scan

# Set to True for debug output
DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'


class ZHAExporter:
    def __init__(self):
        if not SUPERVISOR_TOKEN:
            raise Exception("SUPERVISOR_TOKEN environment variable not set")
        self.token = SUPERVISOR_TOKEN
        self.ws_url = WS_URL
        self.api_url = INTERNAL_API_URL
        self.msg_id = 0

    def next_id(self) -> int:
        self.msg_id += 1
        return self.msg_id

    async def ws_command(self, ws, command: dict, timeout: float = WS_COMMAND_TIMEOUT) -> dict:
        """Send a WebSocket command and return the result with timeout."""
        msg_id = self.next_id()
        command["id"] = msg_id

        if DEBUG:
            log(f"      [DEBUG] Sending: {command.get('type')}")

        try:
            await ws.send_json(command)
        except (ConnectionResetError, aiohttp.ClientError) as e:
            log(f"      Error: WebSocket connection failed - {e}")
            raise

        try:
            # Wait for response with matching ID, with timeout
            end_time = asyncio.get_event_loop().time() + timeout

            while True:
                remaining = end_time - asyncio.get_event_loop().time()
                if remaining <= 0:
                    raise asyncio.TimeoutError(f"Timeout waiting for {command.get('type')}")

                try:
                    msg = await asyncio.wait_for(ws.receive_json(), timeout=remaining)
                except asyncio.TimeoutError:
                    raise asyncio.TimeoutError(f"Timeout waiting for {command.get('type')}")

                if DEBUG:
                    log(f"      [DEBUG] Received: type={msg.get('type')}, id={msg.get('id')}")

                # Check if this is our response
                if msg.get("id") == msg_id:
                    return msg

                # Skip events and other messages
                if msg.get("type") == "event":
                    continue

        except asyncio.TimeoutError:
            log(f"      Warning: Timeout on {command.get('type')}")
            return {"success": False, "error": "timeout"}

    async def authenticate(self, ws) -> bool:
        """Authenticate WebSocket connection."""
        try:
            msg = await asyncio.wait_for(ws.receive_json(), timeout=10)
            if msg.get("type") != "auth_required":
                log(f"      Unexpected message: {msg}")
                return False

            await ws.send_json({
                "type": "auth",
                "access_token": self.token
            })

            msg = await asyncio.wait_for(ws.receive_json(), timeout=10)
            return msg.get("type") == "auth_ok"
        except asyncio.TimeoutError:
            log("      Authentication timeout")
            return False

    async def export_all(self) -> dict:
        """Export all ZHA data including topology."""
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                self.ws_url,
                headers={"Authorization": f"Bearer {self.token}"},
                heartbeat=15,
                autoping=True,
                receive_timeout=None
            ) as ws:
                if not await self.authenticate(ws):
                    raise Exception("Authentication failed - check Supervisor token")

                log("      Connected and authenticated!")

                log("[1/7] Triggering topology scan...")
                await self.trigger_topology_scan(ws)

                log("[2/7] Fetching ZHA devices with neighbor data...")
                devices = await self.get_devices(ws)
                log(f"      Found {len(devices)} devices")

                log("[3/7] Fetching network settings...")
                network = await self.get_network_settings(ws)
                channel = network.get("network_info", {}).get("channel", "N/A")
                log(f"      Channel: {channel}")

                log("[4/7] Fetching network backups...")
                backups = await self.get_network_backups(ws)
                log(f"      Found {len(backups)} backups")

                log("[5/7] Fetching ZHA groups...")
                groups = await self.get_groups(ws)
                log(f"      Found {len(groups)} groups")

                log("[6/7] Fetching device clusters...")
                devices_with_clusters = await self.get_device_clusters(ws, devices)

                log("[7/7] Fetching device registry...")
                registry = await self.get_device_registry(ws)
                log(f"      Found {len(registry)} registry entries")

        # Fetch entity states via REST and optionally floorplan SVG
        async with aiohttp.ClientSession() as session:
            entities = await self.get_zha_entities(session)
            log(f"      Found {len(entities)} ZHA entities")

            # Fetch floorplan SVG if configured
            floorplan_svg = await self.get_floorplan_svg(session)
            if floorplan_svg:
                log(f"      Loaded floorplan SVG ({len(floorplan_svg)} bytes)")

        return {
            "export_timestamp": datetime.now().isoformat(),
            "network_settings": network,
            "network_backups": backups,
            "devices": devices_with_clusters,
            "groups": groups,
            "device_registry": registry,
            "entities": entities,
            "topology": self.build_topology(devices_with_clusters),
            "floorplan_svg": floorplan_svg
        }

    async def trigger_topology_scan(self, ws):
        """Trigger a network topology scan and wait for completion."""
        result = await self.ws_command(ws, {"type": "zha/topology/update"}, timeout=10)

        if not result.get("success", True):
            log(f"      Note: Topology update response: {result}")

        log(f"      Waiting {TOPOLOGY_SCAN_WAIT}s for scan to complete", end="", flush=True)
        start_time = asyncio.get_event_loop().time()
        last_dot = start_time

        while asyncio.get_event_loop().time() - start_time < TOPOLOGY_SCAN_WAIT:
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
                if msg.type == aiohttp.WSMsgType.CLOSE:
                    log("\n      Warning: WebSocket closed during scan wait")
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    log("\n      Warning: WebSocket error during scan wait")
                    break
            except asyncio.TimeoutError:
                pass

            now = asyncio.get_event_loop().time()
            if now - last_dot >= 5:
                print(".", end="", flush=True)  # Keep dots without timestamp for progress
                last_dot = now

        log(" done")

    async def get_devices(self, ws) -> list:
        """Fetch all ZHA devices."""
        result = await self.ws_command(ws, {"type": "zha/devices"})
        return result.get("result", [])

    async def get_network_settings(self, ws) -> dict:
        """Fetch ZHA network settings."""
        result = await self.ws_command(ws, {"type": "zha/network/settings"})
        return result.get("result", {})

    async def get_network_backups(self, ws) -> list:
        """Fetch list of network backups."""
        result = await self.ws_command(ws, {"type": "zha/network/backups/list"})
        return result.get("result", [])

    async def get_groups(self, ws) -> list:
        """Fetch ZHA groups."""
        result = await self.ws_command(ws, {"type": "zha/groups"})
        return result.get("result", [])

    async def get_device_registry(self, ws) -> list:
        """Fetch device registry filtered to ZHA devices."""
        result = await self.ws_command(ws, {"type": "config/device_registry/list"})
        all_devices = result.get("result", [])

        return [
            d for d in all_devices
            if any("zha" in str(ident).lower() for ident in d.get("identifiers", []))
        ]

    async def get_device_clusters(self, ws, devices: list) -> list:
        """Fetch cluster information for each device."""
        log(f"      Fetching clusters for {len(devices)} devices", end="", flush=True)

        # Set an overall timeout for cluster fetching (2 minutes max)
        start_time = asyncio.get_event_loop().time()
        max_duration = 120  # seconds
        devices_processed = 0
        errors = 0

        for device in devices:
            # Check if we've exceeded the overall timeout
            if asyncio.get_event_loop().time() - start_time > max_duration:
                log(f"\n      Warning: Cluster fetch timeout after {devices_processed} devices")
                break

            ieee = device.get("ieee")
            if not ieee:
                continue

            device["cluster_details"] = {}

            for endpoint in device.get("endpoint_names", []):
                endpoint_id = endpoint.get("endpoint_id")
                if endpoint_id is None:
                    continue

                try:
                    result = await self.ws_command(ws, {
                        "type": "zha/devices/clusters",
                        "ieee": ieee,
                        "endpoint_id": endpoint_id
                    }, timeout=5)  # Reduced timeout per request

                    if result.get("success", True):
                        clusters = result.get("result", [])
                        device["cluster_details"][endpoint_id] = clusters
                    else:
                        errors += 1
                except Exception as e:
                    errors += 1
                    if DEBUG:
                        log(f"\n      [DEBUG] Cluster fetch failed for {ieee}: {e}")

            devices_processed += 1
            print(".", end="", flush=True)  # Keep dots without timestamp for progress

        log(f" done ({devices_processed} devices, {errors} errors)")
        return devices

    async def get_zha_entities(self, session: aiohttp.ClientSession) -> list:
        """Fetch ZHA entity states via REST API."""
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        try:
            async with session.get(
                f"{self.api_url}/api/states",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    log(f"      Warning: Could not fetch entities (HTTP {resp.status})")
                    return []

                all_states = await resp.json()

                zha_entities = []
                for entity in all_states:
                    entity_id = entity.get("entity_id", "")
                    attributes = entity.get("attributes", {})

                    if "ieee" in str(attributes) or "zha" in entity_id.lower():
                        zha_entities.append(entity)

                return zha_entities
        except Exception as e:
            log(f"      Warning: Entity fetch failed: {e}")
            return []

    async def get_floorplan_svg(self, session: aiohttp.ClientSession) -> str:
        """Fetch floorplan SVG from Home Assistant if configured."""
        # Read the floorplan path from options
        options_file = DATA_DIR / 'options.json'
        if not options_file.exists():
            return None

        try:
            with open(options_file) as f:
                options = json.load(f)
        except Exception:
            return None

        floorplan_path = options.get('floorplan_svg', '')
        if not floorplan_path:
            return None

        # Convert /local/ path to actual API endpoint
        # /local/path/file.svg -> /api/local/path/file.svg
        if floorplan_path.startswith('/local/'):
            api_path = floorplan_path.replace('/local/', '/api/local/', 1)
        elif floorplan_path.startswith('local/'):
            api_path = '/api/' + floorplan_path
        else:
            api_path = '/api/local/' + floorplan_path.lstrip('/')

        headers = {
            "Authorization": f"Bearer {self.token}",
        }

        try:
            url = f"{self.api_url}{api_path}"
            if DEBUG:
                log(f"      [DEBUG] Fetching floorplan from: {url}")

            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    log(f"      Warning: Could not fetch floorplan SVG (HTTP {resp.status})")
                    return None

                content_type = resp.headers.get('Content-Type', '')
                if 'svg' not in content_type and 'xml' not in content_type:
                    log(f"      Warning: Floorplan file is not SVG (Content-Type: {content_type})")

                svg_content = await resp.text()
                return svg_content
        except Exception as e:
            log(f"      Warning: Floorplan fetch failed: {e}")
            return None

    def build_topology(self, devices: list) -> dict:
        """Build a topology structure suitable for visualization."""
        nodes = []
        edges = []

        ieee_to_name = {}
        for device in devices:
            ieee = device.get("ieee", "")
            name = device.get("user_given_name") or device.get("name", ieee)
            ieee_to_name[ieee] = name

        for device in devices:
            ieee = device.get("ieee", "")
            name = device.get("user_given_name") or device.get("name", ieee)
            device_type = device.get("device_type", "Unknown")
            manufacturer = device.get("manufacturer", "Unknown")
            model = device.get("model", "Unknown")

            device_lqi_raw = device.get("lqi")
            try:
                device_lqi = int(device_lqi_raw) if device_lqi_raw else None
            except (ValueError, TypeError):
                device_lqi = None

            nodes.append({
                "id": ieee,
                "name": name,
                "device_type": device_type,
                "manufacturer": manufacturer,
                "model": model,
                "is_coordinator": device_type == "Coordinator",
                "lqi": device_lqi,
                "rssi": device.get("rssi")
            })

            neighbors = device.get("neighbors", [])
            for neighbor in neighbors:
                neighbor_ieee = neighbor.get("ieee", "")
                lqi_raw = neighbor.get("lqi", 0)
                try:
                    lqi = int(lqi_raw) if lqi_raw else 0
                except (ValueError, TypeError):
                    lqi = 0
                relationship = neighbor.get("relationship", "Unknown")

                if neighbor_ieee:
                    edges.append({
                        "source": ieee,
                        "source_name": name,
                        "target": neighbor_ieee,
                        "target_name": ieee_to_name.get(neighbor_ieee, neighbor_ieee),
                        "lqi": lqi,
                        "lqi_percent": round((lqi / 255) * 100, 1) if lqi else 0,
                        "relationship": relationship
                    })

        return {
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges)
        }


def print_topology_summary(topology: dict):
    """Print a summary of the network topology."""
    log("=" * 60)
    log("NETWORK TOPOLOGY SUMMARY")
    log("=" * 60)

    nodes = topology.get("nodes", [])
    edges = topology.get("edges", [])

    coordinators = sum(1 for n in nodes if n.get("is_coordinator"))
    routers = sum(1 for n in nodes if n.get("device_type") == "Router")
    end_devices = sum(1 for n in nodes if n.get("device_type") == "EndDevice")

    log(f"Devices: {len(nodes)} total")
    log(f"  - Coordinator: {coordinators}")
    log(f"  - Routers: {routers}")
    log(f"  - End Devices: {end_devices}")

    device_lqis = [n.get("lqi") for n in nodes if n.get("lqi") is not None]
    if device_lqis:
        avg_device_lqi = sum(device_lqis) / len(device_lqis)
        min_device_lqi = min(device_lqis)
        max_device_lqi = max(device_lqis)
        log(f"Device Signal Quality (matches ZHA visualization):")
        log(f"  - Average: {avg_device_lqi:.0f}/255 ({(avg_device_lqi/255)*100:.0f}%)")
        log(f"  - Range: {min_device_lqi} - {max_device_lqi}")

        weak_devices = [(n.get("name"), n.get("lqi")) for n in nodes
                        if n.get("lqi") is not None and n.get("lqi") < 50]
        if weak_devices:
            log(f"[!] Weak Devices (LQI < 50):")
            for name, lqi in sorted(weak_devices, key=lambda x: x[1]):
                log(f"  - {name}: LQI {lqi}")

    log(f"Mesh Connections: {len(edges)} neighbor links")
    if edges:
        link_lqis = [e.get("lqi", 0) for e in edges if e.get("lqi")]
        if link_lqis:
            avg_link_lqi = sum(link_lqis) / len(link_lqis)
            min_link_lqi = min(link_lqis)
            max_link_lqi = max(link_lqis)
            log(f"  - Average link LQI: {avg_link_lqi:.0f}/255 ({(avg_link_lqi/255)*100:.0f}%)")
            log(f"  - Range: {min_link_lqi} - {max_link_lqi}")


async def export_data():
    """Export ZHA data and save to file."""
    log("=" * 60)
    log("Home Assistant ZHA Full Data Exporter")
    log("=" * 60)

    exporter = ZHAExporter()

    try:
        data = await exporter.export_all()
    except Exception as e:
        log(f"Error: {e}")
        raise

    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = DATA_DIR / f"zha_full_export_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(data, f, indent=2, default=str)

    log("=" * 60)
    log(f"Export saved to: {filename}")

    print_topology_summary(data.get("topology", {}))

    log("=" * 60)

    return str(filename)


def main():
    return asyncio.run(export_data())


if __name__ == "__main__":
    main()
