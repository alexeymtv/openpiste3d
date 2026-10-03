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

    # Computed here rather than written by hand: an earlier version quoted a
    # drift measured on one run, and the figure stayed in the README after the
    # experiment grew to three. Rows come out in blocks of one run per cell
    # size, and two different features share the name "Olympia Abfahrt", so the
    # blocks are taken in order rather than grouped by name.
    drifts = []
    for i in range(0, len(rows), len(CELLS)):
        block = rows[i:i + len(CELLS)]
        if len(block) < 2:
            continue
        block.sort(key=lambda r: r[1])
        name = block[0][0]
        m0, p0 = block[0][3], block[0][4]
        m1, p1 = block[-1][3], block[-1][4]
        drifts.append((name, block[0][1], block[-1][1],
                       100 * (m1 - m0) / m0, 100 * (p1 - p0) / p0))

    dm = [abs(d[3]) for d in drifts]
    dp = [abs(d[4]) for d in drifts]
    direction = "always downward" if all(d[3] < 0 and d[4] < 0 for d in drifts) else "in both directions"
    fh.write("\n## Drift from the finest cell to the coarsest\n\n")
    fh.write("| Run | Cells | Mean slope | p90 slope |\n|---|---|---:|---:|\n")
    for name, c0, c1, m, p in drifts:
        fh.write(f"| {name} | {c0} m to {c1} m | {m:+.1f}% | {p:+.1f}% |\n")
    fh.write(f"\nAcross {len(drifts)} runs and an eightfold change in cell size the mean moves "
             f"by at most {max(dm):.1f}% and the 90th percentile by at most {max(dp):.1f}%, "
             f"{direction} as cells coarsen. The mean survives a change of mesh resolution; "
             f"the percentile does not, and is not comparable between datasets unless the cell "
             f"size is quoted with it. That is why the cell is derived from the DEM rather than "
             f"chosen, and why both the value and the rule are written into the build report.\n")

print("\nwrote experiments/cell_size.md")
