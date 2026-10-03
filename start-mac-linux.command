#!/bin/bash
# Double-click to open the viewer. Serves this folder over HTTP, because
# browsers refuse to load the tileset from a file:// page.
cd "$(dirname "$0")" || exit 1
command -v python3 >/dev/null 2>&1 && exec python3 serve.py
command -v python  >/dev/null 2>&1 && exec python  serve.py
echo "Python not found. Install it, or with Node.js run: npx --yes serve ."
read -r -p "Press enter to close."
