"""
ZHA Network Topology Visualizer
Generates an interactive HTML visualization using D3.js with draggable nodes.
Adapted for Home Assistant Add-on environment.
"""

import json
import os
import sys
import yaml
from pathlib import Path
from collections import defaultdict

# Data directory for persistence
DATA_DIR = Path('/data')

# Add-on version from config
def get_addon_version():
    """Read add-on version from config.yaml."""
    config_paths = [
        Path('/config.yaml'),  # Standard add-on location
        Path(__file__).parent.parent.parent / 'config.yaml',  # Development
    ]
    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    return config.get('version', 'unknown')
            except Exception:
                pass
    return 'unknown'

ADDON_VERSION = get_addon_version()


# --- Source-route layer (zha_routes) -------------------------------------
# Plain strings (not f-strings) injected into the page, so braces are literal.
# Only route CSS is conditional; ROUTE_JS is always included because the main
# script calls its hooks, which are no-ops when routesMeta is null.

ROUTE_CSS = """
        .route-only { display: none; }
        body.routes-on .route-only { display: inline; }
        .route-seg { fill: none; stroke: #E040FB; stroke-linecap: round; pointer-events: stroke; cursor: help; }
        .route-seg.startup { stroke-dasharray: 5, 4; }
        .route-seg.route-dim { stroke-opacity: 0.08 !important; }
        .route-seg.route-hl { stroke: #FF80FF; stroke-opacity: 1 !important; filter: drop-shadow(0 0 4px #E040FB); }
        .route-load-badge text { font-size: 6px; font-weight: bold; fill: #fff; text-anchor: middle; pointer-events: none; }
        .route-flags { font-size: 9px; font-weight: bold; text-anchor: end; pointer-events: none; text-shadow: 0 1px 2px #000; }
        .top-load-ring { fill: none; stroke: #FFD54F; stroke-width: 2.5px; stroke-dasharray: 3, 2; pointer-events: none; }
        .route-hist { font-size: 10px; color: #aaa; margin-left: 10px; }
        .link.primary.zroute_startup { stroke-dasharray: 4, 3; stroke-opacity: 0.5; }
        .conflict-link { fill: none; stroke: #FFB300; stroke-width: 1.6px; stroke-dasharray: 3, 3;
                         stroke-opacity: 0.9; pointer-events: stroke; cursor: help; }
        body.tree-neighbour .conflict-links-group { display: none; }
        .nh-row { font-size: 10px; margin-left: 10px; color: #aaa; }
        .nh-row.used { color: #fff; }
"""

ROUTE_JS = r"""
        // ---------------- Source-route layer (zha_routes) ----------------
        // Thresholds for the per-device flags. Tune here.
        const FLAP_CHANGES_PER_HOUR = 5;   // flapping: route changes/hour since listening started
        const SILENT_HOURS = 6;            // silent: no route report for this long (or startup route only)

        let routesOn = !!routesMeta;

        function routeDefs() {
            // Our own <defs> as a direct child of the graph SVG. A bare
            // svg.select('defs') would find the floorplan's <defs> (inside its
            // foreignObject), where markers never render.
            return topoDefs();
        }
        let routeSelectedId = null;
        let routeSeg = null;
        let topLoadIds = new Set();

        function routeListenHours() {
            if (!routesMeta || !routesMeta.listening_since) return null;
            const h = (exportTime - new Date(routesMeta.listening_since)) / 3600000;
            return isNaN(h) ? null : h;
        }

        function routeFlags(d) {
            const r = d.route;
            if (!routesMeta || d.is_coordinator) return {};
            if (!r) return (d.next_hop && d.next_hop.verdict === 'conflict') ? { conflict: true } : {};
            const flags = {};
            if (r.relays === null) flags.noRoute = true;
            if (d.next_hop && d.next_hop.verdict === 'conflict') flags.conflict = true;
            const hrs = routeListenHours();
            if (hrs && r.changes / Math.max(hrs, 1) > FLAP_CHANGES_PER_HOUR) flags.flapping = true;
            const reportAgeH = r.last_report ? (exportTime - new Date(r.last_report)) / 3600000 : Infinity;
            if (r.source === 'database' || !(reportAgeH <= SILENT_HOURS)) flags.silent = true;
            return flags;
        }

        function fmtAgo(iso) {
            if (!iso) return 'never';
            const mins = Math.floor((exportTime - new Date(iso)) / 60000);
            if (isNaN(mins)) return 'unknown';
            if (mins < 1) return 'just now';
            if (mins < 60) return mins + 'm ago';
            const h = Math.floor(mins / 60);
            if (h < 48) return h + 'h ' + (mins % 60) + 'm ago';
            return Math.floor(h / 24) + 'd ago';
        }

        function escHtml(s) {
            return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
        }

        function routePathHtml(names, deviceName) {
            if (names === null || names === undefined) return '<span style="color:#F44336">no route known</span>';
            const parts = [`<span style="color:#FFC107">${escHtml(deviceName)}</span>`];
            names.forEach(n => parts.push(`<span style="color:#CE93D8">${escHtml(n)}</span>`));
            parts.push('<span style="color:#00d4ff">Coordinator</span>');
            return parts.join(' &rarr; ') + (names.length === 0 ? ' <span style="color:#888">(direct)</span>' : '');
        }

        const NH_KIND = { record: 'Route record', table: 'Route table', parent: 'Parent' };
        const NH_STATUS = {
            used: '<span style="color:#4CAF50">← used</span>',
            agree: '<span style="color:#4CAF50">✓ agrees</span>',
            alternating: '<span style="color:#90CAF9" title="Differs, but this hop appears in the device\'s recent route history: normal path switching">⇄ alternating</span>',
            outdated: '<span style="color:#9E9E9E" title="Differs, but one side is stale data">differs (stale)</span>',
            conflict: '<span style="color:#FFB300">⚠ conflicts</span>',
        };
        const NH_VERDICT = {
            agree: '<span style="color:#4CAF50">✓ Sources agree</span>',
            single: '<span style="color:#888">One source only</span>',
            alternating: '<span style="color:#90CAF9">⇄ Alternating between these hops (normal switching)</span>',
            outdated: '<span style="color:#9E9E9E">Sources differ, but the other one is stale</span>',
            conflict: '<span style="color:#FFB300">⚠ Conflict: two current sources point at different next hops, and the other hop isn\'t in recent route history</span>',
        };

        function nextHopHtml(d) {
            const nh = d.next_hop;
            if (!nh || d.is_coordinator) return '';
            if (nh.verdict === 'none') {
                return `<div style="margin-top:4px">Next hop: <span style="color:#888">no direct evidence (tree line is ${escHtml(nh.fallback)})</span></div>`;
            }
            const rows = nh.sources.map(src => {
                const age = src.age ? `, ${fmtAgo(src.age)}` : '';
                return `<div class="nh-row${src.status === 'used' ? ' used' : ''}">${NH_KIND[src.kind] || src.kind}: `
                    + `<span style="color:#CE93D8">${escHtml(src.name)}</span> `
                    + `<span style="color:#666">(${escHtml(src.detail)}${age})</span> ${NH_STATUS[src.status] || ''}</div>`;
            }).join('');
            return `<div style="margin-top:4px;border-top:1px solid #333;padding-top:4px">Next hop:</div>${rows}`
                + `<div class="nh-row">${NH_VERDICT[nh.verdict] || ''}</div>`;
        }

        function routeDetailHtml(d) {
            if (!routesMeta) return '';
            let html = nextHopHtml(d);
            if (d.route_load > 0 || d.route_load_startup > 0) {
                const top = topLoadIds.has(d.id) ? ' <span style="color:#FFD54F">(busiest router)</span>' : '';
                const startup = d.route_load_startup
                    ? `, <span style="color:#9E9E9E" title="Devices whose only known route is the one stored at startup (age unknown)">${d.route_load_startup} startup only</span>`
                    : '';
                html += `<div>Routes through this node: <span style="color:#E040FB">${d.route_load || 0} live</span>${startup}${top}</div>`;
            }
            if (d.is_coordinator) return html;
            const r = d.route;
            if (!r) {
                return html + '<div style="color:#666">Route: not tracked by zha_routes</div>';
            }
            const name = d.user_given_name || d.name;
            const flags = routeFlags(d);
            const hrs = routeListenHours();
            const rate = hrs ? (r.changes / Math.max(hrs, 1)).toFixed(1) : '?';
            const flagText = [
                flags.flapping ? '<span style="color:#FF9800">&#8623; flapping</span>' : '',
                flags.silent ? '<span style="color:#9E9E9E">z silent</span>' : '',
                flags.noRoute ? '<span style="color:#F44336">&#8709; no route</span>' : '',
                flags.conflict ? '<span style="color:#FFB300">&#9888; next-hop conflict</span>' : '',
            ].filter(Boolean).join(' ');
            const sourceText = r.source === 'live'
                ? '<span style="color:#4CAF50">live</span>'
                : '<span style="color:#9E9E9E">startup only (age unknown)</span>';
            html += `<div style="margin-top:4px;border-top:1px solid #333;padding-top:4px">Route <span style="color:#555;font-size:9px">(zha_routes)</span>: <span style="font-size:11px">${routePathHtml(r.relay_names, name)}</span></div>`;
            if (r.unresolved && r.unresolved.length) {
                html += `<div style="color:#FF9800;font-size:10px">Unknown relay NWK: ${r.unresolved.map(escHtml).join(', ')}</div>`;
            }
            html += `<div>Hops: <span>${r.hops !== null ? r.hops : 'n/a'}</span> | Source: ${sourceText}</div>`;
            html += `<div>Last route report: <span>${fmtAgo(r.last_report)}</span>${r.last_change ? ` | changed ${fmtAgo(r.last_change)}` : ''}</div>`;
            html += `<div>Changes: <span>${r.changes}</span> since listening started <span style="color:#666">(${rate}/h, ${r.reports} reports)</span></div>`;
            if (flagText) html += `<div>Flags: ${flagText}</div>`;
            if (r.history && r.history.length) {
                const recent = r.history.slice(-8).reverse();
                html += `<div style="margin-top:2px">Recent changes <span style="color:#666">(${r.history.length} kept)</span>:</div>`;
                html += recent.map(h => {
                    const t = h.t ? new Date(h.t).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) : '?';
                    const p = h.names === null ? 'no route' : (h.names.length ? h.names.map(escHtml).join(' &rarr; ') : 'direct');
                    return `<div class="route-hist">${t} &nbsp;${p}</div>`;
                }).join('');
            }
            return html;
        }

        function routeSummaryText() {
            const hrs = routeListenHours();
            const since = routesMeta.listening_since ? new Date(routesMeta.listening_since).toLocaleString() : '?';
            let flap = 0, silent = 0, none = 0, conflict = 0;
            nodesData.forEach(n => {
                const f = routeFlags(n);
                if (f.flapping) flap++;
                if (f.silent) silent++;
                if (f.noRoute) none++;
                if (f.conflict) conflict++;
            });
            const hrsText = hrs !== null ? ` (${hrs.toFixed(1)}h)` : '';
            return {
                text: `Listening since ${since}${hrsText} · ${routesMeta.live_reports ?? '?'} live reports`
                    + ` · ↯${flap} flapping · z${silent} silent · ∅${none} no route · ⚠${conflict} conflict`,
                title: `zha_routes: ${routesMeta.hooked_devices ?? '?'} hooked devices. Counts reset when Home Assistant restarts.\n`
                    + `Flapping = more than ${FLAP_CHANGES_PER_HOUR} route changes/hour; silent = startup route only or no report for ${SILENT_HOURS}h.`
            };
        }

        function segEnds(s) {
            const a = nodeMap[s.source], b = nodeMap[s.target];
            if (!a || !b || a.x == null || b.x == null) return null;
            const dx = b.x - a.x, dy = b.y - a.y;
            const len = Math.hypot(dx, dy) || 1;
            const ra = getNodeRadius(a) + 1, rb = getNodeRadius(b) + 4;
            if (len < ra + rb) return null;
            return [a.x + dx / len * ra, a.y + dy / len * ra, b.x - dx / len * rb, b.y - dy / len * rb];
        }

        function updateRouteSegments() {
            if (!routeSeg) return;
            routeSeg.attr('d', s => {
                const e = segEnds(s);
                return e ? `M${e[0]},${e[1]} L${e[2]},${e[3]}` : '';
            });
        }

        function highlightRoute(d) {
            if (!routesMeta || !routesOn || !routeSeg) return;
            if (!d.route && !d.route_load && !d.route_load_startup) return;
            routeSelectedId = d.id;
            const pathSet = new Set([d.id, coordinatorId]);
            (d.route && d.route.relay_ieees || []).forEach(x => x && pathSet.add(x));
            // Device's own path, plus (for a router) every path it carries.
            routeSeg.classed('route-hl', s => s.devices.includes(d.id));
            const carries = d.route_load || d.route_load_startup;
            routeSeg.classed('route-dim', s => !s.devices.includes(d.id) && !(carries && (s.source === d.id || s.target === d.id)));
            const neighborIds = new Set(selectedNode ? selectedNode.neighbors.map(n => n.ieee) : []);
            node.classed('dimmed', n => !(pathSet.has(n.id) || neighborIds.has(n.id)));
            node.classed('selected', n => n.id === d.id);
            routeSeg.filter('.route-hl').raise();
        }

        function clearRouteHighlight() {
            routeSelectedId = null;
            if (routeSeg) routeSeg.classed('route-hl', false).classed('route-dim', false);
        }

        let conflictSel = null;

        function updateConflictLinks() {
            if (!conflictSel) return;
            conflictSel.attr('d', l => {
                const a = nodeMap[l.source], b = nodeMap[l.target];
                if (!a || !b || a.x == null || b.x == null) return '';
                return `M${a.x},${a.y} L${b.x},${b.y}`;
            });
        }

        function applyRouteFilters() {
            if (conflictSel) conflictSel.classed('hidden', l => {
                const a = nodeMap[l.source], b = nodeMap[l.target];
                return !a || !b || a.visible === false || b.visible === false;
            });
            if (!routeSeg) return;
            routeSeg.classed('hidden', s => {
                const a = nodeMap[s.source], b = nodeMap[s.target];
                return !a || !b || a.visible === false || b.visible === false;
            });
        }

        function toggleRoutes(btn) {
            routesOn = !routesOn;
            document.body.classList.toggle('routes-on', routesOn);
            btn.classList.toggle('active', routesOn);
            if (!routesOn) clearRouteHighlight();
        }

        function toggleHierarchy(btn) {
            hierarchyMode = hierarchyMode === 'routes' ? 'neighbor' : 'routes';
            btn.textContent = hierarchyMode === 'routes' ? 'Tree: Best evidence' : 'Tree: Neighbour tables';
            document.body.classList.toggle('tree-neighbour', hierarchyMode !== 'routes');
            btn.classList.toggle('active', hierarchyMode === 'routes');
            clearSelection();
            primaryLinks = hierarchyMode === 'routes' ? routePrimaryLinks : neighborPrimaryLinks;
            // forceLink resolves string ids to node objects before we render.
            simulation.force('link').links(primaryLinks.concat(siblingLinks));
            renderPrimaryLinks();
            applyFilters();
            simulation.alpha(0.3).restart();
        }

        if (routesMeta) {
            document.body.classList.add('routes-on');
            const hb = document.getElementById('hierarchyBtn');
            if (hb) hb.classList.toggle('active', hierarchyMode === 'routes');

            // Busiest router(s) by live paths, computed from per-device relays (not names).
            const maxLoad = Math.max(0, ...nodesData.map(n => n.route_load || 0));
            if (maxLoad > 0) topLoadIds = new Set(nodesData.filter(n => n.route_load === maxLoad).map(n => n.id));

            // Merged path segments: above the tree links, but below the tree LQI
            // labels and the click-to-show neighbour lines so they never hide them.
            const routeGroup = g.insert('g', '.neighbor-links-group').attr('class', 'route-only route-segs-group');
            routeSeg = routeGroup.selectAll('path')
                .data(routeSegments)
                .join('path')
                .attr('class', s => 'route-seg' + (s.live === 0 ? ' startup' : ''))
                .attr('stroke-width', s => 1.2 + Math.sqrt(s.count) * 1.1)
                .attr('stroke-opacity', s => s.live === 0 ? 0.45 : 0.75)
                .attr('marker-end', 'url(#route-arrow)');
            routeSeg.append('title').text(s => {
                const a = nodeMap[s.source], b = nodeMap[s.target];
                const names = s.devices.map(id => nodeMap[id] ? (nodeMap[id].user_given_name || nodeMap[id].name) : id);
                return `${a ? a.name : s.source} → ${b ? b.name : s.target}\n${s.count} device path${s.count !== 1 ? 's' : ''}`
                    + (s.live === 0 ? ' (startup routes only)' : '') + `:\n` + names.join(', ');
            });

            routeDefs().append('marker')
                .attr('id', 'route-arrow')
                .attr('viewBox', '0 0 10 10').attr('refX', 8).attr('refY', 5)
                .attr('markerUnits', 'userSpaceOnUse').attr('markerWidth', 7).attr('markerHeight', 7)
                .attr('orient', 'auto')
                .append('path').attr('d', 'M0,0 L10,5 L0,10 z').attr('fill', '#E040FB');

            // Router load badge (bottom-left) and busiest-router ring.
            node.filter(d => topLoadIds.has(d.id))
                .insert('circle', ':first-child')
                .attr('class', 'route-only top-load-ring')
                .attr('r', d => getNodeRadius(d) + 5);
            const badge = node.filter(d => d.route_load > 0)
                .append('g')
                .attr('class', 'route-only route-load-badge')
                .attr('transform', d => `translate(${-getNodeRadius(d) + 2}, ${getNodeRadius(d) - 2})`);
            badge.append('circle').attr('r', 5.5).attr('fill', '#7B1FA2').attr('stroke', '#fff').attr('stroke-width', 0.8);
            badge.append('text').attr('dy', 2).text(d => d.route_load);

            // Per-device flags (top-left): flapping / silent / no route.
            // Conflicting next hops: dashed amber line from the other source's hop.
            conflictSel = g.insert('g', '.neighbor-links-group').attr('class', 'conflict-links-group')
                .selectAll('path').data(conflictLinks).join('path').attr('class', 'conflict-link');
            conflictSel.append('title').text(l => {
                const a = nodeMap[l.source], b = nodeMap[l.target];
                const kind = { table: 'route table', parent: 'parent relationship', record: 'route record' }[l.kind] || l.kind;
                return `Conflict: ${b ? lqiNodeName(b) : l.target}'s ${kind} says next hop is ${a ? lqiNodeName(a) : l.source}`;
            });
            simulation.on('tick.conflicts', updateConflictLinks);

            const flagText = node.append('text')
                .attr('class', 'route-only route-flags')
                .attr('x', d => -getNodeRadius(d) + 1)
                .attr('y', d => -getNodeRadius(d) + 3);
            flagText.each(function(d) {
                const f = routeFlags(d);
                const t = d3.select(this);
                if (f.noRoute) t.append('tspan').attr('fill', '#F44336').text('∅');
                if (f.flapping) t.append('tspan').attr('fill', '#FF9800').text('↯');
                if (f.silent) t.append('tspan').attr('fill', '#9E9E9E').text('z');
                if (f.conflict) t.append('tspan').attr('fill', '#FFB300').text('\u26a0');
            });

            const summary = document.getElementById('routeSummary');
            if (summary) {
                const s = routeSummaryText();
                summary.textContent = s.text;
                summary.title = s.title;
            }
            // The summary may wrap the header; re-fit without disturbing the layout.
            const topBefore = container.offsetTop;
            fitGraphTop();
            if (container.offsetTop !== topBefore) {
                width = container.clientWidth;
                height = container.clientHeight;
                svg.attr('viewBox', [0, 0, width, height]);
            }

            simulation.on('tick.routes', updateRouteSegments);
        }
"""


