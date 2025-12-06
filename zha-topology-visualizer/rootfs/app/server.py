"""
ZHA Topology Visualization Server
Serves the HTML visualization and handles refresh requests.
Supports configurable auto-refresh.
"""

import json
import os
import sys
import threading
import time
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Import our modules
from main import export_data
from visualize import generate_visualization, find_latest_export

# Data directory
DATA_DIR = Path('/data')
OPTIONS_FILE = DATA_DIR / 'options.json'
HTML_FILE = DATA_DIR / 'topology.html'

# Global state
refresh_lock = threading.Lock()
last_refresh_time = 0


def read_options() -> dict:
    """Read add-on options from options.json."""
    if OPTIONS_FILE.exists():
        with open(OPTIONS_FILE) as f:
            return json.load(f)
    return {}


def do_refresh() -> tuple:
    """Perform data refresh and regenerate visualization."""
    global last_refresh_time

    with refresh_lock:
        try:
            print("\n" + "=" * 50)
            print("Starting data refresh...")
            print("=" * 50)

            # Export new data
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                json_file = loop.run_until_complete(export_data())
            finally:
                loop.close()

            # Generate visualization
            output_file = generate_visualization(json_file)

            last_refresh_time = time.time()
            print(f"\nRefresh complete! Serving: {output_file}")
            return True, None

        except Exception as e:
            error_msg = str(e)
            print(f"\nRefresh failed: {error_msg}")
            return False, error_msg


class VisualizationHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the visualization server."""

    def log_message(self, format, *args):
        print(f"[Server] {args[0]}")

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.serve_html()
        elif self.path == '/health':
            self.serve_health()
        elif self.path == '/status':
            self.serve_status()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/refresh':
            self.handle_refresh()
        else:
            self.send_error(404)

    def serve_html(self):
        """Serve the visualization HTML."""
        try:
            if not HTML_FILE.exists():
                # Generate on first access if not exists
                print("No visualization found, generating...")
                success, error = do_refresh()
                if not success:
                    self.send_error(500, f'Failed to generate visualization: {error}')
                    return

            with open(HTML_FILE, 'r', encoding='utf-8') as f:
                content = f.read()

            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', len(content.encode('utf-8')))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))

        except FileNotFoundError:
            self.send_error(404, 'Visualization file not found')
        except Exception as e:
            self.send_error(500, str(e))

    def serve_health(self):
        """Health check endpoint."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')

    def serve_status(self):
        """Status endpoint with details."""
        status = {
            'healthy': True,
            'last_refresh': last_refresh_time,
            'html_exists': HTML_FILE.exists(),
            'options': read_options()
        }

        content = json.dumps(status, indent=2)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(content.encode('utf-8')))
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def handle_refresh(self):
        """Handle refresh request."""
        print("\n" + "=" * 50)
        print("Manual refresh requested...")
        print("=" * 50)

        success, error = do_refresh()

        if success:
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(error.encode('utf-8'))


def auto_refresh_loop(interval_minutes: int):
    """Background thread for auto-refresh."""
    print(f"Auto-refresh enabled: every {interval_minutes} minutes")

    while True:
        time.sleep(interval_minutes * 60)
        print("\n" + "=" * 50)
        print(f"Auto-refresh triggered (every {interval_minutes} min)...")
        print("=" * 50)
        do_refresh()


def main():
    """Main entry point for the server."""
    print("=" * 50)
    print("ZHA Topology Visualization Server")
    print("=" * 50)

    # Read options
    options = read_options()
    auto_refresh_minutes = options.get('auto_refresh_minutes', 0)

    print(f"Configuration:")
    print(f"  - Auto-refresh: {auto_refresh_minutes} minutes (0 = disabled)")
    print(f"  - Data directory: {DATA_DIR}")
    print(f"  - HTML file: {HTML_FILE}")

    # Check if we have an existing visualization or need to generate
    if not HTML_FILE.exists():
        # Check for existing export
        latest = find_latest_export()
        if latest:
            print(f"\nFound existing export: {latest}")
            print("Generating visualization...")
            try:
                generate_visualization(latest)
            except Exception as e:
                print(f"Warning: Could not generate from existing export: {e}")
        else:
            print("\nNo existing data found. Will generate on first access.")

    # Start auto-refresh thread if configured
    if auto_refresh_minutes > 0:
        thread = threading.Thread(
            target=auto_refresh_loop,
            args=(auto_refresh_minutes,),
            daemon=True
        )
        thread.start()

    # Start HTTP server
    port = 8099
    server = HTTPServer(('0.0.0.0', port), VisualizationHandler)

    print(f"\n{'=' * 50}")
    print(f"Server running on port {port}")
    print(f"Access at: http://<your-ha-host>:{port}")
    print(f"{'=' * 50}")
    print("Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
