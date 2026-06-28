#!/bin/sh

# Get version from config.yaml
VERSION=$(python3 -c "import yaml; print(yaml.safe_load(open('/config.yaml'))['version'])" 2>/dev/null || echo "unknown")

echo "Starting ZHA Network Topology Visualizer v${VERSION}..."

# Read configuration from options.json (created by HA Supervisor)
if [ -f /data/options.json ]; then
    export USE_ZHA_TOOLKIT=$(cat /data/options.json | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('use_zha_toolkit', True)).lower())")
    export ZHA_TOOLKIT_TIMEOUT=$(cat /data/options.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('zha_toolkit_timeout', 180))")
    AUTO_REFRESH=$(cat /data/options.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('auto_refresh_minutes', 0))")
    DEBUG_MODE=$(cat /data/options.json | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('debug', False)).lower())")
    export DEBUG=$DEBUG_MODE
else
    export USE_ZHA_TOOLKIT=true
    export ZHA_TOOLKIT_TIMEOUT=180
    AUTO_REFRESH=0
    export DEBUG=false
fi

echo "Active scan via zha-toolkit: ${USE_ZHA_TOOLKIT} (timeout ${ZHA_TOOLKIT_TIMEOUT}s)"
echo "Auto-refresh interval: ${AUTO_REFRESH} minutes (0 = disabled)"

# Ensure data directory exists
mkdir -p /data

# Start the server
echo "Starting visualization server on port 8099..."
cd /app
exec python3 server.py