# --- Tree-line LQI labels -------------------------------------------------
# LQI only exists in neighbour tables, so it lives on the tree lines (never on
# the route layer). Each tree line shows both directions; hovering a number
# draws an arrow along the line in the direction that value was measured.
#   fwd = child -> parent, measured by the parent (parent's neighbour table)
#   rev = parent -> child, measured by the child  (child's neighbour table)

TREE_LQI_CSS = """
        .tree-lqi { font-size: 5.5px; font-weight: bold; text-anchor: middle; paint-order: stroke;
                    stroke: #1a1a2e; stroke-width: 1.6px; stroke-linejoin: round; cursor: help; }
        .tree-lqi.unknown { fill: #777; font-weight: normal; }
        .tree-lqi.active { font-size: 8px; }
        .tree-lqi.dimmed { opacity: 0.15; }
        body.no-tree-lqi .tree-lqi-group { display: none; }
        .lqi-dir { fill: none; stroke-width: 3px; stroke-opacity: 0.95; stroke-linejoin: round;
                   pointer-events: none; filter: drop-shadow(0 0 3px rgba(0,0,0,0.9)); }
"""

TREE_LQI_JS = r"""
        // ---------------- Tree-line LQI labels ----------------
        // `var` on purpose: renderPrimaryLinks() runs before this block, and must
        // see these as undefined (not in the temporal dead zone).
        var treeLabelsReady = false;

        // Marker definitions live in our own top-level <defs>, never the
        // floorplan's (markers inside its foreignObject don't render).
        function topoDefs() {
            let defs = svg.select(':scope > defs.topo-defs');
            if (defs.empty()) defs = svg.insert('defs', ':first-child').attr('class', 'topo-defs');
            return defs;
        }
        var treeLabelGroup = null, treeDirGroup = null, treeLabel = null;
        var LQI_ARROW_COLORS = ['#4CAF50', '#8BC34A', '#FFC107', '#F44336', '#888'];

        function lqiNodeName(n) {
            if (!n || typeof n !== 'object') return String(n);
            return n.user_given_name || n.name || n.id;
        }

        function treeLinkTitle(d) {
            const p = lqiNodeName(d.source), c = lqiNodeName(d.target);
            const f = d.lqi_fwd != null ? d.lqi_fwd : 'not reported';
            const r = d.lqi_reverse != null ? d.lqi_reverse : 'not reported';
            return `${c} → ${p}: ${f}  (measured by ${p})\n${p} → ${c}: ${r}  (measured by ${c})\nLine width = weaker direction`;
        }

        function lqiLabelTitle(e) {
            const p = lqiNodeName(e.link.source), c = lqiNodeName(e.link.target);
            const [from, to] = e.dir === 'fwd' ? [c, p] : [p, c];
            const v = e.v != null ? `LQI ${e.v}` : 'not reported';
            return `${from} → ${to}: ${v}\nHow ${to} hears ${from} (from ${to}'s neighbour table)`;
        }

        function renderTreeLabels() {
            if (!treeLabelsReady) return;
            const data = [];
            primaryLinks.forEach(l => {
                if (l.lqi_fwd == null && l.lqi_reverse == null) return;  // nothing measured either way
                data.push({ link: l, dir: 'fwd', v: l.lqi_fwd });
                data.push({ link: l, dir: 'rev', v: l.lqi_reverse });
            });
            treeLabel = treeLabelGroup.selectAll('text')
                .data(data)
                .join('text')
                .attr('class', e => 'tree-lqi' + (e.v == null ? ' unknown' : ''))
                .attr('fill', e => e.v != null ? getLqiColor(e.v) : null)
                .text(e => e.v != null ? e.v : '?')
                .on('mouseenter', (event, e) => showLqiDirection(e))
                .on('mouseleave', hideLqiDirection)
                .on('click', event => event.stopPropagation());
            treeLabel.selectAll('title').remove();
            treeLabel.append('title').text(lqiLabelTitle);
            positionTreeLabels();
            syncTreeLabels();
        }

        // Both labels sit at the middle of the line's horizontal run, each on the
        // side of the node that measured it (fwd near the parent, rev near the child).
        function positionTreeLabels() {
            if (!treeLabel) return;
            treeLabel
                .attr('x', e => {
                    const p = e.link.source, c = e.link.target;
                    if (p.x == null || c.x == null) return 0;
                    const mx = (p.x + c.x) / 2;
                    const parentLeft = p.x <= c.x;
                    const towardParent = e.dir === 'fwd';
                    return mx + ((parentLeft === towardParent) ? -7 : 7);
                })
                .attr('y', e => {
                    const p = e.link.source, c = e.link.target;
                    if (p.y == null || c.y == null) return 0;
                    return (p.y + c.y) / 2 - 2;
                });
        }

        // Mirror each line's hidden/dimmed state onto its labels.
        function syncTreeLabels() {
            if (!treeLabel || !link) return;
            const state = new Map();
            link.each(function(l) {
                state.set(l, {
                    hidden: this.classList.contains('hidden') || this.style.display === 'none',
                    dimmed: this.classList.contains('dimmed'),
                });
            });
            treeLabel
                .classed('hidden', e => { const s = state.get(e.link); return !s || s.hidden; })
                .classed('dimmed', e => { const s = state.get(e.link); return !!(s && s.dimmed); });
        }

        // Walk back `r` units from one end of a polyline (so arrowheads clear the node).
        function trimPolyline(pts, rStart, rEnd) {
            pts = pts.filter((p, i) => i === 0 || Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) > 0.5);
            const trimEnd = (arr, r) => {
                arr = arr.slice();
                while (arr.length > 1 && r > 0) {
                    const a = arr[arr.length - 2], b = arr[arr.length - 1];
                    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
                    if (len > r) {
                        arr[arr.length - 1] = [b[0] - (b[0] - a[0]) / len * r, b[1] - (b[1] - a[1]) / len * r];
                        r = 0;
                    } else {
                        arr.pop();
                        r -= len;
                    }
                }
                return arr;
            };
            return trimEnd(trimEnd(pts, rEnd).reverse(), rStart).reverse();
        }

        function showLqiDirection(e) {
            hideLqiDirection();
            const p = e.link.source, c = e.link.target;
            if (p.x == null || c.x == null) return;
            const midY = (p.y + c.y) / 2;
            // Same elbow shape as the tree line, oriented sender -> receiver.
            const [snd, rcv] = e.dir === 'fwd' ? [c, p] : [p, c];
            const pts = trimPolyline(
                [[snd.x, snd.y], [snd.x, midY], [rcv.x, midY], [rcv.x, rcv.y]],
                getNodeRadius(snd) + 1, getNodeRadius(rcv) + 2);  // arrow tip stops at the node edge
            if (pts.length < 2) return;
            const color = e.v != null ? getLqiColor(e.v) : '#888';
            treeDirGroup.append('path')
                .attr('class', 'lqi-dir')
                .attr('d', 'M' + pts.map(q => q.join(',')).join(' L'))
                .attr('stroke', color)
                .attr('marker-end', `url(#lqi-arrow-${color.slice(1)})`);
            treeLabel.classed('active', x => x === e);
        }

        function hideLqiDirection() {
            if (treeDirGroup) treeDirGroup.selectAll('*').remove();
            if (treeLabel) treeLabel.classed('active', false);
        }

        function toggleTreeLqi(btn) {
            const off = document.body.classList.toggle('no-tree-lqi');
            btn.classList.toggle('active', !off);
            hideLqiDirection();
        }

        (function initTreeLabels() {
            const defs = topoDefs();
            LQI_ARROW_COLORS.forEach(col => {
                defs.append('marker')
                    .attr('id', 'lqi-arrow-' + col.slice(1))
                    .attr('viewBox', '0 0 10 10').attr('refX', 10).attr('refY', 5)
                    .attr('markerUnits', 'userSpaceOnUse').attr('markerWidth', 16).attr('markerHeight', 16)
                    .attr('orient', 'auto')
                    .append('path').attr('d', 'M0,0 L10,5 L0,10 z').attr('fill', col);
            });
            // Above the tree lines and route layer, below neighbour overlay and nodes.
            treeDirGroup = g.insert('g', '.neighbor-links-group').attr('class', 'lqi-dir-group');
            treeLabelGroup = g.insert('g', '.neighbor-links-group').attr('class', 'tree-lqi-group');
            treeLabelsReady = true;
            renderTreeLabels();
            simulation.on('tick.treelqi', positionTreeLabels);
        })();
"""


