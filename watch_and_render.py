#!/usr/bin/env python3
"""
Glove80 Keymap Live Watcher & Viewer Server
- Watches config/glove80.keymap for changes
- Automatically re-renders SVG & HTML layout using keymap-drawer (~1.3s)
- Serves interactive viewer on http://localhost:8080 with live-reload
"""

import http.server
import json
import os
import re
import socket
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
KEYMAP_PATH = REPO_DIR / "config" / "glove80.keymap"
INFO_JSON = REPO_DIR / "config" / "info.json"
YAML_PATH = REPO_DIR / "glove80_layout.yaml"
SVG_PATH = REPO_DIR / "glove80_layout.svg"
HTML_PATH = REPO_DIR / "layout_viewer.html"

# Global list of active SSE clients
sse_clients = []
sse_lock = threading.Lock()

def render_layout():
    """Runs keymap-drawer to parse and draw the layout."""
    t0 = time.time()
    try:
        # 1. Parse .keymap to YAML
        subprocess.run(
            ["keymap", "parse", "-z", str(KEYMAP_PATH), "-o", str(YAML_PATH)],
            check=True,
            capture_output=True,
            text=True
        )

        # 2. Draw YAML to SVG
        subprocess.run(
            ["keymap", "draw", "-j", str(INFO_JSON), str(YAML_PATH), "-o", str(SVG_PATH)],
            check=True,
            capture_output=True,
            text=True
        )

        # 3. Generate HTML viewer
        svg_content = SVG_PATH.read_text(encoding="utf-8")
        layers = re.findall(r'class="layer-([^"\s>]+)"', svg_content)
        seen = set()
        unique_layers = [l for l in layers if not (l in seen or seen.add(l))]

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Glove80 Keymap Viewer (Live)</title>
    <style>
        :root {{
            --bg: #1e1e2e;
            --surface: #252538;
            --accent: #89b4fa;
            --text: #cdd6f4;
            --muted: #6c7086;
            --success: #a6e3a1;
        }}
        body {{
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            display: flex;
            flex-direction: column;
            height: 100vh;
        }}
        header {{
            background: var(--surface);
            padding: 10px 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 12px;
            z-index: 10;
        }}
        h1 {{
            margin: 0;
            font-size: 1.15rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .badge {{
            font-size: 0.75rem;
            background: rgba(137, 180, 250, 0.2);
            color: var(--accent);
            padding: 2px 8px;
            border-radius: 12px;
        }}
        .live-dot {{
            display: inline-block;
            width: 8px;
            height: 8px;
            background: var(--success);
            border-radius: 50%;
            margin-right: 4px;
            box-shadow: 0 0 8px var(--success);
        }}
        .controls {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        select, button {{
            background: var(--bg);
            color: var(--text);
            border: 1px solid var(--muted);
            border-radius: 6px;
            padding: 6px 12px;
            font-size: 0.9rem;
            cursor: pointer;
        }}
        select:focus, button:focus {{
            outline: none;
            border-color: var(--accent);
        }}
        .tabs {{
            display: flex;
            gap: 6px;
            overflow-x: auto;
            padding: 8px 16px;
            background: rgba(0,0,0,0.15);
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .tab {{
            padding: 5px 12px;
            background: transparent;
            border: none;
            border-radius: 4px;
            color: var(--muted);
            cursor: pointer;
            font-size: 0.85rem;
            white-space: nowrap;
            transition: all 0.15s;
        }}
        .tab:hover {{
            background: rgba(255,255,255,0.05);
            color: var(--text);
        }}
        .tab.active {{
            background: var(--accent);
            color: #11111b;
            font-weight: 600;
        }}
        #container {{
            flex: 1;
            overflow: auto;
            display: flex;
            align-items: flex-start;
            justify-content: center;
            padding: 24px;
        }}
        svg.keymap {{
            max-width: 100%;
            height: auto;
            filter: drop-shadow(0 4px 16px rgba(0,0,0,0.2));
        }}
        body.single-layer svg.keymap g[class*="layer-"] {{
            display: none;
        }}
        body.single-layer svg.keymap g.active-layer {{
            display: block;
        }}
        #toast {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: rgba(166, 227, 161, 0.9);
            color: #11111b;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 600;
            opacity: 0;
            transition: opacity 0.3s;
            pointer-events: none;
            z-index: 100;
        }}
    </style>
</head>
<body class="single-layer">
    <header>
        <h1>
            <span>Glove80 Layout</span>
            <span class="badge"><span class="live-dot"></span>Live Watcher</span>
            <span class="badge">{len(unique_layers)} Layers</span>
        </h1>
        <div class="controls">
            <label for="layerSelect" style="font-size: 0.85rem; color: var(--muted);">Layer:</label>
            <select id="layerSelect" onchange="selectLayer(this.value)">
                {''.join(f'<option value="{l}">{l}</option>' for l in unique_layers)}
            </select>
            <button onclick="toggleAllLayers()" id="toggleBtn">Show All Layers</button>
        </div>
    </header>

    <div class="tabs" id="tabsBar">
        {''.join(f'<button class="tab" onclick="selectLayer(\'{l}\')">{l}</button>' for l in unique_layers)}
    </div>

    <div id="container">
        {svg_content}
    </div>

    <div id="toast">Layout Updated!</div>

    <script>
        const layers = {unique_layers};
        let currentLayer = localStorage.getItem('glove80_selected_layer') || layers[0];
        if (!layers.includes(currentLayer)) currentLayer = layers[0];
        let showAll = localStorage.getItem('glove80_show_all') === 'true';

        function showToast(msg) {{
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.style.opacity = '1';
            setTimeout(() => toast.style.opacity = '0', 1500);
        }}

        function updateView() {{
            const svg = document.querySelector('svg.keymap');
            if (!svg) return;
            const gLayers = svg.querySelectorAll('g[class*="layer-"]');
            const toggleBtn = document.getElementById('toggleBtn');
            const select = document.getElementById('layerSelect');
            const tabs = document.querySelectorAll('.tab');

            select.value = currentLayer;
            tabs.forEach(tab => {{
                tab.classList.toggle('active', tab.textContent === currentLayer && !showAll);
            }});

            if (showAll) {{
                document.body.classList.remove('single-layer');
                toggleBtn.textContent = "Show Single Layer";
                svg.setAttribute('viewBox', '0 0 1068 16452');
                svg.setAttribute('height', '16452');
            }} else {{
                document.body.classList.add('single-layer');
                toggleBtn.textContent = "Show All Layers";
                gLayers.forEach(g => {{
                    if (g.classList.contains('layer-' + currentLayer)) {{
                        g.classList.add('active-layer');
                        const transform = g.getAttribute('transform');
                        const match = transform ? transform.match(/translate\\((\\d+),\\s*(\\d+)\\)/) : null;
                        const yOffset = match ? parseInt(match[2]) : 0;
                        svg.setAttribute('viewBox', `0 ${{yOffset}} 1068 512`);
                        svg.setAttribute('height', '512');
                    }} else {{
                        g.classList.remove('active-layer');
                    }}
                }});
            }}
        }}

        function selectLayer(name) {{
            showAll = false;
            currentLayer = name;
            localStorage.setItem('glove80_selected_layer', name);
            localStorage.setItem('glove80_show_all', 'false');
            updateView();
        }}

        function toggleAllLayers() {{
            showAll = !showAll;
            localStorage.setItem('glove80_show_all', showAll ? 'true' : 'false');
            updateView();
        }}

        // Keyboard navigation (Arrow keys left/right to change layer)
        window.addEventListener('keydown', (e) => {{
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
            let idx = layers.indexOf(currentLayer);
            if (e.key === 'ArrowRight') {{
                selectLayer(layers[(idx + 1) % layers.length]);
            }} else if (e.key === 'ArrowLeft') {{
                selectLayer(layers[(idx - 1 + layers.length) % layers.length]);
            }}
        }});

        // SSE Live Reload Connection
        if (window.location.protocol.startsWith('http')) {{
            const es = new EventSource('/events');
            es.onmessage = (event) => {{
                if (event.data === 'reload') {{
                    fetch('/glove80_layout.svg?t=' + Date.now())
                        .then(r => r.text())
                        .then(newSvg => {{
                            document.getElementById('container').innerHTML = newSvg;
                            updateView();
                            showToast('Layout Updated!');
                        }})
                        .catch(() => location.reload());
                }}
            }};
        }}

        // Initial render
        updateView();
    </script>
</body>
</html>
"""
        HTML_PATH.write_text(html, encoding="utf-8")
        dt = time.time() - t0
        print(f"[✓] Re-rendered in {dt:.2f}s at {time.strftime('%H:%M:%S')}")

        # Notify SSE clients
        notify_reload()
        return True
    except subprocess.CalledProcessError as e:
        print(f"[!] Build error:\n{e.stderr or e.stdout}")
        return False
    except Exception as e:
        print(f"[!] Unexpected error during render: {e}")
        return False

def notify_reload():
    """Broadcasts a reload signal to all connected browser SSE clients."""
    with sse_lock:
        to_remove = []
        for client in sse_clients:
            try:
                client.wfile.write(b"data: reload\n\n")
                client.wfile.flush()
            except Exception:
                to_remove.append(client)
        for dead in to_remove:
            if dead in sse_clients:
                sse_clients.remove(dead)

class LiveHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(REPO_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if HTML_PATH.exists():
                self.wfile.write(HTML_PATH.read_bytes())
            return
        elif self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with sse_lock:
                sse_clients.append(self)
            try:
                # Keep alive until disconnect
                while True:
                    time.sleep(15)
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                with sse_lock:
                    if self in sse_clients:
                        sse_clients.remove(self)
            return
        else:
            return super().do_GET()

    def log_message(self, format, *args):
        # Suppress noisy HTTP request logging
        pass

def run_server(port=8080):
    socketserver.TCPServer.allow_reuse_address = True
    for p in range(port, port + 10):
        try:
            httpd = socketserver.TCPServer(("127.0.0.1", p), LiveHandler)
            print(f"[*] Live viewer running at: http://localhost:{p}")
            httpd.serve_forever()
            break
        except OSError:
            continue

def watch_keymap():
    """Watches config/glove80.keymap using inotifywait or polling."""
    # First initial render
    render_layout()

    # Try inotifywait first for instant reaction
    has_inotify = subprocess.run(["which", "inotifywait"], capture_output=True).returncode == 0
    if has_inotify:
        print("[*] Watching config/glove80.keymap via inotifywait...")
        watch_dir = KEYMAP_PATH.parent
        proc = subprocess.Popen(
            ["inotifywait", "-mr", "-e", "close_write,moved_to", str(watch_dir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            if "glove80.keymap" in line:
                time.sleep(0.2)  # Brief debounce
                render_layout()
    else:
        print("[*] Watching config/glove80.keymap via polling...")
        last_mtime = KEYMAP_PATH.stat().st_mtime if KEYMAP_PATH.exists() else 0
        while True:
            time.sleep(0.5)
            if KEYMAP_PATH.exists():
                mtime = KEYMAP_PATH.stat().st_mtime
                if mtime > last_mtime:
                    last_mtime = mtime
                    render_layout()

def main():
    # Start server in background thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Run watcher on main thread
    try:
        watch_keymap()
    except KeyboardInterrupt:
        print("\nStopping watcher...")

if __name__ == "__main__":
    main()
