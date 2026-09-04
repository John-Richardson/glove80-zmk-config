#!/usr/bin/env python3
import subprocess
import sys
import re
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
KEYMAP_PATH = REPO_DIR / "config" / "glove80.keymap"
INFO_JSON = REPO_DIR / "config" / "info.json"
YAML_PATH = REPO_DIR / "glove80_layout.yaml"
SVG_PATH = REPO_DIR / "glove80_layout.svg"
HTML_PATH = REPO_DIR / "layout_viewer.html"

def main():
    print(f"[*] Parsing {KEYMAP_PATH}...")
    subprocess.run(
        [
            "keymap", "parse",
            "-z", str(KEYMAP_PATH),
            "-o", str(YAML_PATH)
        ],
        check=True
    )
    print(f"[+] Saved YAML to {YAML_PATH.name}")

    print(f"[*] Drawing SVG layout with {INFO_JSON}...")
    subprocess.run(
        [
            "keymap", "draw",
            "-j", str(INFO_JSON),
            str(YAML_PATH),
            "-o", str(SVG_PATH)
        ],
        check=True
    )
    print(f"[+] Saved full SVG to {SVG_PATH.name}")

    # Generate an interactive HTML viewer with layer switching
    print(f"[*] Generating interactive HTML viewer...")
    svg_content = SVG_PATH.read_text(encoding="utf-8")
    
    # Extract layer names from class="layer-<name>"
    layers = re.findall(r'class="layer-([^"\s>]+)"', svg_content)
    # Deduplicate preserving order
    seen = set()
    unique_layers = []
    for l in layers:
        if l not in seen:
            seen.add(l)
            unique_layers.append(l)

    # Wrap in interactive viewer
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Glove80 Keymap Viewer</title>
    <style>
        :root {{
            --bg: #1e1e2e;
            --surface: #252538;
            --accent: #89b4fa;
            --text: #cdd6f4;
            --muted: #6c7086;
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
            padding: 12px 20px;
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
        /* Hide all layers by default in single-layer view */
        body.single-layer svg.keymap g[class*="layer-"] {{
            display: none;
        }}
        body.single-layer svg.keymap g.active-layer {{
            display: block;
        }}
    </style>
</head>
<body class="single-layer">
    <header>
        <h1>Glove80 Layout <span class="badge">{len(unique_layers)} Layers</span></h1>
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

    <script>
        const layers = {unique_layers};
        let currentLayer = layers[0];
        let showAll = false;

        function updateView() {{
            const svg = document.querySelector('svg.keymap');
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
            updateView();
        }}

        function toggleAllLayers() {{
            showAll = !showAll;
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

        // Initialize first layer
        selectLayer(layers[0]);
    </script>
</body>
</html>
"""
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"[+] Saved interactive viewer to {HTML_PATH.name}")
    print(f"\nDone! You can open {HTML_PATH} directly in your browser or VS Code.")

if __name__ == "__main__":
    main()