def load_topology(json_file: str) -> dict:
    """Load topology data from JSON export file."""
    with open(json_file, 'r') as f:
        data = json.load(f)
    return data


def _parse_nwk(nwk_val):
    """Normalize a ZHA NWK value (hex string '0x1234', int, or None) to an int.

    ZHA serializes nwk as a hex string, but route next_hop/dest_nwk comparisons
    need integers. Keeping both forms consistent is what makes route-based parent
    resolution work for multi-hop devices.
    """
    if nwk_val is None:
        return None
    if isinstance(nwk_val, int):
        return nwk_val
    if isinstance(nwk_val, str):
        try:
            return int(nwk_val, 16) if nwk_val.lower().startswith('0x') else int(nwk_val)
        except ValueError:
            return None
    return None


def build_hierarchy(data: dict) -> dict:
    """Extract the coordinator, node map and device map used by the visualizer.

    The rendered graph's parent/child structure is computed entirely in
    generate_html() via the device_primary_link cascade (route -> parent ->
    child-from-others -> best-neighbour -> fallback). This function only locates
    the coordinator and exposes the node/device lookups it needs.
    """
    topology = data.get('topology', {})
    nodes = {n['id']: n for n in topology.get('nodes', [])}
    devices = {d.get('ieee'): d for d in data.get('devices', [])}

    coordinator = None
    for node in nodes.values():
        if node.get('is_coordinator'):
            coordinator = node
            break

    if not coordinator:
        print("Warning: No coordinator found in topology")
        return {}

    return {
        'coordinator': coordinator,
        'nodes': nodes,
        'devices': devices
    }


def _weaker_lqi(a, b):
    """The weaker of two directional LQIs, ignoring unreported (None) values.

    A hop needs both directions (data one way, ACK the other), so the weaker
    known direction is the honest summary of the link.
    """
    known = [v for v in (a, b) if v is not None]
    return min(known) if known else None


def build_route_data(routes, devices, nodes, coordinator_id, nwk_to_ieee,
                     device_primary_link, directional_lqi, evidence=None):
    """Turn a zha_routes snapshot into what the Routes layer draws.

    Relay order is device first, coordinator last: relays ["0xA", "0xB"] means
    device -> 0xA -> 0xB -> coordinator. [] = direct, None = no route known.
    Devices are matched by IEEE; relay NWKs are resolved against ZHA's own
    device list (never by name). Returns None when there is no usable snapshot,
    in which case the page renders exactly as it did without routes.
    """
    if not isinstance(routes, dict) or not isinstance(routes.get('devices'), list):
        return None

    def resolve(nwk):
        n = _parse_nwk(nwk)
        if n is None:
            return None
        if n == 0:
            return coordinator_id
        return nwk_to_ieee.get(n)

    def label(ieee, raw):
        node = nodes.get(ieee) if ieee else None
        return node.get('name', ieee) if node else raw

    info = {}
    recent_first = {}   # ieee -> first hops seen in the device's recent route history
    segments = {}
    load = defaultdict(int)          # devices with a live route through the router
    load_startup = defaultdict(int)  # devices whose only route is the startup (database) one

    for rd in routes['devices']:
        ieee = rd.get('ieee')
        if not ieee or ieee not in nodes or ieee == coordinator_id:
            continue
        relays = rd.get('relays')
        relay_ieees = None
        unresolved = []
        if isinstance(relays, list):
            relay_ieees = [resolve(r) for r in relays]
            unresolved = [r for r, x in zip(relays, relay_ieees) if x is None]
            # Router load: each device counts once per router on its path. Startup
            # (database) routes are of unknown age, so they're counted apart.
            bucket = load if rd.get('source') == 'live' else load_startup
            for x in {x for x in relay_ieees if x and x != coordinator_id and x != ieee}:
                bucket[x] += 1
            chain = [ieee] + relay_ieees + [coordinator_id]
            for a, b in zip(chain, chain[1:]):
                if not a or not b or a == b:
                    continue  # unresolved hop: leave a gap rather than guess
                seg = segments.setdefault((a, b), {'source': a, 'target': b, 'devices': [], 'live': 0})
                if ieee not in seg['devices']:
                    seg['devices'].append(ieee)
                    if rd.get('source') == 'live':
                        seg['live'] += 1
        else:
            relays = None

        history = []
        firsts = set()
        for h in (rd.get('history') or [])[-50:]:
            hr = h.get('relays')
            if isinstance(hr, list):
                fh = resolve(hr[0]) if hr else coordinator_id
                if fh:
                    firsts.add(fh)
            history.append({
                't': h.get('t'),
                'names': None if hr is None else [label(resolve(r), r) for r in hr],
            })

        recent_first[ieee] = firsts
        info[ieee] = {
            'relays': relays,
            'relay_ieees': relay_ieees,
            'relay_names': None if relays is None else [label(x, r) for r, x in zip(relays, relay_ieees)],
            'unresolved': unresolved,
            'hops': None if relays is None else len(relays),
            'source': rd.get('source'),
            'last_report': rd.get('last_report'),
            'last_change': rd.get('last_change'),
            'reports': rd.get('reports', 0),
            'changes': rd.get('changes', 0),
            'history': history,
        }

    # Best-evidence hierarchy. Each source of "next hop toward the coordinator"
    # is ranked by how direct and how fresh it is; the best one draws the tree
    # line, and the others are compared against it:
    #   1    live route record (zha_routes; actual traffic, continuously updated)
    #   2    route table read by this refresh's active scan
    #   2.5  parent relationship reported by a router scanned this refresh
    #   3    startup route record (zigpy database, age unknown)
    #   4    route table from ZHA's cache (not scanned this refresh)
    #   5    parent relationship from unscanned data
    # Devices with no evidence keep their neighbour-based link (estimated /
    # unknown), so nothing vanishes.
    evidence = evidence or {}
    fresh = evidence.get('fresh') or set()
    table_hop = evidence.get('table_hop', {})
    parent_rel = evidence.get('parent_rel', {})
    severity = {'single': 0, 'agree': 1, 'outdated': 2, 'alternating': 3, 'conflict': 4}
    kind_type = {'table': 'route', 'parent': 'parent'}

    route_primary_links = []
    conflict_links = []
    next_hop = {}
    for ieee in nodes:
        if ieee == coordinator_id:
            continue
        ri = info.get(ieee)
        cands = []
        if ri and ri['relays'] is not None:
            hop = ri['relay_ieees'][0] if ri['relay_ieees'] else coordinator_id
            if hop and hop != ieee:
                live = ri['source'] == 'live'
                cands.append({'kind': 'record', 'hop': hop, 'rank': 1 if live else 3, 'current': live,
                              'detail': 'live' if live else 'startup only, age unknown',
                              'age': ri['last_report'] if live else None})
        th = table_hop.get(ieee)
        if th and th != ieee:
            f = ieee in fresh
            cands.append({'kind': 'table', 'hop': th, 'rank': 2 if f else 4, 'current': f,
                          'detail': 'scanned this refresh' if f else 'cached, not scanned this refresh'})
        pr = parent_rel.get(ieee)
        if pr and pr[0] != ieee:
            f = pr[1] in fresh
            reporter = 'this device' if pr[1] == ieee else label(pr[1], pr[1])
            cands.append({'kind': 'parent', 'hop': pr[0], 'rank': 2.5 if f else 5, 'current': f,
                          'detail': 'reported by ' + reporter + (', scanned this refresh' if f else ', not rescanned')})

        if cands:
            chosen = min(cands, key=lambda c: c['rank'])
            recent = set(recent_first.get(ieee, set()))
            for c in cands:
                if c['kind'] == 'record':
                    recent.add(c['hop'])
            verdict = 'single' if len(cands) == 1 else 'agree'
            for c in cands:
                if c is chosen:
                    c['status'] = 'used'
                    continue
                if c['hop'] == chosen['hop']:
                    c['status'] = 'agree'
                elif c['hop'] in recent and chosen['hop'] in recent:
                    c['status'] = 'alternating'   # normal path switching
                elif c['current'] and chosen['current']:
                    c['status'] = 'conflict'      # two current sources disagree
                    conflict_links.append({'source': c['hop'], 'target': ieee, 'kind': c['kind']})
                else:
                    c['status'] = 'outdated'      # one side is stale data
                if severity[c['status']] > severity[verdict]:
                    verdict = c['status']
            parent = chosen['hop']
            if chosen['kind'] == 'record':
                source_type = 'zroute' if chosen['current'] else 'zroute_startup'
            else:
                source_type = kind_type[chosen['kind']]
            next_hop[ieee] = {
                'verdict': verdict,
                'sources': [{'kind': c['kind'], 'hop': c['hop'], 'name': label(c['hop'], c['hop']),
                             'detail': c['detail'], 'status': c['status'], 'age': c.get('age')}
                            for c in sorted(cands, key=lambda c: c['rank'])],
            }
        else:
            fallback = device_primary_link.get(ieee)
            if not fallback:
                continue
            parent, source_type = fallback['target'], fallback['source_type']
            next_hop[ieee] = {'verdict': 'none', 'sources': [], 'fallback': source_type}

        lqi_fwd = directional_lqi.get((parent, ieee))
        lqi_rev = directional_lqi.get((ieee, parent))
        route_primary_links.append({
            'source': parent,
            'target': ieee,
            'lqi': _weaker_lqi(lqi_fwd, lqi_rev),
            'lqi_fwd': lqi_fwd,
            'lqi_reverse': lqi_rev,
            'type': 'primary',
            'source_type': source_type,
            'source_last_seen': devices.get(ieee, {}).get('last_seen'),
        })

    seg_list = []
    for seg in segments.values():
        seg['count'] = len(seg['devices'])
        seg_list.append(seg)

    meta = {
        'listening_since': routes.get('listening_since'),
        'live_reports': routes.get('live_reports'),
        'hooked_devices': routes.get('hooked_devices'),
        'router_load_reported': routes.get('router_load'),
    }
    print(f"[Visualize] Routes: {len(info)} devices, {len(seg_list)} segments, "
          f"{sum(1 for i in info.values() if i['relays'] is None)} without route")
    return {
        'info': info,
        'segments': seg_list,
        'load': dict(load),
        'load_startup': dict(load_startup),
        'route_primary_links': route_primary_links,
        'conflict_links': conflict_links,
        'next_hop': next_hop,
        'meta': meta,
    }


