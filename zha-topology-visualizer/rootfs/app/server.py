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
is_refreshing = False
refresh_error = None


def read_options() -> dict:
    """Read add-on options from options.json."""
    if OPTIONS_FILE.exists():
        with open(OPTIONS_FILE) as f:
            return json.load(f)
    return {}


def do_refresh() -> tuple:
    """Perform data refresh and regenerate visualization."""
    global last_refresh_time, is_refreshing, refresh_error

    with refresh_lock:
        is_refreshing = True
        refresh_error = None
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
            is_refreshing = False
            return True, None

        except Exception as e:
            error_msg = str(e)
            print(f"\nRefresh failed: {error_msg}")
            import traceback
            traceback.print_exc()
            refresh_error = error_msg
            is_refreshing = False
            return False, error_msg


def get_loading_page():
    """Return a loading page HTML."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ZHA Network Topology - Loading</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            margin: 0;
        }
        .container {
            text-align: center;
            padding: 40px;
        }
        h1 {
            color: #00d4ff;
            margin-bottom: 20px;
        }
        .spinner {
            width: 50px;
            height: 50px;
            border: 4px solid #333;
            border-top: 4px solid #00d4ff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .status {
            color: #888;
            margin-top: 20px;
        }
        .note {
            color: #666;
            font-size: 12px;
            margin-top: 30px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>ZHA Network Topology</h1>
        <div class="spinner"></div>
        <p class="status">Fetching Zigbee network data...</p>
        <p class="note">This may take 1-2 minutes for the initial topology scan.<br>This page will automatically refresh.</p>
    </div>
</body>
</html>'''


def get_error_page(error):
    """Return an error page HTML."""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ZHA Network Topology - Error</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            margin: 0;
        }}
        .container {{
            text-align: center;
            padding: 40px;
            max-width: 600px;
        }}
        h1 {{
            color: #F44336;
            margin-bottom: 20px;
        }}
        .error {{
            background: rgba(244, 67, 54, 0.1);
            border: 1px solid #F44336;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            text-align: left;
            font-family: monospace;
            font-size: 14px;
            white-space: pre-wrap;
            word-break: break-all;
        }}
        button {{
            background: #00d4ff;
            color: #000;
            border: none;
            padding: 12px 24px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            margin-top: 20px;
        }}
        button:hover {{
            background: #00b8e6;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Error Loading Topology</h1>
        <div class="error">{error}</div>
        <button onclick="location.reload()">Retry</button>
    </div>
</body>
</html>'''


class VisualizationHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the visualization server."""

    def log_message(self, format, *args):
        print(f"[Server] {args[0]}")

    def do_GET(self):
        try:
            if self.path == '/' or self.path == '/index.html':
                self.serve_html()
            elif self.path == '/health':
                self.serve_health()
            elif self.path == '/status':
                self.serve_status()
            else:
                self.send_error(404)
        except BrokenPipeError:
            pass  # Client disconnected, ignore
        except ConnectionResetError:
            pass  # Client reset connection, ignore

    def do_POST(self):
        try:
            if self.path == '/refresh':
                self.handle_refresh()
            else:
                self.send_error(404)
        except BrokenPipeError:
            pass
        except ConnectionResetError:
            pass

    def serve_html(self):
        """Serve the visualization HTML."""
        try:
            # If currently refreshing, show loading page
            if is_refreshing:
                content = get_loading_page()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(content.encode('utf-8')))
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
                return

            # If there was a refresh error, show error page
            if refresh_error and not HTML_FILE.exists():
                content = get_error_page(refresh_error)
                self.send_response(500)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(content.encode('utf-8')))
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
                return

            # If no HTML file exists yet, show loading and trigger refresh
            if not HTML_FILE.exists():
                content = get_loading_page()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(content.encode('utf-8')))
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))

                # Trigger background refresh if not already running
                if not is_refreshing:
                    thread = threading.Thread(target=do_refresh, daemon=True)
                    thread.start()
                return

            # Serve the visualization
            with open(HTML_FILE, 'r', encoding='utf-8') as f:
                content = f.read()

            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', len(content.encode('utf-8')))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))

        except BrokenPipeError:
            pass  # Client disconnected
        except Exception as e:
            print(f"Error serving HTML: {e}")
            import traceback
            traceback.print_exc()

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
            'is_refreshing': is_refreshing,
            'last_refresh': last_refresh_time,
            'html_exists': HTML_FILE.exists(),
            'refresh_error': refresh_error,
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
        if is_refreshing:
            self.send_response(202)  # Accepted - already in progress
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Refresh already in progress')
            return

        # Start refresh in background
        thread = threading.Thread(target=do_refresh, daemon=True)
        thread.start()

        self.send_response(202)  # Accepted
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Refresh started')


def auto_refresh_loop(interval_minutes: int):
    """Background thread for auto-refresh."""
    print(f"Auto-refresh enabled: every {interval_minutes} minutes")

    while True:
        time.sleep(interval_minutes * 60)
        if not is_refreshing:
            print("\n" + "=" * 50)
            print(f"Auto-refresh triggered (every {interval_minutes} min)...")
            print("=" * 50)
            do_refresh()


def initial_refresh():
    """Perform initial data refresh on startup."""
    global is_refreshing

    # Check for existing data first
    if HTML_FILE.exists():
        print("Existing visualization found, skipping initial refresh")
        return

    latest = find_latest_export()
    if latest:
        print(f"Found existing export: {latest}")
        print("Generating visualization from existing data...")
        try:
            generate_visualization(latest)
            print("Visualization generated successfully")
            return
        except Exception as e:
            print(f"Warning: Could not generate from existing export: {e}")

    # No existing data, trigger refresh
    print("No existing visualization, starting initial data fetch...")
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

    # Start initial refresh in background thread
    init_thread = threading.Thread(target=initial_refresh, daemon=True)
    init_thread.start()

    # Start auto-refresh thread if configured
    if auto_refresh_minutes > 0:
        thread = threading.Thread(
            target=auto_refresh_loop,
            args=(auto_refresh_minutes,),
            daemon=True
        )
        thread.start()

    # Start HTTP server immediately
    port = 8099
    server = HTTPServer(('0.0.0.0', port), VisualizationHandler)

    print(f"\n{'=' * 50}")
    print(f"Server running on port {port}")
    print(f"Access at: http://<your-ha-host>:{port}")
    print(f"{'=' * 50}\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
