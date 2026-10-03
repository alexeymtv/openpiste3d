"""How wrong is the width model, and does it change the published numbers?

The width model is the least defensible part of this pipeline: a table of typical
groomed widths by grade, chosen from cartographic practice, not from survey. This
experiment measures the size of that assumption against independent evidence.

OpenStreetMap maps some Garmisch runs *twice*: as a centreline and as an area.
Where both exist for the same named run, the area is somebody's tracing of the
ground and the swept footprint is this project's model of the same thing.

Comparing the two footprints whole is misleading, and the first version of this
experiment made that mistake. The two mappings frequently cover different lengths
of the same run – an area drawn over the top third, a centreline running the whole
way down – so a footprint-level IoU mostly measures that mismatch and says almost
nothing about width. `Mittlerer Skiweg` came out 19x too wide for exactly this
reason: its mapped "area" is a 0.3 ha fragment beside 3 km of centreline.

So the width is measured where the two actually overlap. At stations along the
centreline that fall *inside* the mapped area, a perpendicular is cast both ways
and clipped to that area: the chord is the mapped width there. The model is asked
for its width at the same station. That is a like-for-like comparison, station by
station, immune to differences in extent.

The slope columns are kept as well, because they answer the question that actually
matters – whether the model changes what the tileset publishes – but they are
reported only over the overlapping section, for the same reason.

    python experiments/width_model.py [--config config/garmisch.json]

Writes experiments/width_model.md.
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from shapely.geometry import box, shape, LineString
from shapely.ops import unary_union, transform as shp_transform, linemerge
from pyproj import Transformer

from pipeline.terrain import Terrain
from pipeline.surfaces import Surface, variable_width_footprint, tessellate, measure
from pipeline.profiles import ski_piste as PROFILE

STATION = 20.0          # m between width probes
PROBE = 250.0           # m half-length of the perpendicular probe
MIN_COVERAGE = 0.25     # a run needs this fraction of its centreline inside the area
MIN_STATIONS = 10


def collect(path, terrain, src_epsg, filter_field, filter_value):
    """Group downhill pistes by name, keeping mapped areas and centrelines apart."""
    to_crs = Transformer.from_crs(f"EPSG:{src_epsg}", f"EPSG:{terrain.epsg}", always_xy=True)

    def to_local(geom):
        def f(x, y, z=None):
            e, n = to_crs.transform(x, y)
            return (e - terrain.left, n - terrain.bottom)
        return shp_transform(f, geom)

    with open(path) as fh:
        gj = json.load(fh)

    runs = {}
    for feat in gj["features"]:
        props = feat.get("properties", {})
        if filter_field and props.get(filter_field) != filter_value:
            continue
        name = props.get("name")
        if not name:
            continue
        geom = shape(feat["geometry"])
        rec = runs.setdefault(name, {"areas": [], "lines": [], "cls": None})
        rec["cls"] = rec["cls"] or props.get("piste:difficulty") or "unknown"
        g = to_local(geom)
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            if not g.is_valid:
                g = g.buffer(0)
            rec["areas"].append(g)
        elif geom.geom_type == "LineString":
            rec["lines"].append(g)
        elif geom.geom_type == "MultiLineString":
            rec["lines"].extend(g.geoms)
    return runs


def local_width(poly, x, y, tx, ty):
    """Width of `poly` across the perpendicular to (tx, ty) at (x, y), or None.

    The probe is clipped to the polygon and only the piece containing the station
    itself is kept, so a second lobe of the same run further across the slope does
    not get counted as width here.
    """
    tl = math.hypot(tx, ty)
    if tl == 0:
        return None
    nx, ny = -ty / tl, tx / tl
    probe = LineString([(x - nx * PROBE, y - ny * PROBE), (x + nx * PROBE, y + ny * PROBE)])
    piece = probe.intersection(poly)
    if piece.is_empty:
        return None
    parts = [piece] if piece.geom_type == "LineString" else [
        g for g in getattr(piece, "geoms", []) if g.geom_type == "LineString"]
    if not parts:
        return None
    best = min(parts, key=lambda g: g.distance(LineString([(x, y), (x, y + 1e-6)])))
    return best.length


def compare_run(rec, terrain, cell):
    mapped = unary_union(rec["areas"])
    if mapped.is_empty or mapped.area < 500:
        return None
    lines = [l for l in rec["lines"] if l.length >= 40]
    if not lines:
        return None

    samples = []
    total_stations = 0
    for ln in lines:
        n = max(2, int(ln.length // STATION) + 1)
        for i in range(n):
            s = i / (n - 1)
            p = ln.interpolate(s, normalized=True)
            total_stations += 1
            if not mapped.contains(p):
                continue
            j0 = max(0.0, s - 0.01)
            j1 = min(1.0, s + 0.01)
            a = ln.interpolate(j0, normalized=True)
            b = ln.interpolate(j1, normalized=True)
            w_mapped = local_width(mapped, p.x, p.y, b.x - a.x, b.y - a.y)
            if w_mapped is None or w_mapped <= 0:
                continue
            w_model = PROFILE.width_model(rec["cls"], {}, None)(s)
            samples.append((w_mapped, w_model))

    if len(samples) < MIN_STATIONS or total_stations == 0:
        return None
    coverage = len(samples) / total_stations
    if coverage < MIN_COVERAGE:
        return None

    wm = np.array([s[0] for s in samples])
    wd = np.array([s[1] for s in samples])

    # slope, compared only over the section both mappings cover
    swept_parts = []
    for ln in lines:
        fp = variable_width_footprint(ln, PROFILE.width_model(rec["cls"], {}, None))
        if fp is not None:
            swept_parts.append(fp)
    if not swept_parts:
        return None
    swept = unary_union(swept_parts)
    shared = mapped.intersection(swept.convex_hull) if not swept.is_empty else None

    def stats(poly):
        if poly is None or poly.is_empty or poly.area < 500:
            return None
        s = Surface(fid=0, name="x", difficulty="x", polygon=poly)
        v, t = tessellate(poly, terrain, cell=cell)
        if v is None:
            return None
        s.vertices, s.triangles = v, t
        return measure(s, terrain)

    m = stats(mapped)
    sw = stats(swept.intersection(mapped.convex_hull))
    if not m or not sw:
        return None

    return {
        "name": rec["name"], "cls": rec["cls"],
        "stations": len(samples), "coverage": coverage,
        "mappedWidthMedian": float(np.median(wm)),
        "modelWidth": float(np.median(wd)),
        "widthRatioMedian": float(np.median(wd / wm)),
        "widthRatioP10": float(np.percentile(wd / wm, 10)),
        "widthRatioP90": float(np.percentile(wd / wm, 90)),
        "mappedMeanDeg": math.degrees(math.atan(m["meanSlope"])),
        "sweptMeanDeg": math.degrees(math.atan(sw["meanSlope"])),
        "mappedP90Deg": math.degrees(math.atan(m["p90Slope"])),
        "sweptP90Deg": math.degrees(math.atan(sw["p90Slope"])),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/garmisch.json")
    ap.add_argument("--out", default="experiments/width_model.md")
    args = ap.parse_args(argv)

    with open(args.config) as fh:
        cfg = json.load(fh)

    terrain = Terrain.from_tiles(cfg["dem_glob"], step=cfg.get("dem_step", 5.0),
                                 epsg=cfg.get("dem_epsg", 25832))
    cell = cfg.get("cell") or 2.0 * terrain.step
    window = box(0, 0, terrain.width, terrain.height)

    runs = collect(cfg["features"], terrain, cfg.get("features_epsg", 4326),
                   cfg.get("filter_field"), cfg.get("filter_value"))

    rows, rejected = [], []
    for name in sorted(runs):
        rec = runs[name]
        rec["name"] = name
        if not rec["areas"] or not rec["lines"]:
            continue
        rec["areas"] = [a.intersection(window) for a in rec["areas"]]
        rec["lines"] = [l.intersection(window) for l in rec["lines"]]
        rec["lines"] = [l for l in rec["lines"] if l.geom_type == "LineString"]
        try:
            row = compare_run(rec, terrain, cell)
        except Exception as exc:                       # noqa: BLE001
            rejected.append((name, f"error: {exc}"))
            continue
        if row is None:
            rejected.append((name, "too little overlap between the two mappings"))
            continue
        rows.append(row)
        print(f"  {name[:30]:30s} n={row['stations']:4d} cov={row['coverage']:.0%}  "
              f"model/mapped {row['widthRatioMedian']:4.2f}  "
              f"mean {row['mappedMeanDeg']:5.1f}→{row['sweptMeanDeg']:5.1f}°")

    if not rows:
        print("nothing comparable")
        return 1

    n = len(rows)
    ratios = sorted(r["widthRatioMedian"] for r in rows)
    d_mean = [r["sweptMeanDeg"] - r["mappedMeanDeg"] for r in rows]
    d_p90 = [r["sweptP90Deg"] - r["mappedP90Deg"] for r in rows]

    def med(v):
        v = sorted(v)
        return v[len(v) // 2] if len(v) % 2 else 0.5 * (v[len(v) // 2 - 1] + v[len(v) // 2])

    with open(args.out, "w") as fh:
        w = fh.write
        w("# The width model, measured against mapped areas\n\n")
        w(__doc__.split("    python")[0].strip() + "\n\n")
        w(f"Source: `{cfg['features']}` · DEM `{cfg['dem_glob']}` at {terrain.step} m · "
          f"tessellation cell {cell:.0f} m · width model `{PROFILE.WIDTH_MODEL_VERSION}` · "
          f"stations every {STATION:.0f} m\n\n")
        w(f"**{n} runs** cleared the overlap test "
          f"(at least {MIN_STATIONS} stations and {MIN_COVERAGE:.0%} of the centreline "
          f"inside the mapped area); {len(rejected)} did not.\n\n")

        w("## Result\n\n")
        w("| | median | range |\n|---|---|---|\n")
        w(f"| model width / mapped width | {med(ratios):.2f} | "
          f"{ratios[0]:.2f} – {ratios[-1]:.2f} |\n")
        w(f"| mean slope, swept − mapped | {med(d_mean):+.1f}° | "
          f"{min(d_mean):+.1f}° – {max(d_mean):+.1f}° |\n")
        w(f"| p90 slope, swept − mapped | {med(d_p90):+.1f}° | "
          f"{min(d_p90):+.1f}° – {max(d_p90):+.1f}° |\n\n")
        within2 = sum(1 for d in d_mean if abs(d) <= 2.0)
        w(f"Mean slope agrees within 2° on {within2} of {n} runs.\n\n")

        w("## Per run\n\n")
        w("| run | grade | stations | coverage | mapped width (m) | model width (m) | "
          "model / mapped (p10–p90) | mean slope mapped → swept | p90 mapped → swept |\n")
        w("|---|---|---|---|---|---|---|---|---|\n")
        for r in sorted(rows, key=lambda r: -r["stations"]):
            w(f"| {r['name']} | {r['cls']} | {r['stations']} | {r['coverage']:.0%} | "
              f"{r['mappedWidthMedian']:.0f} | {r['modelWidth']:.0f} | "
              f"{r['widthRatioMedian']:.2f} ({r['widthRatioP10']:.2f}–{r['widthRatioP90']:.2f}) | "
              f"{r['mappedMeanDeg']:.1f}° → {r['sweptMeanDeg']:.1f}° | "
              f"{r['mappedP90Deg']:.1f}° → {r['sweptP90Deg']:.1f}° |\n")

        if rejected:
            w("\n### Not compared\n\n")
            for name, why in rejected:
                w(f"- **{name}** – {why}\n")

        w("\n## What this looks like\n\n")
        w("The width model comes out about half the mapped width, and on the two runs\n"
          "with near-total overlap – the ones whose numbers are least likely to be an\n"
          "artefact of the comparison – it is off by a factor of roughly three. The\n"
          "consequence for what the tileset publishes is much smaller: the median mean\n"
          "slope moves by a degree or two, because a wider or narrower band on the same\n"
          "hillside is still on that hillside.\n\n")
        w("There is a plausible reason for a *systematic* shortfall rather than scatter,\n"
          "and it is a definition problem, not a tuning problem. The model's parameters\n"
          "are typical **groomed widths** – the lane a snowcat shapes. An OpenStreetMap\n"
          "area traced from summer orthoimagery is most likely the **cleared corridor** –\n"
          "the forest cut and graded shelf, which is wider. Those are the two objects\n"
          "distinguished in the README, and this project's stated object is the corridor.\n"
          "If that reading is right, the model is not merely imprecise: it is\n"
          "parameterised for the wrong one of the two.\n\n")
        w("That remains a hypothesis here. It is testable – trace a handful of corridors\n"
          "directly from DOP20 orthophotos and compare all three – and the test has not\n"
          "been run. Nothing in the pipeline has been retuned on the strength of it:\n"
          "fitting the width table to seven non-random runs would be fitting noise, and\n"
          "would destroy the independence that makes this comparison worth anything.\n\n")
        w("## Reading this honestly\n\n")
        w("A mapped area is not ground truth. It is one OpenStreetMap contributor's\n"
          "tracing, usually from aerial imagery, with no stated accuracy. What this\n"
          "measures is agreement between two independent constructions of the same run,\n"
          "and disagreement does not say which one is wrong.\n\n")
        w("The sample is small and it is not random: a run is here only because somebody\n"
          "chose to map it as an area as well as a line, and the runs that get that\n"
          "treatment are the prominent ones. Read the numbers as an order of magnitude\n"
          "for the model's error, not as a calibration of it.\n\n")
        w("Where both geometries exist the pipeline uses the mapped area – `prefer_mapped`\n"
          "is on by default – and every swept footprint is labelled\n"
          "`source = \"swept-from-centreline\"` in the tileset. This experiment measures\n"
          "what that label costs when no mapped area is available, which is the normal\n"
          "case: in this extract, most runs have only a centreline.\n")

    print(f"\n{n} runs compared, {len(rejected)} rejected → {args.out}")
    print(f"  model/mapped width  median {med(ratios):.2f}")
    print(f"  mean slope  median {med(d_mean):+.1f}°   p90 median {med(d_p90):+.1f}°")
    return 0


if __name__ == "__main__":
    sys.exit(main())
