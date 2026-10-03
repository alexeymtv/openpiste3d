"""How much does the tessellation cell size change the measured slope?

The cell size is a free parameter. If the statistics move with it, they are an
artefact of the mesh; if they settle, the mesh is fine enough. Run this, look at
where the numbers stop moving, and pick the largest cell that still sits on the
plateau.

    python experiments/cell_size.py            # writes experiments/cell_size.md
"""
import json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.terrain import Terrain
from pipeline.surfaces import load_features, tessellate, measure
from pipeline.profiles import ski_piste as profile

CELLS = [5, 10, 20, 40]
SAMPLE = ["Kandahar-Abfahrt", "Osterfelder-Abfahrt", "Olympia Abfahrt"]

cfg = json.load(open(os.path.join(os.path.dirname(__file__), "..", "config", "garmisch.json")))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

terrain = Terrain.from_tiles(cfg["dem_glob"], step=cfg.get("dem_step", 5.0))
surfaces, _ = load_features(cfg["features"], terrain,
                            filter_field=cfg.get("filter_field"),
                            filter_value=cfg.get("filter_value"),
                            width_model=profile.width_model)
picked = [s for s in surfaces if s.name in SAMPLE]

rows = []
for s in picked:
    for cell in CELLS:
        v, t = tessellate(s.polygon, terrain, cell=cell)
        if v is None:
            continue
        s.vertices, s.triangles = v, t
        m = measure(s, terrain)
        rows.append((s.name, cell, len(t), m["meanSlopeDeg"], m["p90SlopeDeg"]))
        print(f"{s.name[:28]:28s} cell {cell:3d} m  {len(t):6d} tri  "
              f"mean {m['meanSlopeDeg']:5.2f}°  p90 {m['p90SlopeDeg']:5.2f}°")

with open("experiments/cell_size.md", "w") as fh:
    fh.write("# Tessellation cell size – sensitivity\n\n")
    fh.write("Slope statistics for three runs at four cell sizes. "
             "The question is not which value is *right* but where the numbers stop moving.\n\n")
    fh.write("| Run | Cell | Triangles | Mean slope | p90 slope |\n|---|---:|---:|---:|---:|\n")
    for name, cell, tri, mean, p90 in rows:
        fh.write(f"| {name} | {cell} m | {tri} | {mean:.2f}° | {p90:.2f}° |\n")
print("\nwrote experiments/cell_size.md")
