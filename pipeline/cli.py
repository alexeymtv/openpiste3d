"""Build a 3D Tiles 1.1 tileset from a DEM and a polygon feature layer.

    python -m pipeline.cli --config config/garmisch.json

Terrain-derived measurements are deterministic: the same inputs, DEM and
processing configuration give the same numbers. Footprints swept from centrelines
additionally use an explicit width model whose parameters are part of the profile
and are recorded in the build report.
"""
import argparse
import hashlib
import json
import os
import sys
import time

from pyproj import Transformer

from .terrain import Terrain
from .surfaces import load_features, tessellate, measure, clearance_above_terrain_mesh
from . import tiles3d
from . import overlays

from .profiles import ski_piste as PROFILE

PROFILE_BY_NAME = {"ski_piste": PROFILE}


def build(cfg: dict, out_dir: str):
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)

    print("· loading DEM")
    terrain = Terrain.from_tiles(cfg["dem_glob"], step=cfg.get("dem_step", 5.0),
                                 epsg=cfg.get("dem_epsg", 25832))
    print(f"  {terrain.grid.shape[1]}x{terrain.grid.shape[0]} posts at {terrain.step} m")

    print("· loading features")
    profile = PROFILE_BY_NAME[cfg.get("profile", "ski_piste")]
    surfaces, geom_stats = load_features(
        cfg["features"], terrain,
        src_epsg=cfg.get("features_epsg", 4326),
        name_field=cfg.get("name_field", "name"),
        class_field=cfg.get("class_field", "piste:difficulty"),
        filter_field=cfg.get("filter_field"),
        filter_value=cfg.get("filter_value"),
        width_model=(profile.width_model if cfg.get("sweep_lines", True) else None),
        width_field=cfg.get("width_field", "width"),
        prefer_mapped=cfg.get("prefer_mapped", True))
    print(f"  from mapped areas: {geom_stats['polygon']} · "
          f"swept from centrelines: {geom_stats['line']} · skipped: {geom_stats['skipped']}")
    if cfg.get("only"):
        surfaces = [s for s in surfaces if s.name in cfg["only"]]
    for i, s in enumerate(surfaces):
        s.fid = i
    print(f"  {len(surfaces)} features after grouping")

    # crop the terrain to the features, so the tileset carries no dead ground
    minx = min(s.polygon.bounds[0] for s in surfaces)
    miny = min(s.polygon.bounds[1] for s in surfaces)
    maxx = max(s.polygon.bounds[2] for s in surfaces)
    maxy = max(s.polygon.bounds[3] for s in surfaces)
    shift_x, shift_y = terrain.left, terrain.bottom
    terrain = terrain.crop(minx + shift_x, miny + shift_y, maxx + shift_x, maxy + shift_y,
                           margin=cfg.get("margin", 250.0))
    dx, dy = terrain.left - shift_x, terrain.bottom - shift_y
    from shapely.affinity import translate
    for s in surfaces:
        s.polygon = translate(s.polygon, xoff=-dx, yoff=-dy)

    # The tessellation cell is tied to the DEM, not chosen: two DEM posts per
    # cell. See experiments/cell_size.md – the mean is insensitive to this, the
    # 90th percentile is not, so the value is derived and then reported.
    cell = cfg.get("cell") or 2.0 * terrain.step
    print(f"· draping surfaces on terrain (cell {cell:.0f} m = 2 x DEM step)")
    kept = []
    for s in surfaces:
        v, t = tessellate(s.polygon, terrain, cell=cell)
        if v is None:
            continue
        s.vertices, s.triangles = v, t
        s.metrics = measure(s, terrain)
        kept.append(s)
        print(f"  {s.name[:32]:32s} {len(t):6d} tri  "
              f"mean {s.metrics['meanSlopeDeg']:4.1f}°  p90 {s.metrics['p90SlopeDeg']:4.1f}°")
    surfaces = kept
    for i, s in enumerate(surfaces):
        s.fid = i

    # Presentation only, after every measurement is taken: raise each vertex so
    # the coarser terrain tile cannot poke through the surface.
    terrain_step = cfg.get("terrain_step", 15.0)
    clearance = cfg.get("display_clearance", 0.4)
    for s in surfaces:
        s.display_z = clearance_above_terrain_mesh(s.vertices, terrain, terrain_step, clearance)

    to_wgs = Transformer.from_crs(f"EPSG:{terrain.epsg}", "EPSG:4326", always_xy=True)
    cx, cy = terrain.left + terrain.width / 2, terrain.bottom + terrain.height / 2
    lon0, lat0 = to_wgs.transform(cx, cy)
    h0 = terrain.height_at(terrain.width / 2, terrain.height / 2)
    origin = (lon0, lat0, h0)

    w, s_ = to_wgs.transform(terrain.left, terrain.bottom)
    e, n = to_wgs.transform(terrain.left + terrain.width, terrain.bottom + terrain.height)
    zmin = float(terrain.grid.min()) - 20
    zmax = float(terrain.grid.max()) + 20
    region = (w, s_, e, n, zmin, zmax)

    print("· writing 3D Tiles")
    props = {k: [] for k in profile.PROPERTIES}
    for s in surfaces:
        for k in profile.PROPERTIES:
            if k in profile.STRING_PROPERTIES:
                props[k].append(getattr(s, {"name": "name", "difficulty": "difficulty",
                                            "source": "source"}[k], "") or "")
            else:
                props[k].append(float(s.metrics.get(k, 0.0)))

    stats_p = tiles3d.write_feature_glb(
        os.path.join(out_dir, "pistes.glb"), surfaces, origin, profile.SCHEMA, props,
        terrain.epsg, terrain.left, terrain.bottom, class_name=profile.CLASS_NAME,
        string_properties=profile.STRING_PROPERTIES)
    tiles3d.write_tileset(os.path.join(out_dir, "pistes.json"), "pistes.glb", origin, region,
                          geometric_error=cfg.get("geometric_error", 180.0))

    stats_t = tiles3d.write_terrain_glb(
        os.path.join(out_dir, "terrain.glb"), terrain, origin, step=terrain_step)
    tiles3d.write_tileset(os.path.join(out_dir, "terrain.json"), "terrain.glb", origin, region,
                          geometric_error=cfg.get("geometric_error", 512.0))

    print("· writing reference overlays")
    stats_l = overlays.write_source_lines(
        os.path.join(out_dir, "source-lines.json"), cfg["features"], terrain,
        src_epsg=cfg.get("features_epsg", 4326),
        class_field=cfg.get("class_field", "piste:difficulty"),
        filter_field=cfg.get("filter_field"), filter_value=cfg.get("filter_value"))
    stats_c = overlays.write_contours(
        os.path.join(out_dir, "contours.json"), terrain,
        interval=cfg.get("contour_interval", 100.0))
    print(f"  {stats_l['lines']} source lines · {stats_c['contours']} contour lines "
          f"at {stats_c['intervalM']:.0f} m")

    report = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "origin": {"lon": lon0, "lat": lat0, "height": h0},
        "profile": cfg.get("profile", "ski_piste"),
        "featureCount": len(surfaces),
        "footprintSource": geom_stats,
        "pistes": stats_p,
        "terrain": stats_t,
        "overlays": {"sourceLines": stats_l, "contours": stats_c},
        "features": [
            {"id": s.fid, "name": s.name, "difficulty": s.difficulty,
             **{k: round(v, 4) for k, v in s.metrics.items()}}
            for s in surfaces
        ],
        "inputs": {
            "dem": cfg["dem_glob"], "demStep": terrain.step, "demEpsg": terrain.epsg,
            "features": cfg["features"],
            "tessellationCellM": cell,
            "tessellationRule": "2 x DEM post spacing",
            "terrainMeshStepM": terrain_step,
            "displayClearanceM": clearance,
            "displayClearanceNote": ("presentation only: vertices are raised to clear the "
                                     "coarser terrain mesh; no measurement uses these heights"),
            "featuresSha256": _sha256(cfg["features"]),
            "widthModel": (getattr(profile, "WIDTH_MODEL_PARAMS", None)
                           if cfg.get("sweep_lines", True) else None),
        },
        "elapsedSeconds": round(time.time() - t0, 1),
    }
    with open(os.path.join(out_dir, "build-report.json"), "w") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print(f"· done in {report['elapsedSeconds']}s → {out_dir}")
    print(f"  pistes  {stats_p['triangles']:7d} tri  {stats_p['bytes']/1e6:5.2f} MB")
    print(f"  terrain {stats_t['triangles']:7d} tri  {stats_t['bytes']/1e6:5.2f} MB")
    return report


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default="out")
    args = ap.parse_args(argv)
    with open(args.config) as fh:
        cfg = json.load(fh)
    build(cfg, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
