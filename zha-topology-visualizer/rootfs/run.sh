#!/usr/bin/with-contenv bashio

bashio::log.info "Starting ZHA Network Topology Visualizer..."

# Export configuration as environment variables
export TOPOLOGY_SCAN_WAIT=$(bashio::config 'topology_scan_wait')
bashio::log.info "Topology scan wait: ${TOPOLOGY_SCAN_WAIT}s"

AUTO_REFRESH=$(bashio::config 'auto_refresh_minutes')
bashio::log.info "Auto-refresh interval: ${AUTO_REFRESH} minutes (0 = disabled)"

# Ensure data directory exists
mkdir -p /data

# Copy options to data directory for the Python scripts
bashio::log.info "Writing options to /data/options.json..."
echo "{\"auto_refresh_minutes\": ${AUTO_REFRESH}, \"topology_scan_wait\": ${TOPOLOGY_SCAN_WAIT}}" > /data/options.json

# Start the server
bashio::log.info "Starting visualization server on port 8099..."
cd /app
exec python3 server.py
