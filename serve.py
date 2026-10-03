#!/usr/bin/env python3
"""Serve the repository so the viewer can fetch the tilesets.

    python3 serve.py            # then open http://localhost:8000/viewer/

Opening viewer/index.html straight from disk does not work: browsers block
file:// requests for the tileset JSON.
"""
import http.server, os, socketserver, sys, webbrowser

if sys.version_info[0] < 3:
    sys.stderr.write("This needs Python 3. On Windows try:  py serve.py\n")
    sys.exit(1)

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".glb": "model/gltf-binary", ".json": "application/json"}
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
    def log_message(self, fmt, *args):
        if "404" in (fmt % args):
            sys.stderr.write("  404 " + (fmt % args) + "\n")

socketserver.TCPServer.allow_reuse_address = True

for attempt in range(10):
    try:
        httpd = socketserver.TCPServer(("", PORT), Handler)
        break
    except OSError:
        print(f"  port {PORT} busy, trying {PORT + 1}")
        PORT += 1
else:
    sys.exit("no free port found")

with httpd:
    url = f"http://localhost:{PORT}/viewer/"
    print(f"serving {os.getcwd()}\n  open {url}\n  ctrl-c to stop")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    httpd.serve_forever()
