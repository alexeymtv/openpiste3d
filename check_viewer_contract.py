"""The viewer and the tileset must agree on property names.

A viewer asking for a property the schema no longer has fails silently: the panel
shows NaN and nothing in the build complains. That happened once in this project –
`maxSlope` was removed from the profile and the click panel kept requesting it –
so the agreement is now checked mechanically instead of by eye.

Two things are checked.

Every `getProperty("x")` call and every `${x}` used in a Cesium3DTileStyle in
viewer/index.html must name a property that exists in the published schema.

Every file the viewer fetches out of `out/` must be a file the pipeline writes.
That one is here for the same reason: a page that fetches a file nobody generates
looks fine to its author, whose `out/` still holds it from an earlier run, and
breaks for everyone who clones the repository and builds.

    python check_viewer_contract.py [out/pistes.glb] [viewer/index.html]
"""
import json
import os
import re
import struct
import sys

GLB = sys.argv[1] if len(sys.argv) > 1 else "out/pistes.glb"
VIEWER = sys.argv[2] if len(sys.argv) > 2 else "viewer/index.html"
OUT_DIR = os.path.dirname(GLB) or "."

with open(GLB, "rb") as fh:
    data = fh.read()
magic, ver, length = struct.unpack("<III", data[:12])
assert magic == 0x46546C67 and ver == 2, "not glTF 2.0 binary"
off, gltf = 12, None
while off < len(data):
    clen, ctype = struct.unpack("<II", data[off:off + 8])
    off += 8
    if ctype == 0x4E4F534A:
        gltf = json.loads(data[off:off + clen])
    off += clen

sm = gltf["extensions"]["EXT_structural_metadata"]
cls = list(sm["schema"]["classes"])[0]
published = set(sm["schema"]["classes"][cls]["properties"])
in_table = set(sm["propertyTables"][0]["properties"])
assert published == in_table, f"schema and property table disagree: {published ^ in_table}"

src = open(VIEWER, encoding="utf-8").read()
requested = set(re.findall(r'getProperty\("([A-Za-z0-9_]+)"\)', src))
requested |= set(re.findall(r'\bg\("([A-Za-z0-9_]+)"\)', src))
# ${prop} inside a tile style, written as \${prop} in a JS template literal
styled = set(re.findall(r'\\\$\{([A-Za-z0-9_]+)\}', src))

print(f"published in tileset : {len(published)}  {sorted(published)}")
print(f"read by the viewer   : {len(requested)}  {sorted(requested)}")
print(f"used in tile styles  : {len(styled)}  {sorted(styled)}")

fetched = sorted(set(re.findall(r'["\']\.\./out/([A-Za-z0-9_.\-]+)["\']', src)))
absent = [f for f in fetched if not os.path.exists(os.path.join(OUT_DIR, f))]
print(f"fetched from out/    : {len(fetched)}  {fetched}")

failed = False
missing = (requested | styled) - published
if missing:
    print(f"\nFAIL – the viewer asks for properties the tileset does not publish: {sorted(missing)}")
    failed = True
if absent:
    print(f"\nFAIL – the viewer fetches files the pipeline did not write: {absent}")
    failed = True
if failed:
    sys.exit(1)

unused = published - (requested | styled)
if unused:
    print(f"\nnote: published but not shown in the viewer: {sorted(unused)}")
print("\nOK – viewer and build agree on both property names and output files")
