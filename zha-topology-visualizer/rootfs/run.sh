#!/bin/sh

echo "Starting ZHA Network Topology Visualizer..."

# Read configuration from options.json (created by HA Supervisor)
if [ -f /data/options.json ]; then
    export TOPOLOGY_SCAN_WAIT=$(cat /data/options.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('topology_scan_wait', 60))")
    AUTO_REFRESH=$(cat /data/options.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('auto_refresh_minutes', 0))")
    DEBUG_MODE=$(cat /data/options.json | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('debug', False)).lower())")
    export DEBUG=$DEBUG_MODE
else
    export TOPOLOGY_SCAN_WAIT=60
    AUTO_REFRESH=0
    export DEBUG=false
fi

echo "Topology scan wait: ${TOPOLOGY_SCAN_WAIT}s"
echo "Auto-refresh interval: ${AUTO_REFRESH} minutes (0 = disabled)"

# Ensure data directory exists
mkdir -p /data

# Start the server
echo "Starting visualization server on port 8099..."
cd /app
exec python3 server.py
