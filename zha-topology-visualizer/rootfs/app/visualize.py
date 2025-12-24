"""
ZHA Network Topology Visualizer
Generates an interactive HTML visualization using D3.js with draggable nodes.
Adapted for Home Assistant Add-on environment.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

# Data directory for persistence
DATA_DIR = Path('/data')


def load_topology(json_file: str) -> dict:
    """Load topology data from JSON export file."""
    with open(json_file, 'r') as f:
        data = json.load(f)
    return data


def build_hierarchy(data: dict) -> dict:
    """Build a hierarchical tree structure from the topology data."""
    topology = data.get('topology', {})
    nodes = {n['id']: n for n in topology.get('nodes', [])}
    edges = topology.get('edges', [])
    devices = {d.get('ieee'): d for d in data.get('devices', [])}

    coordinator = None
    for node in nodes.values():
        if node.get('is_coordinator'):
            coordinator = node
            break

    if not coordinator:
        print("Warning: No coordinator found in topology")
        return {}

    children = defaultdict(list)
    assigned = set()
    assigned.add(coordinator['id'])

    best_link = {}
    for edge in edges:
        src, tgt = edge['source'], edge['target']
        lqi = edge.get('lqi', 0) or 0
        key = tuple(sorted([src, tgt]))
        if key not in best_link or lqi > best_link[key]:
            best_link[key] = lqi

    def get_link_lqi(id1, id2):
        key = tuple(sorted([id1, id2]))
        return best_link.get(key, 0)

    router_parents = {}
    for edge in edges:
        source_id = edge['source']
        target_id = edge['target']
        relationship = edge.get('relationship')
        lqi = edge.get('lqi', 0) or 0
        source_node = nodes.get(source_id)
        target_node = nodes.get(target_id)

        if relationship == 'Parent':
            if source_node and source_node.get('device_type') == 'Router':
                if source_id not in router_parents or lqi > router_parents[source_id][1]:
                    router_parents[source_id] = (target_id, lqi)

        if relationship == 'Child':
            if target_node and target_node.get('device_type') == 'Router':
                if source_node and source_node.get('device_type') in ('Router', 'Coordinator'):
                    if target_id not in router_parents or lqi > router_parents[target_id][1]:
                        router_parents[target_id] = (source_id, lqi)

    routers = [n for n in nodes.values() if n.get('device_type') == 'Router']
    for router in routers:
        rid = router['id']
        if rid in router_parents:
            parent_id, lqi = router_parents[rid]
            children[parent_id].append((rid, lqi if lqi > 0 else None))
        else:
            lqi = get_link_lqi(coordinator['id'], rid)
            children[coordinator['id']].append((rid, lqi if lqi > 0 else None))
        assigned.add(rid)

    end_device_parent = {}
    for edge in edges:
        source_id = edge['source']
        target_id = edge['target']
        relationship = edge.get('relationship', '')
        lqi = edge.get('lqi', 0) or 0

        source_node = nodes.get(source_id)
        target_node = nodes.get(target_id)

        if relationship == 'Child':
            if source_node and target_node:
                if source_node.get('device_type') in ('Router', 'Coordinator') and \
                   target_node.get('device_type') == 'EndDevice':
                    if target_id not in end_device_parent or lqi > end_device_parent[target_id][1]:
                        end_device_parent[target_id] = (source_id, lqi)

    end_devices = [n for n in nodes.values() if n.get('device_type') == 'EndDevice']
    for device in end_devices:
        did = device['id']
        if did in assigned:
            continue

        if did in end_device_parent:
            parent_id, lqi = end_device_parent[did]
            children[parent_id].append((did, lqi if lqi > 0 else None))
            assigned.add(did)
            continue

        best_lqi = 0
        best_parent_id = coordinator['id']

        for edge in edges:
            if edge['source'] == did or edge['target'] == did:
                other_id = edge['target'] if edge['source'] == did else edge['source']
                other_node = nodes.get(other_id)
                if other_node and other_node.get('device_type') in ('Router', 'Coordinator'):
                    lqi = edge.get('lqi', 0) or 0
                    if lqi > best_lqi:
                        best_lqi = lqi
                        best_parent_id = other_id

        children[best_parent_id].append((did, best_lqi if best_lqi > 0 else None))
        assigned.add(did)

    for node in nodes.values():
        if node['id'] not in assigned:
            children[coordinator['id']].append((node['id'], None))
            assigned.add(node['id'])

    for parent_id in children:
        children[parent_id].sort(key=lambda x: (
            0 if nodes.get(x[0], {}).get('device_type') == 'Router' else 1,
            -(x[1] or 0)
        ))

    return {
        'coordinator': coordinator,
        'nodes': nodes,
        'children': dict(children),
        'devices': devices
    }


def generate_html(hierarchy: dict, data: dict, output_file: str):
    """Generate interactive HTML visualization with D3.js."""

    d3_nodes = []
    d3_links = []

    devices = hierarchy['devices']
    nodes = hierarchy['nodes']

    nwk_to_ieee = {}
    for ieee, device in devices.items():
        nwk = device.get('nwk')
        if nwk:
            nwk_to_ieee[nwk] = ieee

    device_primary_link = {}

    def nwk_to_int(nwk_val):
        if nwk_val is None:
            return None
        if isinstance(nwk_val, int):
            return nwk_val
        if isinstance(nwk_val, str):
            try:
                return int(nwk_val, 16) if nwk_val.startswith('0x') else int(nwk_val)
            except ValueError:
                return None
        return None

    valid_route_statuses = {'Active', 'Validation_Underway'}
    coordinator_id = hierarchy['coordinator']['id']

    for ieee, device in devices.items():
        routes = device.get('routes', [])
        if not routes:
            continue

        node = nodes.get(ieee)
        if not node or node.get('is_coordinator'):
            continue

        coord_route = None
        for route in routes:
            if route.get('route_status') in valid_route_statuses:
                dest_nwk = nwk_to_int(route.get('dest_nwk'))
                if dest_nwk == 0:
                    next_hop_nwk = nwk_to_int(route.get('next_hop'))
                    if next_hop_nwk is not None:
                        if next_hop_nwk == 0:
                            next_hop_ieee = coordinator_id
                        else:
                            next_hop_ieee = nwk_to_ieee.get(next_hop_nwk)

                        if next_hop_ieee and next_hop_ieee in nodes:
                            neighbors = device.get('neighbors', [])
                            lqi = 0
                            for n in neighbors:
                                n_nwk = nwk_to_int(n.get('nwk'))
                                if n_nwk == next_hop_nwk or n.get('ieee') == next_hop_ieee:
                                    try:
                                        lqi = int(n.get('lqi', 0) or 0)
                                    except (ValueError, TypeError):
                                        lqi = 0
                                    break
                            coord_route = (next_hop_ieee, lqi)
                            break

        if coord_route:
            device_primary_link[ieee] = {
                'target': coord_route[0],
                'lqi': coord_route[1],
                'source_type': 'route'
            }

    for ieee, device in devices.items():
        if ieee in device_primary_link:
            continue

        node = nodes.get(ieee)
        if not node:
            continue

        neighbors = device.get('neighbors', [])
        for n in neighbors:
            if n.get('relationship') == 'Parent':
                parent_ieee = n.get('ieee')
                if parent_ieee and parent_ieee in nodes:
                    try:
                        lqi = int(n.get('lqi', 0) or 0)
                    except (ValueError, TypeError):
                        lqi = 0
                    device_primary_link[ieee] = {
                        'target': parent_ieee,
                        'lqi': lqi,
                        'source_type': 'parent'
                    }
                    break

    for ieee in nodes:
        if ieee in device_primary_link:
            continue

        node = nodes.get(ieee)
        if not node or node.get('is_coordinator'):
            continue

        best_parent = None
        best_lqi = -1
        for other_ieee, other_device in devices.items():
            if other_ieee == ieee:
                continue
            other_node = nodes.get(other_ieee)
            if not other_node:
                continue
            if other_node.get('device_type') not in ('Router', 'Coordinator'):
                continue

            for n in other_device.get('neighbors', []):
                if n.get('ieee') == ieee and n.get('relationship') == 'Child':
                    try:
                        lqi = int(n.get('lqi', 0) or 0)
                    except (ValueError, TypeError):
                        lqi = 0
                    if lqi > best_lqi:
                        best_lqi = lqi
                        best_parent = other_ieee

        if best_parent:
            device_primary_link[ieee] = {
                'target': best_parent,
                'lqi': best_lqi,
                'source_type': 'parent'
            }

    for ieee, device in devices.items():
        if ieee in device_primary_link:
            continue

        node = nodes.get(ieee)
        if not node:
            continue

        if node.get('is_coordinator'):
            continue

        neighbors = device.get('neighbors', [])
        best_neighbor = None
        best_lqi = -1

        device_type = node.get('device_type')

        for n in neighbors:
            n_ieee = n.get('ieee')
            if not n_ieee or n_ieee not in nodes:
                continue

            n_node = nodes.get(n_ieee)
            try:
                lqi = int(n.get('lqi', 0) or 0)
            except (ValueError, TypeError):
                lqi = 0

            if device_type == 'EndDevice':
                if n_node and n_node.get('device_type') in ('Router', 'Coordinator'):
                    if lqi > best_lqi:
                        best_lqi = lqi
                        best_neighbor = n_ieee
            else:
                if lqi > best_lqi:
                    best_lqi = lqi
                    best_neighbor = n_ieee

        if best_neighbor:
            device_primary_link[ieee] = {
                'target': best_neighbor,
                'lqi': best_lqi,
                'source_type': 'neighbor'
            }

    coordinator_id = hierarchy['coordinator']['id']
    for ieee in nodes:
        if ieee not in device_primary_link and ieee != coordinator_id:
            device_primary_link[ieee] = {
                'target': coordinator_id,
                'lqi': None,
                'source_type': 'fallback'
            }

    child_to_parents = defaultdict(list)
    for ieee, link_info in device_primary_link.items():
        parent_ieee = link_info['target']
        parent_node = nodes.get(parent_ieee)
        parent_name = parent_node.get('name', parent_ieee) if parent_node else parent_ieee
        child_to_parents[ieee].append({
            'id': parent_ieee,
            'name': parent_name,
            'lqi': link_info['lqi'],
            'source_type': link_info['source_type']
        })

    for node_id, node in nodes.items():
        device = devices.get(node_id, {})
        neighbors = device.get('neighbors', [])
        neighbor_list = []
        for n in neighbors:
            neighbor_list.append({
                'ieee': n.get('ieee', ''),
                'lqi': int(n.get('lqi', 0)) if n.get('lqi') else 0,
                'relationship': n.get('relationship', 'Unknown'),
                'device_type': n.get('device_type', 'Unknown')
            })

        device_reg_id = device.get('device_reg_id', '')

        d3_nodes.append({
            'id': node_id,
            'name': node.get('name', node_id),
            'user_given_name': device.get('user_given_name', ''),
            'device_type': node.get('device_type', 'Unknown'),
            'manufacturer': node.get('manufacturer', ''),
            'model': node.get('model', ''),
            'lqi': node.get('lqi'),
            'last_seen': device.get('last_seen'),
            'available': device.get('available', True),
            'neighbors': neighbor_list,
            'is_coordinator': node.get('is_coordinator', False),
            'parents': child_to_parents.get(node_id, []),
            'device_reg_id': device_reg_id
        })

    for ieee, link_info in device_primary_link.items():
        d3_links.append({
            'source': link_info['target'],
            'target': ieee,
            'lqi': link_info['lqi'],
            'type': 'primary',
            'source_type': link_info['source_type']
        })

    sibling_links_added = set()
    router_ids = {n['id'] for n in d3_nodes if n['device_type'] in ('Router', 'Coordinator')}

    for node in d3_nodes:
        if node['device_type'] not in ('Router', 'Coordinator'):
            continue
        node_id = node['id']
        for neighbor in node.get('neighbors', []):
            neighbor_id = neighbor.get('ieee')
            relationship = neighbor.get('relationship', '')
            if relationship == 'Sibling' and neighbor_id in router_ids:
                link_key = tuple(sorted([node_id, neighbor_id]))
                primary_exists = any(
                    tuple(sorted([l['source'], l['target']])) == link_key
                    for l in d3_links if l['type'] == 'primary'
                )
                if primary_exists:
                    continue

                if link_key not in sibling_links_added:
                    sibling_links_added.add(link_key)
                    d3_links.append({
                        'source': node_id,
                        'target': neighbor_id,
                        'lqi': neighbor.get('lqi', 0),
                        'type': 'sibling',
                        'source_type': 'sibling'
                    })

    # Compute full path to coordinator for each device
    coordinator_id = hierarchy['coordinator']['id']
    device_paths = {}
    for node_id in nodes.keys():
        if node_id == coordinator_id:
            device_paths[node_id] = []
            continue

        path = []
        current = node_id
        visited = set()

        while current and current != coordinator_id and current not in visited:
            visited.add(current)
            if current in device_primary_link:
                link = device_primary_link[current]
                parent_id = link['target']
                parent_node = nodes.get(parent_id)
                parent_name = parent_node.get('name', parent_id) if parent_node else parent_id
                path.append({
                    'id': parent_id,
                    'name': parent_name,
                    'lqi': link['lqi'],
                    'device_type': parent_node.get('device_type') if parent_node else 'Unknown'
                })
                current = parent_id
            else:
                break

        device_paths[node_id] = path

    # Add path_to_coordinator to each node
    for node in d3_nodes:
        node['path_to_coordinator'] = device_paths.get(node['id'], [])

    export_timestamp = data.get('export_timestamp', '')
    nodes_data = hierarchy['nodes']
    total = len(nodes_data)
    routers = sum(1 for n in nodes_data.values() if n.get('device_type') == 'Router')
    end_devices = sum(1 for n in nodes_data.values() if n.get('device_type') == 'EndDevice')

    coordinator_id = hierarchy['coordinator']['id']
    storage_key = f"zha_topology_{coordinator_id[:8]}"

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ZHA Network Topology</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            overflow: hidden;
        }}
        .header {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            background: rgba(26, 26, 46, 0.95);
            backdrop-filter: blur(10px);
            padding: 12px 20px;
            z-index: 100;
            border-bottom: 1px solid #333;
        }}
        h1 {{
            text-align: center;
            margin-bottom: 6px;
            color: #00d4ff;
            font-size: 22px;
        }}
        .stats {{
            text-align: center;
            color: #888;
            font-size: 13px;
        }}
        .stats span {{
            margin: 0 10px;
        }}
        .legend {{
            display: flex;
            justify-content: center;
            gap: 12px;
            margin-top: 8px;
            flex-wrap: wrap;
            font-size: 11px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 4px;
        }}
        .legend-item.clickable {{
            cursor: pointer;
            padding: 2px 6px;
            border-radius: 4px;
            transition: opacity 0.2s, background 0.2s;
        }}
        .legend-item.clickable:hover {{
            background: rgba(255,255,255,0.1);
        }}
        .legend-item.clickable.disabled {{
            opacity: 0.4;
        }}
        .legend-item.clickable.disabled .legend-line {{
            opacity: 0.3;
        }}
        .legend-color {{
            width: 12px;
            height: 12px;
            border-radius: 3px;
        }}
        .controls {{
            display: flex;
            justify-content: center;
            gap: 8px;
            margin-top: 8px;
            flex-wrap: wrap;
            align-items: center;
        }}
        .controls button {{
            background: #333;
            color: #fff;
            border: 1px solid #555;
            padding: 5px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
            transition: all 0.2s;
        }}
        .controls button:hover {{
            background: #444;
            border-color: #00d4ff;
        }}
        .controls button.active {{
            background: #00d4ff;
            color: #000;
        }}
        .controls button.loading {{
            background: #555;
            color: #888;
            cursor: wait;
        }}
        .controls button.loading::after {{
            content: '...';
            animation: dots 1.5s steps(4, end) infinite;
        }}
        @keyframes dots {{
            0%, 20% {{ content: ''; }}
            40% {{ content: '.'; }}
            60% {{ content: '..'; }}
            80%, 100% {{ content: '...'; }}
        }}
        .controls select {{
            background: #333;
            color: #fff;
            border: 1px solid #555;
            padding: 5px 8px;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
        }}
        .controls label {{
            font-size: 11px;
            color: #888;
        }}
        .filter-group {{
            display: flex;
            align-items: center;
            gap: 5px;
            padding: 0 8px;
            border-left: 1px solid #444;
            margin-left: 4px;
        }}

        #graph {{
            position: fixed;
            top: 140px;
            left: 0;
            right: 0;
            bottom: 0;
        }}

        .node {{
            cursor: grab;
        }}
        .node:active {{
            cursor: grabbing;
        }}
        .node circle {{
            stroke-width: 3px;
            transition: all 0.2s;
        }}
        .node:hover circle {{
            filter: brightness(1.2);
        }}
        .node text {{
            font-size: 11px;
            fill: #fff;
            text-anchor: middle;
            pointer-events: none;
            text-shadow: 0 1px 3px rgba(0,0,0,0.8);
        }}
        .node .lqi-badge {{
            font-size: 9px;
            fill: #fff;
        }}
        .node .neighbor-badge {{
            cursor: pointer;
        }}

        .link {{
            fill: none;
            stroke-opacity: 0.6;
        }}

        .link.sibling {{
            stroke-dasharray: 4, 4;
            stroke-opacity: 0.3;
        }}

        .link.sibling.highlighted {{
            stroke-opacity: 0.8;
        }}

        .neighbor-link {{
            fill: none;
            stroke-dasharray: 5, 5;
            stroke-opacity: 0.8;
            pointer-events: none;
        }}

        .neighbor-link-label {{
            font-size: 10px;
            fill: #fff;
            text-anchor: middle;
            pointer-events: none;
            text-shadow: 0 1px 3px rgba(0,0,0,0.9);
        }}

        .node.selected circle {{
            stroke: #00d4ff !important;
            stroke-width: 4px !important;
            stroke-opacity: 1 !important;
            filter: drop-shadow(0 0 8px #00d4ff);
        }}

        .node.dragging circle {{
            stroke: #ff9800 !important;
            stroke-width: 4px !important;
            stroke-opacity: 1 !important;
            filter: drop-shadow(0 0 8px #ff9800);
        }}

        .link.highlighted {{
            stroke-width: 4px !important;
            stroke-opacity: 1 !important;
            filter: drop-shadow(0 0 4px rgba(255,255,255,0.5));
        }}

        .node.dimmed {{
            opacity: 0.3;
        }}

        .link.dimmed {{
            stroke-opacity: 0.1;
        }}

        .tooltip {{
            position: absolute;
            background: rgba(26, 26, 46, 0.95);
            border: 1px solid #444;
            border-radius: 6px;
            padding: 10px 14px;
            font-size: 11px;
            pointer-events: none;
            z-index: 1000;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            max-width: 280px;
            opacity: 0;
            transition: opacity 0.2s;
        }}
        .tooltip.visible {{
            opacity: 1;
            pointer-events: auto;
        }}
        .tooltip div {{
            margin: 3px 0;
            color: #aaa;
        }}
        .tooltip div span {{
            color: #fff;
        }}

        .overlay {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.85);
            z-index: 500;
        }}
        .overlay.active {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            padding-top: 60px;
            overflow-y: auto;
        }}
        .overlay-header {{
            background: #252540;
            padding: 15px 25px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
            border: 2px solid #00d4ff;
        }}
        .overlay-header h2 {{
            color: #00d4ff;
            margin-bottom: 5px;
            font-size: 18px;
        }}
        .overlay-header p {{
            color: #888;
            font-size: 12px;
        }}
        .overlay-close {{
            position: fixed;
            top: 15px;
            right: 25px;
            font-size: 28px;
            color: #fff;
            cursor: pointer;
            z-index: 600;
        }}
        .overlay-close:hover {{
            color: #00d4ff;
        }}
        .neighbor-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 12px;
            max-width: 1000px;
            width: 90%;
            padding: 15px;
        }}
        .neighbor-card {{
            background: #252540;
            border-radius: 8px;
            padding: 12px;
            border: 2px solid #444;
            transition: all 0.2s;
        }}
        .neighbor-card:hover {{
            border-color: #00d4ff;
        }}
        .neighbor-card .name {{
            font-weight: 600;
            font-size: 13px;
            margin-bottom: 6px;
            color: #fff;
        }}
        .neighbor-card .lqi-bar {{
            height: 6px;
            background: #333;
            border-radius: 3px;
            overflow: hidden;
            margin: 6px 0;
        }}
        .neighbor-card .lqi-bar-fill {{
            height: 100%;
            border-radius: 3px;
        }}
        .neighbor-card .details {{
            font-size: 10px;
            color: #888;
        }}
        .neighbor-card .lqi-value {{
            font-size: 16px;
            font-weight: bold;
        }}
        .neighbor-card.not-in-network {{
            opacity: 0.5;
            border-style: dashed;
        }}

        .hidden {{
            display: none !important;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>ZHA Network Topology</h1>
        <div class="stats">
            <span>Total: {total} devices</span>
            <span id="visibleCount" style="color:#00d4ff">(Showing: {total})</span>
            <span>Coordinator: 1</span>
            <span>Routers: {routers}</span>
            <span>End Devices: {end_devices}</span>
            <span style="color:#666">Export: {export_timestamp[:19] if export_timestamp else 'N/A'}</span>
        </div>
        <div class="legend">
            <div class="legend-item"><div class="legend-color" style="background:#00d4ff"></div> Coordinator</div>
            <div class="legend-item"><div class="legend-color" style="background:#8BC34A"></div> Router</div>
            <div class="legend-item"><div class="legend-color" style="background:#FFC107"></div> End Device</div>
            <div class="legend-item" style="margin-left:15px"><div class="legend-color" style="background:#4CAF50"></div> LQI 150+</div>
            <div class="legend-item"><div class="legend-color" style="background:#8BC34A"></div> LQI 100+</div>
            <div class="legend-item"><div class="legend-color" style="background:#FFC107"></div> LQI 50+</div>
            <div class="legend-item"><div class="legend-color" style="background:#F44336"></div> LQI &lt;50</div>
            <div class="legend-item clickable" data-link-type="route" style="margin-left:15px"><div class="legend-line" style="width:20px;height:3px;background:#00d4ff;margin-right:5px"></div> Route</div>
            <div class="legend-item clickable" data-link-type="parent"><div class="legend-line" style="width:20px;height:3px;background:#8BC34A;margin-right:5px"></div> Parent</div>
            <div class="legend-item clickable" data-link-type="neighbor"><div class="legend-line" style="width:20px;height:3px;background:#FFC107;margin-right:5px"></div> Neighbor</div>
            <div class="legend-item clickable" data-link-type="fallback"><div class="legend-line" style="width:20px;height:3px;background:#666;margin-right:5px"></div> Fallback</div>
            <div class="legend-item clickable disabled" data-link-type="sibling"><div class="legend-line" style="width:20px;border-top:2px dashed #888;margin-right:5px"></div> Sibling</div>
        </div>
        <div class="controls">
            <button onclick="refreshData()" id="refreshBtn">Refresh Data</button>
            <button onclick="resetPositions()">Reset Layout</button>
            <button onclick="savePositions()">Save Positions</button>
            <button onclick="toggleEndDevices(this)" class="active" id="toggleEndBtn">Show End Devices</button>
            <div class="filter-group">
                <label>Last seen:</label>
                <select id="timeFilter" onchange="applyTimeFilter()">
                    <option value="0">All devices</option>
                    <option value="60">Last 1 hour</option>
                    <option value="360">Last 6 hours</option>
                    <option value="1440">Last 24 hours</option>
                    <option value="10080">Last 7 days</option>
                </select>
            </div>
            <div class="filter-group">
                <label>Zoom:</label>
                <button onclick="zoomIn()">+</button>
                <button onclick="zoomOut()">-</button>
                <button onclick="zoomReset()">Reset</button>
            </div>
        </div>
    </div>

    <div id="graph"></div>
    <div class="tooltip" id="tooltip"></div>

    <div class="overlay" id="neighborOverlay">
        <span class="overlay-close" onclick="closeOverlay()">&times;</span>
        <div class="overlay-header">
            <h2 id="overlayTitle">Neighbor Table</h2>
            <p id="overlaySubtitle"></p>
        </div>
        <div class="neighbor-grid" id="neighborGrid"></div>
    </div>

    <script>
        const nodesData = {json.dumps(d3_nodes)};
        const linksData = {json.dumps(d3_links)};
        const exportTime = new Date("{export_timestamp}");
        const storageKey = "{storage_key}";

        const linkTypeVisibility = {{
            route: true,
            parent: true,
            neighbor: true,
            fallback: true,
            sibling: false
        }};

        function toggleLinkType(linkType) {{
            linkTypeVisibility[linkType] = !linkTypeVisibility[linkType];

            const legendItem = document.querySelector(`.legend-item[data-link-type="${{linkType}}"]`);
            if (legendItem) {{
                legendItem.classList.toggle('disabled', !linkTypeVisibility[linkType]);
            }}

            updateLinkVisibility();
        }}

        function updateLinkVisibility() {{
            d3.selectAll('.primary-links-group path')
                .style('display', d => linkTypeVisibility[d.source_type] ? null : 'none');

            d3.selectAll('.sibling-links-group path')
                .style('display', d => linkTypeVisibility.sibling ? null : 'none');
        }}

        document.addEventListener('DOMContentLoaded', () => {{
            document.querySelectorAll('.legend-item.clickable').forEach(item => {{
                item.addEventListener('click', () => {{
                    const linkType = item.dataset.linkType;
                    if (linkType) {{
                        toggleLinkType(linkType);
                    }}
                }});
            }});
        }});

        const nodeMap = {{}};
        nodesData.forEach(n => nodeMap[n.id] = n);

        const container = document.getElementById('graph');
        let width = container.clientWidth;
        let height = container.clientHeight;

        const svg = d3.select('#graph')
            .append('svg')
            .attr('width', '100%')
            .attr('height', '100%')
            .attr('viewBox', [0, 0, width, height]);

        const g = svg.append('g');

        const zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on('zoom', (event) => {{
                g.attr('transform', event.transform);
            }});

        svg.call(zoom);

        function getNodeColor(d) {{
            if (d.is_coordinator) return '#00d4ff';
            if (d.device_type === 'Router') return '#8BC34A';
            return '#FFC107';
        }}

        function getLqiColor(lqi) {{
            if (lqi === null || lqi === undefined) return '#888';
            if (lqi >= 150) return '#4CAF50';
            if (lqi >= 100) return '#8BC34A';
            if (lqi >= 50) return '#FFC107';
            return '#F44336';
        }}

        function getNodeRadius(d) {{
            if (d.is_coordinator) return 30;
            if (d.device_type === 'Router') return 22;
            return 16;
        }}

        const simulation = d3.forceSimulation(nodesData)
            .force('link', d3.forceLink(linksData).id(d => d.id).distance(100).strength(0.5))
            .force('charge', d3.forceManyBody().strength(-300))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collision', d3.forceCollide().radius(d => getNodeRadius(d) + 10));

        function loadPositions() {{
            const saved = localStorage.getItem(storageKey);
            if (saved) {{
                try {{
                    const positions = JSON.parse(saved);
                    nodesData.forEach(node => {{
                        if (positions[node.id]) {{
                            node.x = positions[node.id].x;
                            node.y = positions[node.id].y;
                            node.fx = positions[node.id].fx;
                            node.fy = positions[node.id].fy;
                        }}
                    }});
                    return true;
                }} catch (e) {{
                    console.error('Failed to load positions:', e);
                }}
            }}
            return false;
        }}

        function savePositions() {{
            const positions = {{}};
            nodesData.forEach(node => {{
                positions[node.id] = {{
                    x: node.x,
                    y: node.y,
                    fx: node.fx,
                    fy: node.fy
                }};
            }});
            localStorage.setItem(storageKey, JSON.stringify(positions));
            showToast('Positions saved!');
        }}

        function showToast(message) {{
            const toast = document.createElement('div');
            toast.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#00d4ff;color:#000;padding:10px 20px;border-radius:4px;font-size:14px;z-index:9999;';
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 2000);
        }}

        function resetPositions() {{
            localStorage.removeItem(storageKey);
            nodesData.forEach(node => {{
                node.fx = null;
                node.fy = null;
            }});
            simulation.alpha(1).restart();
            showToast('Layout reset!');
        }}

        const hasPositions = loadPositions();

        function getRectilinearPath(source, target) {{
            const midY = (source.y + target.y) / 2;
            return `M${{source.x}},${{source.y}} L${{source.x}},${{midY}} L${{target.x}},${{midY}} L${{target.x}},${{target.y}}`;
        }}

        const primaryLinks = linksData.filter(l => l.type === 'primary');
        const siblingLinks = linksData.filter(l => l.type === 'sibling');

        function getSourceTypeColor(sourceType) {{
            switch(sourceType) {{
                case 'route': return '#00d4ff';
                case 'parent': return '#8BC34A';
                case 'neighbor': return '#FFC107';
                case 'fallback': return '#666';
                case 'sibling': return '#888';
                default: return '#888';
            }}
        }}

        const siblingLink = g.append('g')
            .attr('class', 'sibling-links-group')
            .selectAll('path')
            .data(siblingLinks)
            .join('path')
            .attr('class', 'link sibling')
            .attr('stroke', d => getSourceTypeColor(d.source_type))
            .attr('stroke-width', 1)
            .style('display', 'none');

        const link = g.append('g')
            .attr('class', 'primary-links-group')
            .selectAll('path')
            .data(primaryLinks)
            .join('path')
            .attr('class', d => `link primary ${{d.source_type}}`)
            .attr('stroke', d => getSourceTypeColor(d.source_type))
            .attr('stroke-width', d => {{
                if (!d.lqi) return 2;
                if (d.lqi >= 150) return 3;
                if (d.lqi >= 100) return 2.5;
                if (d.lqi >= 50) return 2;
                return 1.5;
            }});

        const neighborLinksGroup = g.append('g').attr('class', 'neighbor-links-group');
        const neighborLabelsGroup = g.append('g').attr('class', 'neighbor-labels-group');

        const node = g.append('g')
            .selectAll('g')
            .data(nodesData)
            .join('g')
            .attr('class', 'node')
            .call(d3.drag()
                .on('start', dragstarted)
                .on('drag', dragged)
                .on('end', dragended));

        node.append('circle')
            .attr('r', d => getNodeRadius(d))
            .attr('fill', d => getNodeColor(d))
            .attr('stroke', d => d.available === false ? '#F44336' : '#fff')
            .attr('stroke-opacity', d => d.available === false ? 1 : 0.3);

        node.append('text')
            .attr('dy', d => getNodeRadius(d) + 14)
            .text(d => d.name.length > 15 ? d.name.substring(0, 14) + '...' : d.name);

        node.filter(d => d.lqi !== null)
            .append('text')
            .attr('class', 'lqi-badge')
            .attr('dy', 4)
            .attr('fill', d => getLqiColor(d.lqi))
            .text(d => d.lqi);

        node.filter(d => d.neighbors && d.neighbors.length > 0)
            .append('g')
            .attr('class', 'neighbor-badge')
            .attr('transform', d => `translate(${{getNodeRadius(d) - 5}}, ${{-getNodeRadius(d) + 5}})`)
            .on('click', (event, d) => {{
                event.stopPropagation();
                showNeighborOverlay(d);
            }})
            .call(g => {{
                g.append('circle')
                    .attr('r', 10)
                    .attr('fill', '#00d4ff')
                    .attr('stroke', '#fff')
                    .attr('stroke-width', 2);
                g.append('text')
                    .attr('dy', 4)
                    .attr('text-anchor', 'middle')
                    .attr('fill', '#000')
                    .attr('font-size', '10px')
                    .attr('font-weight', 'bold')
                    .text(d => d.neighbors.length);
            }});

        let selectedNode = null;

        function updateNeighborLinks() {{
            if (!selectedNode) return;

            const selectedData = selectedNode;
            neighborLinksGroup.selectAll('path')
                .attr('d', d => {{
                    const targetNode = nodesData.find(n => n.id === d.ieee);
                    if (!targetNode) return '';
                    return `M${{selectedData.x}},${{selectedData.y}} L${{targetNode.x}},${{targetNode.y}}`;
                }});

            neighborLabelsGroup.selectAll('text')
                .attr('x', d => {{
                    const targetNode = nodesData.find(n => n.id === d.ieee);
                    if (!targetNode) return 0;
                    return (selectedData.x + targetNode.x) / 2;
                }})
                .attr('y', d => {{
                    const targetNode = nodesData.find(n => n.id === d.ieee);
                    if (!targetNode) return 0;
                    return (selectedData.y + targetNode.y) / 2 - 5;
                }});
        }}

        function showNeighborLinks(d) {{
            selectedNode = d;

            node.classed('dimmed', n => n.id !== d.id);
            link.classed('dimmed', true);
            siblingLink.classed('dimmed', true);

            node.classed('selected', n => n.id === d.id);

            link.classed('highlighted', l => l.source.id === d.id || l.target.id === d.id);
            link.classed('dimmed', l => l.source.id !== d.id && l.target.id !== d.id);

            siblingLink.classed('highlighted', l => l.source.id === d.id || l.target.id === d.id);
            siblingLink.classed('dimmed', l => l.source.id !== d.id && l.target.id !== d.id);

            const neighborIeees = new Set(d.neighbors.map(n => n.ieee));

            node.classed('dimmed', n => {{
                if (n.id === d.id) return false;
                return !neighborIeees.has(n.id);
            }});

            const neighborLinks = neighborLinksGroup.selectAll('path')
                .data(d.neighbors.filter(n => nodesData.find(node => node.id === n.ieee)))
                .join('path')
                .attr('class', 'neighbor-link')
                .attr('stroke', n => getLqiColor(n.lqi))
                .attr('stroke-width', 2);

            const neighborLabels = neighborLabelsGroup.selectAll('text')
                .data(d.neighbors.filter(n => nodesData.find(node => node.id === n.ieee)))
                .join('text')
                .attr('class', 'neighbor-link-label')
                .text(n => n.lqi);

            updateNeighborLinks();
        }}

        function clearSelection() {{
            selectedNode = null;
            node.classed('selected', false);
            node.classed('dimmed', false);
            link.classed('dimmed', false);
            link.classed('highlighted', false);
            siblingLink.classed('dimmed', false);
            siblingLink.classed('highlighted', false);
            neighborLinksGroup.selectAll('*').remove();
            neighborLabelsGroup.selectAll('*').remove();
        }}

        svg.on('click', () => {{
            clearSelection();
        }});

        const tooltip = document.getElementById('tooltip');
        let tooltipTimeout = null;
        let currentTooltipPos = {{ x: 0, y: 0 }};

        function showTooltip(content, x, y) {{
            if (tooltipTimeout) {{
                clearTimeout(tooltipTimeout);
                tooltipTimeout = null;
            }}
            tooltip.innerHTML = content;
            tooltip.style.left = (x + 15) + 'px';
            tooltip.style.top = (y + 15) + 'px';
            currentTooltipPos = {{ x: x + 15, y: y + 15 }};
            tooltip.classList.add('visible');
        }}

        function hideTooltip() {{
            tooltipTimeout = setTimeout(() => {{
                tooltip.classList.remove('visible');
            }}, 100);
        }}

        tooltip.addEventListener('mouseenter', () => {{
            if (tooltipTimeout) {{
                clearTimeout(tooltipTimeout);
                tooltipTimeout = null;
            }}
        }});
        tooltip.addEventListener('mouseleave', () => {{
            hideTooltip();
        }});

        node.on('mouseenter', (event, d) => {{
            let parentInfo = 'None (Coordinator)';
            const sourceTypeLabels = {{
                'route': 'Route Table',
                'parent': 'Parent Relationship',
                'neighbor': 'Strongest Neighbor',
                'fallback': 'Fallback',
                'sibling': 'Sibling'
            }};
            const sourceTypeColors = {{
                'route': '#00d4ff',
                'parent': '#8BC34A',
                'neighbor': '#FFC107',
                'fallback': '#666',
                'sibling': '#888'
            }};
            if (d.parents && d.parents.length > 0) {{
                parentInfo = d.parents.map(p => {{
                    const sourceLabel = sourceTypeLabels[p.source_type] || p.source_type;
                    const sourceColor = sourceTypeColors[p.source_type] || '#888';
                    return `${{p.name}}${{p.lqi ? ` (LQI: ${{p.lqi}})` : ''}} <span style="color:${{sourceColor}};font-size:9px">[${{sourceLabel}}]</span>`;
                }}).join(', ');
            }}

            // Build full path to coordinator
            let pathInfo = '';
            if (d.is_coordinator) {{
                pathInfo = '<span style="color:#00d4ff">This is the Coordinator</span>';
            }} else if (d.path_to_coordinator && d.path_to_coordinator.length > 0) {{
                const deviceName = d.user_given_name || d.name;
                const pathParts = [`<span style="color:#FFC107">${{deviceName}}</span>`];
                d.path_to_coordinator.forEach(hop => {{
                    const lqiStr = hop.lqi ? `<span style="color:${{getLqiColor(hop.lqi)}}">${{hop.lqi}}</span>` : '?';
                    const hopColor = hop.device_type === 'Coordinator' ? '#00d4ff' : '#8BC34A';
                    pathParts.push(`—(${{lqiStr}})→ <span style="color:${{hopColor}}">${{hop.name}}</span>`);
                }});
                pathInfo = pathParts.join(' ');
            }} else {{
                pathInfo = '<span style="color:#666">Unknown path</span>';
            }}

            // Construct HA device URL using current hostname (assumes HA is on port 8123)
            const haBaseUrl = `${{window.location.protocol}}//${{window.location.hostname}}:8123`;
            const haDeviceUrl = d.device_reg_id ? `${{haBaseUrl}}/config/devices/device/${{d.device_reg_id}}` : '';

            const content = `
                <div><strong style="color:#00d4ff">${{d.user_given_name || d.name}}</strong></div>
                ${{d.user_given_name ? `<div style="color:#888;font-size:10px">${{d.name}}</div>` : ''}}
                <div>Type: <span>${{d.device_type}}</span></div>
                <div>LQI: <span style="color:${{getLqiColor(d.lqi)}}">${{d.lqi !== null ? d.lqi : 'N/A'}}</span></div>
                <div>Path: <span style="font-size:11px">${{pathInfo}}</span></div>
                <div>Connected via: <span>${{parentInfo}}</span></div>
                <div>Manufacturer: <span>${{d.manufacturer || 'Unknown'}}</span></div>
                <div>Model: <span>${{d.model || 'Unknown'}}</span></div>
                <div>Last seen: <span>${{formatLastSeen(d.last_seen)}}</span></div>
                ${{d.neighbors && d.neighbors.length > 0 ? `<div>Neighbors: <span>${{d.neighbors.length}} (click to show)</span></div>` : ''}}
                ${{haDeviceUrl ? `<div style="margin-top:5px"><a href="${{haDeviceUrl}}" target="_blank" style="color:#00d4ff;text-decoration:none;">Open in Home Assistant &rarr;</a></div>` : ''}}
                <div style="color:#666;margin-top:5px;font-size:10px">Drag to move | Click to select</div>
            `;
            showTooltip(content, event.pageX, event.pageY);
        }})
        .on('mousemove', (event) => {{
            tooltip.style.left = (event.pageX + 15) + 'px';
            tooltip.style.top = (event.pageY + 15) + 'px';
        }})
        .on('mouseleave', () => {{
            hideTooltip();
        }})
        .on('click', (event, d) => {{
            event.stopPropagation();
            if (d.neighbors && d.neighbors.length > 0) {{
                if (selectedNode && selectedNode.id === d.id) {{
                    clearSelection();
                }} else {{
                    clearSelection();
                    showNeighborLinks(d);
                }}
            }}
        }});

        function highlightConnectedLinks(nodeId, highlight) {{
            link.classed('highlighted', l => {{
                if (!highlight) return false;
                return l.source.id === nodeId || l.target.id === nodeId;
            }});
            siblingLink.classed('highlighted', l => {{
                if (!highlight) return false;
                return l.source.id === nodeId || l.target.id === nodeId;
            }});
        }}

        function dragstarted(event, d) {{
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
            d3.select(event.sourceEvent.target.parentNode).classed('dragging', true);
            highlightConnectedLinks(d.id, true);
            showNeighborLinks(d);
        }}

        function dragged(event, d) {{
            d.fx = event.x;
            d.fy = event.y;
        }}

        function dragended(event, d) {{
            if (!event.active) simulation.alphaTarget(0);
            d3.select(event.sourceEvent.target.parentNode).classed('dragging', false);
            highlightConnectedLinks(d.id, false);
            clearSelection();
        }}

        simulation.on('tick', () => {{
            link.attr('d', d => getRectilinearPath(d.source, d.target));

            siblingLink.attr('d', d => `M${{d.source.x}},${{d.source.y}} L${{d.target.x}},${{d.target.y}}`);

            node.attr('transform', d => `translate(${{d.x}},${{d.y}})`);

            updateNeighborLinks();
        }});

        if (hasPositions) {{
            simulation.alpha(0.1);
        }}

        function formatLastSeen(lastSeen) {{
            if (!lastSeen) return 'Never';
            const date = new Date(lastSeen);
            const diffMs = exportTime - date;
            const diffMins = Math.floor(diffMs / 60000);
            if (diffMins < 1) return 'Just now';
            if (diffMins < 60) return `${{diffMins}}m ago`;
            const diffHours = Math.floor(diffMins / 60);
            if (diffHours < 24) return `${{diffHours}}h ago`;
            const diffDays = Math.floor(diffHours / 24);
            return `${{diffDays}}d ago`;
        }}

        function getMinutesSinceLastSeen(lastSeen) {{
            if (!lastSeen) return Infinity;
            const date = new Date(lastSeen);
            return Math.floor((exportTime - date) / 60000);
        }}

        let showEndDevices = true;
        let timeFilterMinutes = 0;

        function toggleEndDevices(btn) {{
            showEndDevices = !showEndDevices;
            btn.classList.toggle('active');
            btn.textContent = showEndDevices ? 'Show End Devices' : 'Hide End Devices';
            applyFilters();
        }}

        function applyTimeFilter() {{
            timeFilterMinutes = parseInt(document.getElementById('timeFilter').value);
            applyFilters();
        }}

        function applyFilters() {{
            let visibleCount = 0;

            node.each(function(d) {{
                const minutesAgo = getMinutesSinceLastSeen(d.last_seen);
                const passesTimeFilter = timeFilterMinutes === 0 || minutesAgo <= timeFilterMinutes || isNaN(minutesAgo);
                const passesTypeFilter = showEndDevices || d.device_type !== 'EndDevice';
                const visible = passesTimeFilter && passesTypeFilter;

                d.visible = visible;
                d3.select(this).classed('hidden', !visible);

                if (visible) visibleCount++;
            }});

            link.classed('hidden', d => !d.source.visible || !d.target.visible);

            document.getElementById('visibleCount').textContent = `(Showing: ${{visibleCount}})`;
        }}

        function zoomIn() {{
            svg.transition().call(zoom.scaleBy, 1.3);
        }}

        function zoomOut() {{
            svg.transition().call(zoom.scaleBy, 0.7);
        }}

        function zoomReset() {{
            svg.transition().call(zoom.transform, d3.zoomIdentity);
        }}

        function showNeighborOverlay(nodeData) {{
            const overlay = document.getElementById('neighborOverlay');
            const title = document.getElementById('overlayTitle');
            const subtitle = document.getElementById('overlaySubtitle');
            const grid = document.getElementById('neighborGrid');

            title.textContent = `${{nodeData.name}} - Neighbor Table`;
            subtitle.textContent = `${{nodeData.neighbors.length}} neighbors | Device LQI: ${{nodeData.lqi || 'N/A'}}`;

            const sortedNeighbors = [...nodeData.neighbors].sort((a, b) => (b.lqi || 0) - (a.lqi || 0));

            let html = '';
            for (const neighbor of sortedNeighbors) {{
                const neighborNode = nodeMap[neighbor.ieee];
                const neighborName = neighborNode ? neighborNode.name : neighbor.ieee.substring(0, 17) + '...';
                const lqiColor = getLqiColor(neighbor.lqi);
                const lqiPercent = Math.round((neighbor.lqi / 255) * 100);
                const notInNetwork = !neighborNode ? 'not-in-network' : '';

                html += `
                    <div class="neighbor-card ${{notInNetwork}}">
                        <div class="name">${{neighborName}}</div>
                        <div class="lqi-value" style="color:${{lqiColor}}">${{neighbor.lqi}}</div>
                        <div class="lqi-bar">
                            <div class="lqi-bar-fill" style="width:${{lqiPercent}}%;background:${{lqiColor}}"></div>
                        </div>
                        <div class="details">
                            <div>Relationship: <span>${{neighbor.relationship}}</span></div>
                            <div>Type: <span>${{neighbor.device_type}}</span></div>
                            ${{!neighborNode ? '<div style="color:#F44336">Not in current network</div>' : ''}}
                        </div>
                    </div>
                `;
            }}

            grid.innerHTML = html;
            overlay.classList.add('active');
        }}

        function closeOverlay() {{
            document.getElementById('neighborOverlay').classList.remove('active');
        }}

        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape') closeOverlay();
        }});

        document.getElementById('neighborOverlay').addEventListener('click', (e) => {{
            if (e.target.id === 'neighborOverlay') closeOverlay();
        }});

        window.addEventListener('resize', () => {{
            width = container.clientWidth;
            height = container.clientHeight;
            svg.attr('viewBox', [0, 0, width, height]);
            simulation.force('center', d3.forceCenter(width / 2, height / 2));
            simulation.alpha(0.3).restart();
        }});

        setInterval(() => {{
            const positions = {{}};
            let hasFixed = false;
            nodesData.forEach(node => {{
                if (node.fx !== null && node.fx !== undefined) {{
                    hasFixed = true;
                    positions[node.id] = {{
                        x: node.x,
                        y: node.y,
                        fx: node.fx,
                        fy: node.fy
                    }};
                }}
            }});
            if (hasFixed) {{
                localStorage.setItem(storageKey, JSON.stringify(positions));
            }}
        }}, 10000);

        async function refreshData() {{
            const btn = document.getElementById('refreshBtn');
            const originalText = btn.textContent;
            btn.textContent = 'Refreshing';
            btn.classList.add('loading');
            btn.disabled = true;

            try {{
                const response = await fetch('/refresh', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }}
                }});

                if (response.ok) {{
                    window.location.reload();
                }} else {{
                    const error = await response.text();
                    alert('Refresh failed: ' + error);
                    btn.textContent = originalText;
                    btn.classList.remove('loading');
                    btn.disabled = false;
                }}
            }} catch (err) {{
                alert('Refresh failed: ' + err.message);
                btn.textContent = originalText;
                btn.classList.remove('loading');
                btn.disabled = false;
            }}
        }}
    </script>
</body>
</html>
'''

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    return output_file


def find_latest_export():
    """Find the most recent export file."""
    exports = sorted(DATA_DIR.glob('zha_full_export_*.json'), reverse=True)
    if not exports:
        return None
    return str(exports[0])


def generate_visualization(json_file: str = None) -> str:
    """Generate visualization from an export file."""
    if json_file is None:
        json_file = find_latest_export()

    if not json_file:
        raise FileNotFoundError("No ZHA export file found")

    print(f"Loading: {json_file}")
    data = load_topology(json_file)

    print("Building hierarchy...")
    hierarchy = build_hierarchy(data)

    if not hierarchy:
        raise ValueError("Could not build hierarchy from topology data")

    output_file = str(DATA_DIR / 'topology.html')
    print(f"Generating: {output_file}")
    generate_html(hierarchy, data, output_file)

    return output_file


def main():
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
    else:
        json_file = find_latest_export()

    if not json_file:
        print("Error: No zha_full_export_*.json file found")
        print("Usage: python visualize.py [export_file.json]")
        sys.exit(1)

    output_file = generate_visualization(json_file)
    print(f"\nDone! Generated: {output_file}")


if __name__ == "__main__":
    main()