def generate_html(hierarchy: dict, data: dict, output_file: str):
    """Generate interactive HTML visualization with D3.js."""

    d3_nodes = []
    d3_links = []

    devices = hierarchy['devices']
    nodes = hierarchy['nodes']

    # Build a map of IEEE -> entities using device registry and entity registry
    # 1. Device registry maps device_id -> IEEE (from identifiers like ["zha", "00:11:22:..."])
    # 2. Entity registry maps entity_id -> device_id
    # 3. Entity states provide friendly_name and current state

    ieee_to_entities = {}

    # Step 1: Build device_id -> IEEE map from device registry
    device_id_to_ieee = {}
    ieee_to_device_reg_id = {}  # reverse map so the "Open in Home Assistant" link works
    device_registry = data.get('device_registry', [])
    for dev in device_registry:
        device_id = dev.get('id')
        identifiers = dev.get('identifiers', [])
        for ident in identifiers:
            if isinstance(ident, (list, tuple)) and len(ident) >= 2:
                if ident[0] == 'zha':
                    device_id_to_ieee[device_id] = ident[1]
                    if device_id:
                        ieee_to_device_reg_id[ident[1]] = device_id
                    break
    print(f"[Visualize] Device registry: {len(device_registry)} devices, {len(device_id_to_ieee)} with IEEE")

    # Step 2: Build entity_id -> device_id map from entity registry
    entity_id_to_device_id = {}
    entity_registry = data.get('entity_registry', [])
    for ent in entity_registry:
        entity_id = ent.get('entity_id')
        device_id = ent.get('device_id')
        if entity_id and device_id:
            entity_id_to_device_id[entity_id] = device_id
    print(f"[Visualize] Entity registry: {len(entity_registry)} entities, {len(entity_id_to_device_id)} with device_id")

    # Step 3: Get entity states for friendly names and current state
    entity_states = {}
    entities_list = data.get('entities', [])
    for entity in entities_list:
        entity_id = entity.get('entity_id', '')
        attributes = entity.get('attributes', {})
        entity_states[entity_id] = {
            'friendly_name': attributes.get('friendly_name', entity_id),
            'state': entity.get('state', 'unknown')
        }
    print(f"[Visualize] Entity states: {len(entity_states)} total entities")

    # Step 4: Chain: entity_id -> device_id -> IEEE, and build ieee_to_entities map
    entities_mapped = 0
    for entity_id, device_id in entity_id_to_device_id.items():
        ieee = device_id_to_ieee.get(device_id)
        if ieee and entity_id in entity_states:
            entities_mapped += 1
            if ieee not in ieee_to_entities:
                ieee_to_entities[ieee] = []
            state_info = entity_states[entity_id]
            ieee_to_entities[ieee].append({
                'entity_id': entity_id,
                'friendly_name': state_info['friendly_name'],
                'state': state_info['state']
            })
    print(f"[Visualize] Mapped {entities_mapped} entities to {len(ieee_to_entities)} devices")

    # Key by BOTH the raw nwk and its normalized int form. Route resolution looks
    # up next_hop as an int; without the int key every multi-hop next_hop missed
    # and the authoritative 'route' parent was silently never assigned.
    nwk_to_ieee = {}
    for ieee, device in devices.items():
        nwk = device.get('nwk')
        if nwk is not None and nwk != '':
            nwk_to_ieee[nwk] = ieee
            nwk_int = _parse_nwk(nwk)
            if nwk_int is not None:
                nwk_to_ieee[nwk_int] = ieee

    # Build directional LQI lookup: (source_ieee, target_ieee) -> lqi
    # Source is the reporting device, target is the neighbor it reported.
    # Preserve None for "not reported" so unknown links aren't shown as weak.
    topology = data.get('topology', {})
    directional_lqi = {}
    for edge in topology.get('edges', []):
        src = edge.get('source')
        tgt = edge.get('target')
        lqi = edge.get('lqi')
        if src and tgt:
            directional_lqi[(src, tgt)] = lqi if lqi else None

    device_primary_link = {}

    nwk_to_int = _parse_nwk

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
                'lqi': coord_route[1] or None,
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
                        'lqi': lqi or None,
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
                'lqi': best_lqi if best_lqi > 0 else None,
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
            # "Best neighbour" is a guess (strongest signal, no reported parent
            # relationship) for ANY device type - routers included. Mark it
            # inferred so the displayed backbone never looks more certain than it
            # is, instead of giving routers a confident solid link.
            device_primary_link[ieee] = {
                'target': best_neighbor,
                'lqi': best_lqi if best_lqi > 0 else None,
                'source_type': 'inferred'
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
        # Two independent directional measurements (each measured at the receiver,
        # each may be None = "not reported"):
        #   forward  child -> parent : how the PARENT hears the child
        #   reverse  parent -> child : how the CHILD hears the parent
        # Looking both up from directional_lqi avoids showing one measurement as
        # if it were both directions (the case for inferred end-device links).
        lqi_fwd = directional_lqi.get((parent_ieee, ieee))
        lqi_rev = directional_lqi.get((ieee, parent_ieee))
        # Source last_seen: when was the reporting device last heard from?
        reporting_device = devices.get(ieee, {})
        child_to_parents[ieee].append({
            'id': parent_ieee,
            'name': parent_name,
            'lqi': lqi_fwd,
            'lqi_reverse': lqi_rev,
            'source_type': link_info['source_type'],
            'source_last_seen': reporting_device.get('last_seen')
        })

    for node_id, node in nodes.items():
        device = devices.get(node_id, {})
        neighbors = device.get('neighbors', [])
        neighbor_list = []
        for n in neighbors:
            neighbor_list.append({
                'ieee': n.get('ieee', ''),
                # 0/missing = "not reported" on TI Z-Stack, kept as None so the
                # neighbour overlay shows "unknown" instead of a red zero.
                'lqi': int(n.get('lqi')) if n.get('lqi') else None,
                'relationship': n.get('relationship', 'Unknown'),
                'device_type': n.get('device_type', 'Unknown')
            })

        # Prefer the device-registry id (authoritative) so the "Open in Home
        # Assistant" deep link resolves; fall back to anything on the device.
        device_reg_id = ieee_to_device_reg_id.get(node_id) or device.get('device_reg_id', '')

        # Get nwk address
        nwk = device.get('nwk', '')

        # Power source (Mains / Battery / Unknown): distinguishes always-on
        # routers from sleepy battery devices, which explains many unreported LQIs.
        power_source = device.get('power_source') or ''
        is_mains = ('main' in power_source.lower()) if power_source else None

        # Get entity names associated with this device from the ieee_to_entities map
        device_entities = ieee_to_entities.get(node_id, [])
        entity_names = []
        entity_details = []  # For displaying in tooltip
        for e in device_entities:
            # Add the friendly name for searchability
            if e.get('friendly_name'):
                entity_names.append(e.get('friendly_name'))
            # Also add the entity_id for searchability (e.g., "light.living_room")
            if e.get('entity_id'):
                entity_names.append(e.get('entity_id'))
            # Store full details for tooltip display
            entity_details.append({
                'entity_id': e.get('entity_id', ''),
                'friendly_name': e.get('friendly_name', ''),
                'state': e.get('state', 'unknown')
            })

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
            'device_reg_id': device_reg_id,
            'nwk': nwk,
            'power_source': power_source,
            'is_mains': is_mains,
            'entity_names': entity_names,
            'entity_details': entity_details
        })

    for ieee, link_info in device_primary_link.items():
        parent_ieee = link_info['target']
        lqi_fwd = directional_lqi.get((parent_ieee, ieee))
        lqi_rev = directional_lqi.get((ieee, parent_ieee))
        # Stroke width uses the weaker known direction; None = "not reported" so
        # the link isn't drawn as weak. lqi_fwd = child->parent (measured by the
        # parent), lqi_reverse = parent->child (measured by the child).
        link_lqi = _weaker_lqi(lqi_fwd, lqi_rev)
        # Source last_seen: when was the reporting device last heard from?
        reporting_device = devices.get(ieee, {})
        d3_links.append({
            'source': parent_ieee,
            'target': ieee,
            'lqi': link_lqi,
            'lqi_fwd': lqi_fwd,
            'lqi_reverse': lqi_rev,
            'type': 'primary',
            'source_type': link_info['source_type'],
            'source_last_seen': reporting_device.get('last_seen')
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
                    # Same convention as links: fwd = this hop's child -> parent
                    # (parent's table), rev = parent -> child (child's table).
                    'lqi_fwd': directional_lqi.get((parent_id, current)),
                    'lqi_rev': directional_lqi.get((current, parent_id)),
                    'device_type': parent_node.get('device_type') if parent_node else 'Unknown'
                })
                current = parent_id
            else:
                break

        device_paths[node_id] = path

    # Add path_to_coordinator to each node
    for node in d3_nodes:
        node['path_to_coordinator'] = device_paths.get(node['id'], [])

    # Next-hop evidence for the best-evidence tree (only used with zha_routes).
    # Route-table hop: the 'route' links above came straight from each router's
    # own table entry for the coordinator.
    table_hop = {i: l['target'] for i, l in device_primary_link.items() if l['source_type'] == 'route'}
    # Parent relationship: (parent, who reported it). The device's own Parent
    # entry wins; otherwise a router that lists the device as its Child.
    parent_rel = {}
    for ieee, device in devices.items():
        if ieee not in nodes:
            continue
        for n in device.get('neighbors', []):
            if n.get('relationship') == 'Parent' and n.get('ieee') in nodes:
                parent_rel[ieee] = (n['ieee'], ieee)
                break
    for other_ieee, other in devices.items():
        if nodes.get(other_ieee, {}).get('device_type') not in ('Router', 'Coordinator'):
            continue
        for n in other.get('neighbors', []):
            child = n.get('ieee')
            if n.get('relationship') == 'Child' and child in nodes and child not in parent_rel:
                parent_rel[child] = (other_ieee, other_ieee)
    scan_info = data.get('scan') if isinstance(data.get('scan'), dict) else {}
    evidence = {
        'table_hop': table_hop,
        'parent_rel': parent_rel,
        'fresh': set(scan_info.get('responded') or []),
    }

    # Optional source-route layer (zha_routes). None -> page identical to v1.3.1.
    route_data = build_route_data(data.get('routes'), devices, nodes, coordinator_id,
                                  nwk_to_ieee, device_primary_link, directional_lqi, evidence)
    if route_data:
        for node in d3_nodes:
            node['route'] = route_data['info'].get(node['id'])
            node['route_load'] = route_data['load'].get(node['id'], 0)
            node['route_load_startup'] = route_data['load_startup'].get(node['id'], 0)
            node['next_hop'] = route_data['next_hop'].get(node['id'])
    routes_meta_json = json.dumps(route_data['meta']) if route_data else 'null'
    route_segments_json = json.dumps(route_data['segments']) if route_data else '[]'
    route_primary_json = json.dumps(route_data['route_primary_links']) if route_data else '[]'
    conflict_links_json = json.dumps(route_data['conflict_links']) if route_data else '[]'
    has_routes = route_data is not None

    export_timestamp = data.get('export_timestamp', '')
    data_fetched_str = export_timestamp[:19].replace('T', ' ') if export_timestamp else 'N/A'
    nodes_data = hierarchy['nodes']
    total = len(nodes_data)
    routers = sum(1 for n in nodes_data.values() if n.get('device_type') == 'Router')
    end_devices = sum(1 for n in nodes_data.values() if n.get('device_type') == 'EndDevice')

    # Network channel for the health line (from zha/network/settings)
    channel = data.get('network_settings', {}).get('network_info', {}).get('channel')
    channel_html = (f'<span style="color:#888">Channel: {channel}</span>'
                    if channel not in (None, 'N/A', '') else '')

    coordinator_id = hierarchy['coordinator']['id']
    storage_key = f"zha_topology_{coordinator_id[:8]}"

    # Get floorplan SVG and CSS if available
    floorplan_svg = data.get('floorplan_svg', '')
    floorplan_css = data.get('floorplan_css', '')
    has_floorplan = bool(floorplan_svg)

    # Debug log for floorplan
    print(f"[Visualize] Floorplan SVG in data: {'Yes (' + str(len(floorplan_svg)) + ' bytes)' if floorplan_svg else 'No'}")
    print(f"[Visualize] Floorplan CSS in data: {'Yes (' + str(len(floorplan_css)) + ' bytes)' if floorplan_css else 'No'}")

    # Escape the SVG for embedding in JavaScript
    if floorplan_svg:
        # Escape backticks and backslashes for JS template literal
        floorplan_svg_escaped = floorplan_svg.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')
    else:
        floorplan_svg_escaped = ''

    # Escape CSS for embedding
    floorplan_css_escaped = floorplan_css if floorplan_css else ''

    if has_routes:
        route_legend_html = (
            '<div class="legend-item clickable" data-link-type="zroute" title="Tree parent = first relay in the device&#39;s latest live route record (zha_routes)">'
            '<div class="legend-line" style="width:20px;height:3px;background:#CE93D8;margin-right:5px"></div> Route record</div>'
            '<div class="legend-item clickable" data-link-type="zroute_startup" title="Tree parent from a route record stored at startup (age unknown)">'
            '<div class="legend-line" style="width:20px;border-top:2px dashed #CE93D8;margin-right:5px"></div> Route record (startup)</div>'
            '<div class="legend-item" title="Two current sources disagree on the next hop; dashed amber line points at the other one">'
            '<div class="legend-line" style="width:20px;border-top:2px dashed #FFB300;margin-right:5px"></div> Conflicting next hop</div>'
            '<span class="legend-group" style="margin-left:12px">Routes:</span>'
            '<div class="legend-item" title="Actual path traffic takes to the coordinator; thicker = more devices share it">'
            '<div class="legend-line" style="width:20px;height:3px;background:#E040FB;margin-right:5px"></div> Path (thicker = more devices)</div>'
            '<div class="legend-item" title="Only startup (database) routes - age unknown">'
            '<div class="legend-line" style="width:20px;border-top:2px dashed #E040FB;margin-right:5px;opacity:0.6"></div> Startup only</div>'
            '<div class="legend-item" title="Number of device paths through this router; gold ring = busiest router">'
            '<div class="legend-color" style="background:#7B1FA2;border-radius:50%"></div> Router load</div>'
            '<div class="legend-item" title="Route changed more often than the flapping threshold since listening started">'
            '<span style="color:#FF9800;font-weight:bold">&#8623;</span> Flapping</div>'
            '<div class="legend-item" title="Only a startup route, or no route report within the silent threshold">'
            '<span style="color:#9E9E9E;font-weight:bold">z</span> Silent</div>'
            '<div class="legend-item" title="No route known for this device">'
            '<span style="color:#F44336;font-weight:bold">&#8709;</span> No route</div>'
            '<div class="legend-item" title="Route record and route table / parent disagree, and neither is stale">'
            '<span style="color:#FFB300;font-weight:bold">&#9888;</span> Conflict</div>'
        )
        route_controls_html = (
            '<div class="filter-group">'
            '<button onclick="toggleRoutes(this)" class="active" id="toggleRoutesBtn" '
            'title="Show the actual source routes reported to the coordinator (zha_routes)">Routes</button>'
            '<button onclick="toggleHierarchy(this)" id="hierarchyBtn" '
            'title="Best evidence: each device hangs from its most trusted next hop (live route record &gt; fresh route table &gt; startup record &gt; cached table &gt; parent). Neighbour tables: the v1.3 method.">Tree: Best evidence</button>'
            '<span id="routeSummary" style="font-size:11px;color:#CE93D8"></span>'
            '</div>'
        )
    else:
        route_legend_html = ''
        route_controls_html = ''

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
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
            overflow: hidden;
        }}
        body.floorplan-active {{
            background: transparent;
        }}

        /* Floorplan CSS */
        {floorplan_css_escaped}
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
        .legend-group {{
            display: flex;
            align-items: center;
            font-size: 11px;
            color: #aaa;
            font-weight: 600;
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
        .search-container {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .search-container input {{
            background: #333;
            color: #fff;
            border: 1px solid #555;
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 11px;
            width: 180px;
            transition: border-color 0.2s, width 0.2s;
        }}
        .search-container input:focus {{
            outline: none;
            border-color: #00d4ff;
            width: 220px;
        }}
        .search-container input::placeholder {{
            color: #666;
        }}
        .search-container .clear-search {{
            background: transparent;
            border: none;
            color: #888;
            cursor: pointer;
            font-size: 14px;
            padding: 2px 6px;
            display: none;
        }}
        .search-container .clear-search.visible {{
            display: inline;
        }}
        .search-container .clear-search:hover {{
            color: #00d4ff;
        }}
        .search-container .search-count {{
            font-size: 10px;
            color: #888;
            min-width: 50px;
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
            font-size: 7px;
            fill: #fff;
            text-anchor: middle;
            pointer-events: none;
            text-shadow: 0 1px 3px rgba(0,0,0,0.8);
        }}
        .node .lqi-badge {{
            font-size: 6px;
            fill: #fff;
        }}
        .node .neighbor-badge {{
            cursor: pointer;
        }}
        .node .neighbor-badge text {{
            font-size: 6px;
        }}

        .floorplan-layer {{
            pointer-events: none;
        }}
        .floorplan-layer svg {{
            width: 100%;
            height: 100%;
        }}

        .link {{
            fill: none;
            stroke-opacity: 0.6;
        }}

        .link.sibling {{
            stroke-dasharray: 4, 4;
            stroke-opacity: 0.3;
        }}

        .link.primary.inferred {{
            stroke-dasharray: 4, 2;
            stroke-opacity: 0.4;
        }}

        /* "Unknown" attachment (fallback): dashed + faint so it never reads as a
           confirmed direct connection to the coordinator. */
        .link.primary.fallback {{
            stroke-dasharray: 2, 3;
            stroke-opacity: 0.35;
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

        /* Pinned corner card: fixed top-right so it never follows the cursor
           and can never be clipped at the viewport edge. Scrolls if too tall. */
        .tooltip {{
            position: fixed;
            top: 148px;
            right: 12px;
            left: auto;
            background: rgba(26, 26, 46, 0.97);
            border: 1px solid #00d4ff;
            border-radius: 6px;
            padding: 10px 28px 10px 14px;
            font-size: 11px;
            z-index: 1000;
            box-shadow: 0 4px 16px rgba(0,0,0,0.6);
            width: 300px;
            max-width: calc(100vw - 24px);
            max-height: calc(100vh - 164px);
            overflow-y: auto;
            opacity: 0;
            transform: translateX(8px);
            pointer-events: none;
            transition: opacity 0.15s, transform 0.15s;
        }}
        .tooltip.visible {{
            opacity: 1;
            transform: translateX(0);
            pointer-events: auto;
        }}
        .tooltip .card-close {{
            position: absolute;
            top: 4px;
            right: 8px;
            color: #888;
            cursor: pointer;
            font-size: 16px;
            line-height: 1;
        }}
        .tooltip .card-close:hover {{ color: #00d4ff; }}
        /* On phones, pin to the bottom as a full-width card */
        @media (max-width: 600px) {{
            .tooltip {{
                top: auto;
                bottom: 8px;
                left: 8px;
                right: 8px;
                width: auto;
                max-width: none;
                max-height: 45vh;
            }}
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
{TREE_LQI_CSS}
{ROUTE_CSS if has_routes else ''}
    </style>
</head>
<body>
    <div class="header">
        <h1>ZHA Network Topology <span style="font-size:11px;color:#666;font-weight:normal">v{ADDON_VERSION}</span></h1>
        <div class="stats">
            <span>Total: {total} devices</span>
            <span id="visibleCount" style="color:#00d4ff">(Showing: {total})</span>
            <span>Coordinator: 1</span>
            <span>Routers: {routers}</span>
            <span>End Devices: {end_devices}</span>
            {channel_html}
            <span id="dataAge" style="color:#666" title="When this data was fetched from ZHA">Data fetched: {data_fetched_str}</span>
            <span id="oldestSeen" style="color:#888" title="Oldest device last_seen - the stalest data in this view"></span>
            <span id="healthSummary" style="color:#FFC107" title="Network health: weak / offline / unknown-attachment devices"></span>
        </div>
        <div class="legend">
            <span class="legend-group">Device:</span>
            <div class="legend-item"><div class="legend-color" style="background:#00d4ff"></div> Coordinator</div>
            <div class="legend-item"><div class="legend-color" style="background:#8BC34A"></div> Router</div>
            <div class="legend-item"><div class="legend-color" style="background:#FFC107"></div> End Device</div>
            <span class="legend-group" style="margin-left:12px">Signal <span style="color:#666;font-weight:normal">(TI LQI; badge &amp; links = last hop to coordinator)</span>:</span>
            <div class="legend-item"><div class="legend-color" style="background:#4CAF50"></div> 90+</div>
            <div class="legend-item"><div class="legend-color" style="background:#8BC34A"></div> 65+</div>
            <div class="legend-item"><div class="legend-color" style="background:#FFC107"></div> 45+</div>
            <div class="legend-item"><div class="legend-color" style="background:#F44336"></div> &lt;45</div>
            <div class="legend-item"><div class="legend-color" style="background:#888"></div> not reported</div>
            <span class="legend-group" style="margin-left:12px">Connection:</span>
            <div class="legend-item clickable" data-link-type="route" title="Next hop from the router's own route table (read by the zha-toolkit scan)"><div class="legend-line" style="width:20px;height:3px;background:#00d4ff;margin-right:5px"></div> Route table</div>
            <div class="legend-item clickable" data-link-type="parent" title="Parent from a reported Parent/Child relationship"><div class="legend-line" style="width:20px;height:3px;background:#8BC34A;margin-right:5px"></div> Parent (confirmed)</div>
            <div class="legend-item clickable" data-link-type="inferred" title="Best guess from signal strength - no reported relationship"><div class="legend-line" style="width:20px;border-top:2px dashed #FF9800;margin-right:5px"></div> Estimated</div>
            <div class="legend-item clickable" data-link-type="fallback" title="Attachment unknown - shown at the coordinator for layout only"><div class="legend-line" style="width:20px;border-top:2px dashed #666;margin-right:5px"></div> Unknown</div>
            <div class="legend-item clickable disabled" data-link-type="sibling"><div class="legend-line" style="width:20px;border-top:2px dashed #888;margin-right:5px"></div> Sibling</div>
            <div class="legend-item"><div class="legend-line" style="width:20px;border-top:2px dashed #666;margin-right:5px;opacity:0.5"></div> Stale (&gt;24h)</div>
            {route_legend_html}
        </div>
        <div class="controls">
            <div class="search-container">
                <input type="text" id="searchInput" placeholder="Search devices, entities, nwk..." oninput="handleSearch(this.value)">
                <button class="clear-search" id="clearSearch" onclick="clearSearch()">&times;</button>
                <span class="search-count" id="searchCount"></span>
            </div>
            <button onclick="refreshData()" id="refreshBtn" title="Re-measure the network: actively scans every router for fresh routes &amp; neighbour LQIs via zha-toolkit, then reloads (takes 1-5 min)">Refresh Data</button>
            <button onclick="scanNetwork()" id="scanBtn" title="Ask ZHA to rebuild its own topology (zha/network/update_topology). Usually unnecessary now - Refresh already scans actively.">Scan Network</button>
            <button onclick="regenerateUI()" id="regenBtn" title="Regenerate UI from cached data (fast)">Regenerate UI</button>
            <button onclick="resetPositions()">Reset Layout</button>
            <button onclick="savePositions()">Save Positions</button>
            <button onclick="toggleEndDevices(this)" class="active" id="toggleEndBtn">Show End Devices</button>
            <button onclick="toggleTreeLqi(this)" class="active" id="toggleTreeLqiBtn" title="Show both LQI directions on each tree line; hover a number to see which direction it measures">LQI Labels</button>
            {'<button onclick="toggleFloorplan(this)" class="active" id="toggleFloorplanBtn">Show Floorplan</button>' if has_floorplan else ''}
            {'<button onclick="toggleGrid(this)" id="toggleGridBtn">Show Grid</button>' if has_floorplan else ''}
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
            {route_controls_html}
        </div>
    </div>

    <div id="graph"></div>
    <div class="tooltip" id="tooltip"></div>
    <div id="coordDisplay" style="position:fixed; bottom:8px; left:8px; font-size:11px; color:#888; font-family:monospace; pointer-events:none; z-index:10;"></div>

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
        const hasFloorplan = {'true' if has_floorplan else 'false'};
        const floorplanSvgContent = `{floorplan_svg_escaped}`;
        // Source routes from zha_routes (null when unavailable -> no route UI).
        const routesMeta = {routes_meta_json};
        const routeSegments = {route_segments_json};
        const routePrimaryLinks = {route_primary_json};
        const conflictLinks = {conflict_links_json};
        const coordinatorId = "{coordinator_id}";

        const linkTypeVisibility = {{
            route: true,
            parent: true,
            neighbor: true,
            inferred: true,
            fallback: true,
            zroute: true,
            zroute_startup: true,
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
            syncTreeLabels();
        }}

        function updateDataAge() {{
            const now = new Date();
            const diffMs = now - exportTime;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMins / 60);
            const diffDays = Math.floor(diffHours / 24);

            let relativeTime;
            if (diffMins < 1) relativeTime = 'just now';
            else if (diffMins < 60) relativeTime = `${{diffMins}} minute${{diffMins !== 1 ? 's' : ''}} ago`;
            else if (diffHours < 24) relativeTime = `${{diffHours}} hour${{diffHours !== 1 ? 's' : ''}} ago`;
            else relativeTime = `${{diffDays}} day${{diffDays !== 1 ? 's' : ''}} ago`;

            const dateStr = exportTime.toLocaleString();
            document.getElementById('dataAge').textContent = `Data fetched: ${{dateStr}} (${{relativeTime}})`;
        }}

        function updateHealthSummary() {{
            const el = document.getElementById('healthSummary');
            if (!el) return;
            const weak = nodesData.filter(n => !n.is_coordinator && n.lqi != null && n.lqi < 50).length;
            const offline = nodesData.filter(n => n.available === false).length;
            const unknown = nodesData.filter(n => n.parents && n.parents.length && n.parents[0].source_type === 'fallback').length;
            const estimated = nodesData.filter(n => n.parents && n.parents.length && n.parents[0].source_type === 'inferred').length;
            if (weak === 0 && offline === 0 && unknown === 0) {{
                el.style.color = '#4CAF50';
                el.textContent = '\\u2713 No issues';
                el.title = 'No weak, offline, or unknown-attachment devices';
                return;
            }}
            const parts = [];
            if (weak) parts.push(`${{weak}} weak`);
            if (offline) parts.push(`${{offline}} offline`);
            if (unknown) parts.push(`${{unknown}} unknown link`);
            el.style.color = (offline || weak) ? '#F44336' : '#FFC107';
            el.textContent = '\\u26a0 ' + parts.join(' \\u00b7 ');
            el.title = `Weak (device LQI<50 to coordinator): ${{weak}}  |  Offline: ${{offline}}  |  `
                + `Unknown attachment: ${{unknown}}  |  Estimated attachment: ${{estimated}}`;
        }}

        function updateOldestSeen() {{
            // Find the oldest last_seen timestamp from all devices
            // This indicates how stale the neighbor data might be
            const lastSeenDates = nodesData
                .filter(n => n.last_seen && !n.is_coordinator)
                .map(n => new Date(n.last_seen))
                .filter(d => !isNaN(d.getTime()));

            if (lastSeenDates.length === 0) {{
                document.getElementById('oldestSeen').textContent = '';
                return;
            }}

            const oldestDate = new Date(Math.min(...lastSeenDates));
            const now = new Date();
            const diffMs = now - oldestDate;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMins / 60);
            const diffDays = Math.floor(diffHours / 24);

            let relativeTime;
            if (diffMins < 1) relativeTime = 'just now';
            else if (diffMins < 60) relativeTime = `${{diffMins}}m ago`;
            else if (diffHours < 24) relativeTime = `${{diffHours}}h ago`;
            else relativeTime = `${{diffDays}}d ago`;

            // Color code based on age
            let color = '#4CAF50';  // Green - recent
            if (diffHours >= 24) color = '#F44336';  // Red - very old
            else if (diffHours >= 6) color = '#FFC107';  // Yellow - getting stale

            const el = document.getElementById('oldestSeen');
            el.style.color = color;
            el.textContent = `Oldest seen: ${{relativeTime}}`;
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

            // Update data age display
            updateDataAge();
            updateOldestSeen();
            updateHealthSummary();
            // Update every minute
            setInterval(updateDataAge, 60000);
            setInterval(updateOldestSeen, 60000);
        }});

        const nodeMap = {{}};
        nodesData.forEach(n => nodeMap[n.id] = n);

        const container = document.getElementById('graph');
        // The header can wrap to more lines (e.g. with route controls); start the
        // graph and the pinned card just below it instead of at a fixed 140px.
        function fitGraphTop() {{
            if (!routesMeta) return;  // keep the v1.3 layout untouched without routes
            const h =document.querySelector('.header').offsetHeight;
            container.style.top = h + 'px';
            const card = document.getElementById('tooltip');
            if (card) card.style.top = window.innerWidth > 600 ? (h + 8) + 'px' : '';
        }}
        fitGraphTop();
        let width = container.clientWidth;
        let height = container.clientHeight;

        const svg = d3.select('#graph')
            .append('svg')
            .attr('width', '100%')
            .attr('height', '100%')
            .attr('viewBox', [0, 0, width, height]);

        const g = svg.append('g');

        // Add floorplan background if available
        let floorplanGroup = null;
        let floorplanVisible = hasFloorplan;
        let floorplanBounds = {{ width: width, height: height }};

        console.log('[Floorplan] hasFloorplan:', hasFloorplan);
        console.log('[Floorplan] SVG content length:', floorplanSvgContent ? floorplanSvgContent.length : 0);

        if (hasFloorplan && floorplanSvgContent) {{
            try {{
                floorplanGroup = g.append('g')
                    .attr('class', 'floorplan-layer')
                    .attr('opacity', 0.8);

                // Parse the SVG content to extract it properly
                const parser = new DOMParser();
                const svgDoc = parser.parseFromString(floorplanSvgContent, 'image/svg+xml');
                const svgElement = svgDoc.documentElement;

                // Check for parsing errors
                const parserError = svgDoc.querySelector('parsererror');
                if (parserError) {{
                    console.error('[Floorplan] SVG parsing error:', parserError.textContent);
                }}

                // Get the original viewBox or dimensions
                let viewBox = svgElement.getAttribute('viewBox');
                let svgWidth = parseFloat(svgElement.getAttribute('width')) || width;
                let svgHeight = parseFloat(svgElement.getAttribute('height')) || height;

                console.log('[Floorplan] viewBox:', viewBox);
                console.log('[Floorplan] dimensions:', svgWidth, 'x', svgHeight);

                if (viewBox) {{
                    const vb = viewBox.split(/[\s,]+/).map(parseFloat);
                    svgWidth = vb[2] || svgWidth;
                    svgHeight = vb[3] || svgHeight;
                }}

                floorplanBounds = {{ width: svgWidth, height: svgHeight }};

                // Use a fixed scale factor (1 SVG unit = 1 graph unit)
                // This keeps the floorplan and nodes at consistent relative sizes
                const scale = 0.5;
                const offsetX = (width - svgWidth * scale) / 2;
                const offsetY = (height - svgHeight * scale) / 2;

                console.log('[Floorplan] scale:', scale, 'offset:', offsetX, offsetY);

                // Add a foreignObject to embed the SVG
                floorplanGroup.append('foreignObject')
                    .attr('x', offsetX)
                    .attr('y', offsetY)
                    .attr('width', svgWidth * scale)
                    .attr('height', svgHeight * scale)
                    .append('xhtml:div')
                    .style('width', '100%')
                    .style('height', '100%')
                    .html(floorplanSvgContent);

                // Store transform info for position normalization
                floorplanGroup.datum({{
                    scale: scale,
                    offsetX: offsetX,
                    offsetY: offsetY,
                    originalWidth: svgWidth,
                    originalHeight: svgHeight
                }});

                console.log('[Floorplan] Successfully added floorplan layer');
                // Set initial body class for floorplan background
                document.body.classList.add('floorplan-active');
            }} catch (err) {{
                console.error('[Floorplan] Error adding floorplan:', err);
            }}
        }} else {{
            console.log('[Floorplan] Skipping - hasFloorplan:', hasFloorplan, 'content exists:', !!floorplanSvgContent);
        }}

        // Coordinate system: 1 SVG unit = 1 inch, 12 units = 1 foot
        const UNITS_PER_FOOT = 12;
        const GRID_SPACING_FT = 10;

        function feetToUnits(feet) {{
            return feet * UNITS_PER_FOOT;
        }}

        function unitsToFeet(units) {{
            return units / UNITS_PER_FOOT;
        }}

        // Grid layer for visual positioning reference
        let gridGroup = null;
        let gridVisible = false;

        function createGrid() {{
            if (!hasFloorplan || !floorplanGroup) return;

            const fpData = floorplanGroup.datum();
            if (!fpData) return;

            const {{ scale, offsetX, offsetY, originalWidth, originalHeight }} = fpData;

            // Calculate grid dimensions in feet
            const widthFeet = Math.ceil(originalWidth / UNITS_PER_FOOT);
            const heightFeet = Math.ceil(originalHeight / UNITS_PER_FOOT);

            gridGroup = g.append('g')
                .attr('class', 'grid-layer')
                .style('display', 'none');

            // Vertical lines every GRID_SPACING_FT feet
            for (let ft = 0; ft <= widthFeet; ft += GRID_SPACING_FT) {{
                const x = offsetX + (ft * UNITS_PER_FOOT * scale);
                gridGroup.append('line')
                    .attr('x1', x)
                    .attr('y1', offsetY)
                    .attr('x2', x)
                    .attr('y2', offsetY + originalHeight * scale)
                    .attr('stroke', '#444')
                    .attr('stroke-width', 1)
                    .attr('stroke-dasharray', '4,4')
                    .attr('opacity', 0.5);

                // Label
                gridGroup.append('text')
                    .attr('x', x)
                    .attr('y', offsetY - 5)
                    .attr('fill', '#666')
                    .attr('font-size', '10px')
                    .attr('text-anchor', 'middle')
                    .text(ft + 'ft');
            }}

            // Horizontal lines every GRID_SPACING_FT feet
            for (let ft = 0; ft <= heightFeet; ft += GRID_SPACING_FT) {{
                const y = offsetY + (ft * UNITS_PER_FOOT * scale);
                gridGroup.append('line')
                    .attr('x1', offsetX)
                    .attr('y1', y)
                    .attr('x2', offsetX + originalWidth * scale)
                    .attr('y2', y)
                    .attr('stroke', '#444')
                    .attr('stroke-width', 1)
                    .attr('stroke-dasharray', '4,4')
                    .attr('opacity', 0.5);

                // Label
                gridGroup.append('text')
                    .attr('x', offsetX - 5)
                    .attr('y', y + 3)
                    .attr('fill', '#666')
                    .attr('font-size', '10px')
                    .attr('text-anchor', 'end')
                    .text(ft + 'ft');
            }}

            console.log('[Grid] Created grid: ' + widthFeet + 'ft x ' + heightFeet + 'ft');
        }}

        function toggleGrid(btn) {{
            if (!gridGroup) return;
            gridVisible = !gridVisible;
            gridGroup.style('display', gridVisible ? null : 'none');
            btn.classList.toggle('active', gridVisible);
            btn.textContent = gridVisible ? 'Hide Grid' : 'Show Grid';
        }}

        // Create grid after floorplan
        if (hasFloorplan) {{
            createGrid();
        }}

        function toggleFloorplan(btn) {{
            if (!floorplanGroup) return;
            floorplanVisible = !floorplanVisible;
            floorplanGroup.style('display', floorplanVisible ? null : 'none');
            btn.classList.toggle('active', floorplanVisible);
            btn.textContent = floorplanVisible ? 'Show Floorplan' : 'Hide Floorplan';
            // Toggle body background
            document.body.classList.toggle('floorplan-active', floorplanVisible);
        }}

        let currentTransform = d3.zoomIdentity;

        const zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on('zoom', (event) => {{
                currentTransform = event.transform;
                g.attr('transform', event.transform);
            }});

        svg.call(zoom);

        // Mouse position display (bottom-left corner)
        svg.on('mousemove', (event) => {{
            const [mx, my] = d3.pointer(event);
            const worldX = (mx - currentTransform.x) / currentTransform.k;
            const worldY = (my - currentTransform.y) / currentTransform.k;
            const pos = screenToFeet(worldX, worldY);
            const coordEl = document.getElementById('coordDisplay');
            if (pos.isFeet) {{
                coordEl.textContent = pos.x + ' ft, ' + pos.y + ' ft';
            }} else {{
                coordEl.textContent = Math.round(worldX) + ', ' + Math.round(worldY);
            }}
        }});

        function getNodeColor(d) {{
            if (d.is_coordinator) return '#00d4ff';
            if (d.device_type === 'Router') return '#8BC34A';
            return '#FFC107';
        }}

        function getLqiColor(lqi) {{
            // Bands calibrated for TI Z-Stack, where LQI is compressed and rarely
            // exceeds ~110 even on strong links (this network's observed max ~105).
            if (lqi === null || lqi === undefined) return '#888';
            if (lqi >= 90) return '#4CAF50';   // excellent
            if (lqi >= 65) return '#8BC34A';   // good
            if (lqi >= 45) return '#FFC107';   // fair
            return '#F44336';                  // weak
        }}

        function getNodeRadius(d) {{
            if (d.is_coordinator) return 15;
            if (d.device_type === 'Router') return 11;
            return 8;
        }}

        // Two candidate trees: neighbour/route-table based (v1.3) and, when
        // zha_routes data exists, route-record based (parent = first relay).
        const neighborPrimaryLinks = linksData.filter(l => l.type === 'primary');
        const siblingLinks = linksData.filter(l => l.type === 'sibling');
        let hierarchyMode = routesMeta ? 'routes' : 'neighbor';
        let primaryLinks = hierarchyMode === 'routes' ? routePrimaryLinks : neighborPrimaryLinks;

        const simulation = d3.forceSimulation(nodesData)
            .force('link', d3.forceLink(primaryLinks.concat(siblingLinks)).id(d => d.id).distance(100).strength(0.5))
            .force('charge', d3.forceManyBody().strength(-300))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collision', d3.forceCollide().radius(d => getNodeRadius(d) + 5));

        function getFloorplanScale() {{
            if (!hasFloorplan) return 1;
            return 0.5;  // Fixed scale used for floorplan display
        }}

        // Convert screen coordinates to feet (relative to floorplan origin)
        function screenToFeet(screenX, screenY) {{
            if (!hasFloorplan || !floorplanGroup) {{
                // No floorplan - store as normalized viewport coordinates
                return {{ x: screenX / width, y: screenY / height, isFeet: false }};
            }}

            const fpData = floorplanGroup.datum();
            if (!fpData) {{
                return {{ x: screenX / width, y: screenY / height, isFeet: false }};
            }}

            const {{ scale, offsetX, offsetY }} = fpData;

            // Convert screen position to SVG units, then to feet
            const svgX = (screenX - offsetX) / scale;
            const svgY = (screenY - offsetY) / scale;

            return {{
                x: Math.round(unitsToFeet(svgX) * 10) / 10,  // Round to 1 decimal
                y: Math.round(unitsToFeet(svgY) * 10) / 10,
                isFeet: true
            }};
        }}

        // Convert feet (relative to floorplan origin) to screen coordinates
        function feetToScreen(feetX, feetY, isFeet) {{
            if (!isFeet) {{
                // Legacy normalized viewport coordinates
                return {{ x: feetX * width, y: feetY * height }};
            }}

            if (!hasFloorplan || !floorplanGroup) {{
                // No floorplan - can't convert feet, use center
                return {{ x: width / 2, y: height / 2 }};
            }}

            const fpData = floorplanGroup.datum();
            if (!fpData) {{
                return {{ x: width / 2, y: height / 2 }};
            }}

            const {{ scale, offsetX, offsetY }} = fpData;

            // Convert feet to SVG units, then to screen position
            const svgX = feetToUnits(feetX);
            const svgY = feetToUnits(feetY);

            return {{
                x: svgX * scale + offsetX,
                y: svgY * scale + offsetY
            }};
        }}

        // Node position bounds (in feet)
        const BOUNDS_FT = {{ minX: -100, maxX: 150, minY: 0, maxY: 250 }};
        const boundsMin = feetToScreen(BOUNDS_FT.minX, BOUNDS_FT.minY, true);
        const boundsMax = feetToScreen(BOUNDS_FT.maxX, BOUNDS_FT.maxY, true);
        const BOUNDS = {{
            minX: Math.min(boundsMin.x, boundsMax.x),
            maxX: Math.max(boundsMin.x, boundsMax.x),
            minY: Math.min(boundsMin.y, boundsMax.y),
            maxY: Math.max(boundsMin.y, boundsMax.y)
        }};

        // Server-side position storage
        let serverPositions = {{}};
        let positionsDirty = false;
        let saveTimeout = null;

        async function loadPositionsFromServer() {{
            try {{
                const response = await fetch('/positions');
                if (response.ok) {{
                    serverPositions = await response.json();
                    console.log('[Positions] Loaded', Object.keys(serverPositions).length, 'positions from server');

                    let loadedCount = 0;
                    nodesData.forEach(node => {{
                        if (serverPositions[node.id]) {{
                            const pos = serverPositions[node.id];
                            const screen = feetToScreen(pos.x, pos.y, pos.isFeet !== false);
                            node.x = screen.x;
                            node.y = screen.y;
                            if (pos.fixed) {{
                                node.fx = screen.x;
                                node.fy = screen.y;
                            }}
                            loadedCount++;
                        }}
                    }});
                    console.log('[Positions] Applied positions to', loadedCount, 'nodes');
                    return loadedCount > 0;
                }}
            }} catch (e) {{
                console.error('[Positions] Failed to load from server:', e);
            }}
            return false;
        }}

        async function savePositionsToServer() {{
            const positions = {{}};
            nodesData.forEach(node => {{
                if (node.fx !== null && node.fx !== undefined) {{
                    const feet = screenToFeet(node.x, node.y);
                    positions[node.id] = {{
                        x: feet.x,
                        y: feet.y,
                        isFeet: feet.isFeet,
                        fixed: true
                    }};
                }}
            }});

            try {{
                const response = await fetch('/positions', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(positions)
                }});
                if (response.ok) {{
                    serverPositions = positions;
                    positionsDirty = false;
                    console.log('[Positions] Saved', Object.keys(positions).length, 'positions to server');
                    return true;
                }}
            }} catch (e) {{
                console.error('[Positions] Failed to save to server:', e);
            }}
            return false;
        }}

        // Debounced save - waits 500ms after last change before saving
        function scheduleSave() {{
            positionsDirty = true;
            if (saveTimeout) {{
                clearTimeout(saveTimeout);
            }}
            saveTimeout = setTimeout(async () => {{
                if (positionsDirty) {{
                    await savePositionsToServer();
                }}
            }}, 500);
        }}

        function savePositions() {{
            savePositionsToServer().then(success => {{
                if (success) {{
                    showToast('Positions saved!');
                }} else {{
                    showToast('Failed to save positions');
                }}
            }});
        }}

        function showToast(message) {{
            const toast = document.createElement('div');
            toast.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#00d4ff;color:#000;padding:10px 20px;border-radius:4px;font-size:14px;z-index:9999;';
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 2000);
        }}

        async function resetPositions() {{
            // Clear server positions
            try {{
                await fetch('/positions', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{}})
                }});
            }} catch (e) {{
                console.error('[Positions] Failed to clear server positions:', e);
            }}

            serverPositions = {{}};
            nodesData.forEach(node => {{
                node.fx = null;
                node.fy = null;
            }});
            simulation.alpha(1).restart();
            showToast('Layout reset!');
        }}

        // Load positions on startup (async)
        let hasPositions = false;
        loadPositionsFromServer().then(loaded => {{
            hasPositions = loaded;
            if (loaded) {{
                simulation.alpha(0.1);
            }}
            // Fit view to show all content on initial load
            setTimeout(() => fitView(), 100);
        }});

        function getRectilinearPath(source, target) {{
            const midY = (source.y + target.y) / 2;
            return `M${{source.x}},${{source.y}} L${{source.x}},${{midY}} L${{target.x}},${{midY}} L${{target.x}},${{target.y}}`;
        }}


        function getSourceTypeColor(sourceType) {{
            switch(sourceType) {{
                case 'route': return '#00d4ff';
                case 'parent': return '#8BC34A';
                case 'neighbor': return '#FFC107';
                case 'inferred': return '#FF9800';
                case 'fallback': return '#666';
                case 'zroute': return '#CE93D8';
                case 'zroute_startup': return '#CE93D8';
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

        const primaryLinksGroup = g.append('g').attr('class', 'primary-links-group');
        let link = primaryLinksGroup.selectAll('path');

        function renderPrimaryLinks() {{
          link = primaryLinksGroup.selectAll('path')
            .data(primaryLinks)
            .join('path')
            .attr('class', d => `link primary ${{d.source_type}}`)
            .attr('stroke', d => getSourceTypeColor(d.source_type))
            .attr('stroke-width', d => {{
                if (d.lqi == null) return 1.5;  // unknown quality - de-emphasized
                if (d.lqi >= 90) return 3;
                if (d.lqi >= 65) return 2.5;
                if (d.lqi >= 45) return 2;
                return 1.5;
            }})
            .attr('stroke-dasharray', d => {{
                // Stale links (>24h) shown dashed
                if (!d.source_last_seen) return '6, 3';
                const hoursSince = (exportTime - new Date(d.source_last_seen)) / 3600000;
                if (hoursSince > 24) return '6, 3';
                return null;
            }})
            .attr('stroke-opacity', d => {{
                if (!d.source_last_seen) return 0.35;
                const hoursSince = (exportTime - new Date(d.source_last_seen)) / 3600000;
                if (hoursSince > 24) return 0.35;
                return 0.6;
            }})
            .style('display', d => linkTypeVisibility[d.source_type] ? null : 'none');
          link.selectAll('title').remove();
          link.append('title').text(d => treeLinkTitle(d));
          renderTreeLabels();
        }}
        renderPrimaryLinks();

        const neighborLinksGroup = g.append('g').attr('class', 'neighbor-links-group');
        const neighborLabelsGroup = g.append('g').attr('class', 'neighbor-labels-group');

        const node = g.append('g')
            .attr('class', 'nodes-group')
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
            .attr('dy', d => getNodeRadius(d) + 10)
            .text(d => d.name.length > 15 ? d.name.substring(0, 14) + '...' : d.name);

        node.filter(d => d.lqi !== null)
            .append('text')
            .attr('class', 'lqi-badge')
            .attr('dy', 3)
            .attr('fill', d => getLqiColor(d.lqi))
            .text(d => d.lqi);

        node.filter(d => d.neighbors && d.neighbors.length > 0)
            .append('g')
            .attr('class', 'neighbor-badge')
            .attr('transform', d => `translate(${{getNodeRadius(d) - 3}}, ${{-getNodeRadius(d) + 3}})`)
            .on('click', (event, d) => {{
                event.stopPropagation();
                showNeighborOverlay(d);
            }})
            .call(g => {{
                g.append('circle')
                    .attr('r', 5)
                    .attr('fill', '#00d4ff')
                    .attr('stroke', '#fff')
                    .attr('stroke-width', 1);
                g.append('text')
                    .attr('dy', 3)
                    .attr('text-anchor', 'middle')
                    .attr('fill', '#000')
                    .attr('font-size', '6px')
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
            syncTreeLabels();
        }}

        function clearSelection() {{
            clearRouteHighlight();
            selectedNode = null;
            node.classed('selected', false);
            node.classed('dimmed', false);
            link.classed('dimmed', false);
            link.classed('highlighted', false);
            siblingLink.classed('dimmed', false);
            siblingLink.classed('highlighted', false);
            neighborLinksGroup.selectAll('*').remove();
            neighborLabelsGroup.selectAll('*').remove();
            syncTreeLabels();
        }}

        svg.on('click', () => {{
            clearSelection();
            hideCard();
        }});

        const tooltip = document.getElementById('tooltip');

        // Pinned corner card: fixed top-right, updated on hover and on tap, with
        // a close button. It never follows the cursor, so it can't be clipped.
        function showCard(content) {{
            tooltip.innerHTML = '<span class="card-close" onclick="hideCard()" title="Close">\\u00d7</span>' + content;
            tooltip.classList.add('visible');
        }}

        function hideCard() {{
            tooltip.classList.remove('visible');
        }}

        function nodeDetailHtml(d) {{
            let parentInfo = 'None (Coordinator)';
            const sourceTypeLabels = {{
                'route': 'Route table',
                'parent': 'Parent relationship (confirmed)',
                'neighbor': 'Strongest neighbour',
                'inferred': 'Estimated (strongest signal, no reported parent)',
                'fallback': 'Unknown (no connection data)',
                'zroute': 'Route record (zha_routes, live)',
                'zroute_startup': 'Route record (startup only, age unknown)',
                'sibling': 'Sibling'
            }};
            const sourceTypeColors = {{
                'route': '#00d4ff',
                'parent': '#8BC34A',
                'neighbor': '#FFC107',
                'inferred': '#FF9800',
                'fallback': '#666',
                'zroute': '#CE93D8',
                'zroute_startup': '#CE93D8',
                'sibling': '#888'
            }};
            if (d.parents && d.parents.length > 0) {{
                parentInfo = d.parents.map(p => {{
                    const sourceLabel = sourceTypeLabels[p.source_type] || p.source_type;
                    const sourceColor = sourceTypeColors[p.source_type] || '#888';
                    // Show bidirectional LQI: forward (child→parent) and reverse (parent→child)
                    let lqiDisplay = '';
                    if (p.lqi != null || p.lqi_reverse != null) {{
                        const fwd = p.lqi != null ? p.lqi : '?';
                        const rev = p.lqi_reverse != null ? p.lqi_reverse : '?';
                        lqiDisplay = ` (LQI: ${{fwd}} \\u2192 / \\u2190 ${{rev}})`;
                    }}
                    // Show data staleness
                    const dataAge = p.source_last_seen ? formatLastSeen(p.source_last_seen) : 'unknown';
                    return `${{p.name}}${{lqiDisplay}} <span style="color:${{sourceColor}};font-size:9px">[${{sourceLabel}}]</span> <span style="color:#666;font-size:9px">(data: ${{dataAge}})</span>`;
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
                    const dirStr = v => v != null ? `<span style="color:${{getLqiColor(v)}}">${{v}}</span>` : '?';
                    const lqiStr = `${{dirStr(hop.lqi_fwd)}} → / ← ${{dirStr(hop.lqi_rev)}}`;
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

            // Calculate depth from path length (coordinator = 0)
            const depthValue = d.is_coordinator ? 0 : (d.path_to_coordinator ? d.path_to_coordinator.length : null);
            const depthDisplay = depthValue !== null ? depthValue : 'N/A';

            // Build entities section for tooltip
            let entitiesHtml = '';
            if (d.entity_details && d.entity_details.length > 0) {{
                const entityLines = d.entity_details.slice(0, 5).map(e => {{
                    const stateColor = e.state === 'on' ? '#4CAF50' : (e.state === 'off' ? '#666' : '#888');
                    return `<div style="font-size:10px;margin-left:10px;color:#aaa">• ${{e.friendly_name}} <span style="color:${{stateColor}}">${{e.state}}</span></div>`;
                }}).join('');
                const moreCount = d.entity_details.length > 5 ? `<div style="font-size:10px;margin-left:10px;color:#666">... and ${{d.entity_details.length - 5}} more</div>` : '';
                entitiesHtml = `<div style="margin-top:3px">Entities: <span style="color:#888">(${{d.entity_details.length}})</span></div>${{entityLines}}${{moreCount}}`;
            }}

            // Get position in feet for display
            const posFeet = screenToFeet(d.x, d.y);
            const positionDisplay = posFeet.isFeet
                ? `${{posFeet.x}}ft × ${{posFeet.y}}ft`
                : `${{Math.round(d.x)}}px × ${{Math.round(d.y)}}px`;

            const content = `
                <div><strong style="color:#00d4ff">${{d.user_given_name || d.name}}</strong></div>
                ${{d.user_given_name ? `<div style="color:#888;font-size:10px">${{d.name}}</div>` : ''}}
                <div>Type: <span>${{d.device_type}}</span>${{d.nwk ? ` <span style="color:#666;font-size:10px">(NWK: ${{d.nwk}})</span>` : ''}}</div>
                <div>Power: <span>${{d.power_source || 'Unknown'}}</span>${{d.available === false ? ' <span style="color:#F44336">• Offline</span>' : ''}}</div>
                <div>Device LQI <span style="color:#555;font-size:9px">(signal of last hop to coordinator, not this device's own link)</span>: <span style="color:${{getLqiColor(d.lqi)}}">${{d.lqi != null ? d.lqi : 'not reported'}}</span> | Hops (est.): <span>${{depthDisplay}}</span></div>
                <div>Position: <span style="color:#888">${{positionDisplay}}</span></div>
                ${{routeDetailHtml(d)}}
                <div>Path${{d.route ? ' <span style="color:#555;font-size:9px">(neighbour estimate)</span>' : ''}}: <span style="font-size:11px">${{pathInfo}}</span></div>
                <div>Connected via: <span>${{parentInfo}}</span></div>
                <div style="color:#555;font-size:9px;margin-top:-2px">Link LQI = neighbour-table values (→ child→parent / ← parent→child); "?" = not reported</div>
                <div>Manufacturer: <span>${{d.manufacturer || 'Unknown'}}</span></div>
                <div>Model: <span>${{d.model || 'Unknown'}}</span></div>
                ${{entitiesHtml}}
                <div>Last seen: <span>${{formatLastSeen(d.last_seen)}}</span></div>
                ${{d.neighbors && d.neighbors.length > 0 ? `<div>Neighbors: <span>${{d.neighbors.length}} (click to show)</span></div>` : ''}}
                ${{haDeviceUrl ? `<div style="margin-top:5px"><a href="${{haDeviceUrl}}" target="_blank" style="color:#00d4ff;text-decoration:none;">Open in Home Assistant &rarr;</a></div>` : ''}}
                ${{(d.device_type === 'Router' || d.is_coordinator) ? `<div style="margin-top:6px"><button onclick="rescanRouter('${{d.id}}')" style="background:#00d4ff;color:#000;border:none;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:11px">Rescan this router</button></div>` : ''}}
                <div style="color:#666;margin-top:5px;font-size:10px">Drag to move | Click to select</div>
            `;
            return content;
        }}

        // Hover (desktop) and tap (mobile) both populate the pinned card.
        node.on('mouseenter', (event, d) => showCard(nodeDetailHtml(d)))
        .on('click', (event, d) => {{
            event.stopPropagation();
            showCard(nodeDetailHtml(d));
            // Second click on the same device clears; otherwise select it,
            // showing neighbours (if any) and its route path (if routes on).
            const wasSelected = (selectedNode && selectedNode.id === d.id) || routeSelectedId === d.id;
            clearSelection();
            if (!wasSelected) {{
                if (d.neighbors && d.neighbors.length > 0) showNeighborLinks(d);
                highlightRoute(d);
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
            syncTreeLabels();
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
            d.fx = Math.max(BOUNDS.minX, Math.min(BOUNDS.maxX, event.x));
            d.fy = Math.max(BOUNDS.minY, Math.min(BOUNDS.maxY, event.y));
        }}

        function dragended(event, d) {{
            if (!event.active) simulation.alphaTarget(0);
            d3.select(event.sourceEvent.target.parentNode).classed('dragging', false);
            highlightConnectedLinks(d.id, false);
            clearSelection();
            // Schedule auto-save after drag (debounced)
            scheduleSave();
        }}

        simulation.on('tick', () => {{
            nodesData.forEach(d => {{
                d.x = Math.max(BOUNDS.minX, Math.min(BOUNDS.maxX, d.x));
                d.y = Math.max(BOUNDS.minY, Math.min(BOUNDS.maxY, d.y));
                if (d.fx !== null && d.fx !== undefined) {{
                    d.fx = Math.max(BOUNDS.minX, Math.min(BOUNDS.maxX, d.fx));
                    d.fy = Math.max(BOUNDS.minY, Math.min(BOUNDS.maxY, d.fy));
                }}
            }});

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

        let currentSearchTerm = '';

        function handleSearch(term) {{
            currentSearchTerm = term.toLowerCase().trim();
            const clearBtn = document.getElementById('clearSearch');
            clearBtn.classList.toggle('visible', currentSearchTerm.length > 0);
            applyFilters();
        }}

        function clearSearch() {{
            document.getElementById('searchInput').value = '';
            currentSearchTerm = '';
            document.getElementById('clearSearch').classList.remove('visible');
            document.getElementById('searchCount').textContent = '';
            applyFilters();
        }}

        function matchesSearch(d, term) {{
            if (!term) return true;

            // Match device name
            const name = (d.name || '').toLowerCase();
            if (name.includes(term)) return true;

            // Match user given name
            const userGivenName = (d.user_given_name || '').toLowerCase();
            if (userGivenName.includes(term)) return true;

            // Match nwk address (with or without 0x prefix)
            const nwk = (d.nwk || '').toString().toLowerCase();
            if (nwk.includes(term)) return true;
            if (nwk.replace('0x', '').includes(term.replace('0x', ''))) return true;

            // Match entity names
            if (d.entity_names && d.entity_names.length > 0) {{
                for (const entityName of d.entity_names) {{
                    if (entityName.toLowerCase().includes(term)) return true;
                }}
            }}

            // Match manufacturer
            const manufacturer = (d.manufacturer || '').toLowerCase();
            if (manufacturer.includes(term)) return true;

            // Match model
            const model = (d.model || '').toLowerCase();
            if (model.includes(term)) return true;

            return false;
        }}

        function applyFilters() {{
            let visibleCount = 0;
            let matchCount = 0;

            node.each(function(d) {{
                const minutesAgo = getMinutesSinceLastSeen(d.last_seen);
                const passesTimeFilter = timeFilterMinutes === 0 || minutesAgo <= timeFilterMinutes || isNaN(minutesAgo);
                const passesTypeFilter = showEndDevices || d.device_type !== 'EndDevice';
                const passesSearch = matchesSearch(d, currentSearchTerm);
                const visible = passesTimeFilter && passesTypeFilter;

                d.visible = visible;
                d.searchMatch = passesSearch;
                d3.select(this).classed('hidden', !visible);

                // Dim non-matching nodes when searching
                d3.select(this).classed('dimmed', visible && currentSearchTerm && !passesSearch);

                if (visible) visibleCount++;
                if (visible && passesSearch) matchCount++;
            }});

            link.classed('hidden', d => !d.source.visible || !d.target.visible);

            // Dim links that don't connect to matching nodes
            link.classed('dimmed', d => {{
                if (!currentSearchTerm) return false;
                return !d.source.searchMatch && !d.target.searchMatch;
            }});

            applyRouteFilters();
            syncTreeLabels();
            document.getElementById('visibleCount').textContent = `(Showing: ${{visibleCount}})`;

            // Update search count
            const searchCountEl = document.getElementById('searchCount');
            if (currentSearchTerm) {{
                searchCountEl.textContent = `${{matchCount}} match${{matchCount !== 1 ? 'es' : ''}}`;
            }} else {{
                searchCountEl.textContent = '';
            }}
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

        function fitView() {{
            const padding = 50;
            const bx = BOUNDS.minX - padding;
            const by = BOUNDS.minY - padding;
            const bw = (BOUNDS.maxX - BOUNDS.minX) + padding * 2;
            const bh = (BOUNDS.maxY - BOUNDS.minY) + padding * 2;

            const scale = Math.min(width / bw, height / bh) * 0.9;
            const tx = width / 2 - (bx + bw / 2) * scale;
            const ty = height / 2 - (by + bh / 2) * scale;

            svg.call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
        }}

        function showNeighborOverlay(nodeData) {{
            const overlay = document.getElementById('neighborOverlay');
            const title = document.getElementById('overlayTitle');
            const subtitle = document.getElementById('overlaySubtitle');
            const grid = document.getElementById('neighborGrid');

            title.textContent = `${{nodeData.name}} - Neighbor Table`;
            subtitle.textContent = `${{nodeData.neighbors.length}} neighbors | Device LQI (to coordinator): ${{nodeData.lqi != null ? nodeData.lqi : 'not reported'}}`;

            const sortedNeighbors = [...nodeData.neighbors].sort((a, b) => (b.lqi || 0) - (a.lqi || 0));

            let html = '';
            for (const neighbor of sortedNeighbors) {{
                const neighborNode = nodeMap[neighbor.ieee];
                const neighborName = neighborNode ? neighborNode.name : neighbor.ieee.substring(0, 17) + '...';
                // null LQI = "not reported" (TI Z-Stack), shown neutral - never as a red zero.
                const lqiKnown = neighbor.lqi != null;
                const lqiColor = getLqiColor(neighbor.lqi);
                const lqiPercent = lqiKnown ? Math.round((neighbor.lqi / 255) * 100) : 0;
                const lqiDisplay = lqiKnown ? neighbor.lqi : '<span style="font-size:11px">not reported</span>';
                const notInNetwork = !neighborNode ? 'not-in-network' : '';

                // Look up reverse LQI (how does the neighbor see this device?)
                let reverseLqi = null;
                if (neighborNode && neighborNode.neighbors) {{
                    const reverseEntry = neighborNode.neighbors.find(n => n.ieee === nodeData.id);
                    if (reverseEntry) reverseLqi = reverseEntry.lqi;
                }}
                const reverseLqiColor = reverseLqi != null ? getLqiColor(reverseLqi) : '#666';
                const reverseDisplay = reverseLqi != null ? reverseLqi : '?';

                html += `
                    <div class="neighbor-card ${{notInNetwork}}">
                        <div class="name">${{neighborName}}</div>
                        <div class="lqi-value" style="color:${{lqiColor}}">${{lqiDisplay}} <span style="font-size:11px;color:#888">\\u2192</span> <span style="font-size:11px;color:${{reverseLqiColor}}">\\u2190 ${{reverseDisplay}}</span></div>
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
            fitGraphTop();
            width = container.clientWidth;
            height = container.clientHeight;
            svg.attr('viewBox', [0, 0, width, height]);
            simulation.force('center', d3.forceCenter(width / 2, height / 2));
            simulation.alpha(0.3).restart();
        }});

        async function refreshData() {{
            const btn = document.getElementById('refreshBtn');
            const originalText = btn.textContent;
            btn.textContent = 'Refreshing';
            btn.classList.add('loading');
            btn.disabled = true;

            try {{
                // Start the refresh
                const response = await fetch('/refresh', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }}
                }});

                if (!response.ok) {{
                    const error = await response.text();
                    throw new Error(error);
                }}

                // Poll for completion. The active zha-toolkit scan queries every
                // router, so allow up to ~5 minutes before giving up on the UI side
                // (the backend keeps running regardless).
                let attempts = 0;
                const maxAttempts = 300;  // 5 minutes max
                const pollInterval = 1000;  // 1 second

                while (attempts < maxAttempts) {{
                    await new Promise(r => setTimeout(r, pollInterval));
                    attempts++;

                    let progressMsg = '';
                    try {{
                        const statusResponse = await fetch('/status');
                        if (statusResponse.ok) {{
                            const status = await statusResponse.json();

                            if (status.refresh_error) {{
                                throw new Error(status.refresh_error);
                            }}

                            if (status.progress && status.progress.message) {{
                                progressMsg = status.progress.message;
                            }}

                            if (!status.is_refreshing) {{
                                // Refresh complete
                                window.location.reload();
                                return;
                            }}
                        }}
                    }} catch (pollErr) {{
                        console.error('[Refresh] Poll error:', pollErr);
                    }}

                    // Show live progress (per-router scan count) when available
                    if (progressMsg) {{
                        btn.textContent = progressMsg.length > 38 ? progressMsg.slice(0, 37) + '\\u2026' : progressMsg;
                    }} else {{
                        btn.textContent = `Refreshing (${{attempts}}s)`;
                    }}
                }}

                // Timeout
                throw new Error('Refresh timed out after 5 minutes');

            }} catch (err) {{
                console.error('[Refresh] Error:', err);
                alert('Refresh failed: ' + err.message);
                btn.textContent = originalText;
                btn.classList.remove('loading');
                btn.disabled = false;
            }}
        }}

        async function scanNetwork() {{
            const btn = document.getElementById('scanBtn');

            if (!confirm('This will trigger a full network scan, querying all routers for their neighbor tables.\\n\\nThe scan runs in the background and typically takes 2-5 minutes.\\nClick "Refresh Data" afterward to see updated neighbor tables.\\n\\nContinue?')) {{
                return;
            }}

            btn.textContent = 'Triggering...';
            btn.disabled = true;

            try {{
                const response = await fetch('/scan', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }}
                }});

                const data = await response.json();

                if (response.ok) {{
                    showToast(data.message || "Topology scan triggered. Click 'Refresh Data' in a few minutes.");
                }} else {{
                    showToast('Scan failed: ' + (data.message || 'Unknown error'));
                }}
            }} catch (err) {{
                console.error('[Scan] Error:', err);
                showToast('Failed to trigger scan: ' + err.message);
            }} finally {{
                btn.textContent = 'Scan Network';
                btn.disabled = false;
            }}
        }}

        async function regenerateUI() {{
            const btn = document.getElementById('regenBtn');
            const originalText = btn.textContent;
            btn.textContent = 'Regenerating';
            btn.classList.add('loading');
            btn.disabled = true;

            try {{
                const response = await fetch('/regenerate', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }}
                }});

                if (response.ok) {{
                    window.location.reload();
                }} else {{
                    const error = await response.text();
                    alert('Regenerate failed: ' + error);
                    btn.textContent = originalText;
                    btn.classList.remove('loading');
                    btn.disabled = false;
                }}
            }} catch (err) {{
                alert('Regenerate failed: ' + err.message);
                btn.textContent = originalText;
                btn.classList.remove('loading');
                btn.disabled = false;
            }}
        }}

        // Rescan a single router (from the detail card), then reload with fresh data.
        async function rescanRouter(ieee) {{
            const node = nodeMap[ieee];
            const label = node ? (node.user_given_name || node.name) : 'router';
            showToast('Rescanning ' + label + '...');
            try {{
                const r = await fetch('/rescan', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ ieee: ieee }})
                }});
                if (!r.ok) {{ showToast('Rescan failed: ' + (await r.text())); return; }}
                // Poll until the rescan + regenerate completes, then reload
                for (let i = 0; i < 180; i++) {{
                    await new Promise(res => setTimeout(res, 1000));
                    try {{
                        const sr = await fetch('/status');
                        if (sr.ok) {{
                            const s = await sr.json();
                            if (s.refresh_error) {{ showToast('Rescan failed: ' + s.refresh_error); return; }}
                            if (!s.is_refreshing) {{ window.location.reload(); return; }}
                        }}
                    }} catch (e) {{}}
                }}
                showToast('Rescan timed out');
            }} catch (err) {{
                showToast('Rescan failed: ' + err.message);
            }}
        }}
{ROUTE_JS}
{TREE_LQI_JS}
    </script>
</body>
</html>
'''

    # Write atomically (temp file + rename) so a concurrent page load never
    # reads a half-written topology.html.
    tmp_file = f"{output_file}.tmp"
    with open(tmp_file, 'w', encoding='utf-8') as f:
        f.write(html)
    os.replace(tmp_file, output_file)

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
