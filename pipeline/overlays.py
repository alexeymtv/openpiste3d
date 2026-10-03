"""Reference lines drawn over the tileset: source centrelines and contours.

Neither of these is part of the published data. They exist so that a viewer can
show the surfaces in context:

  source centrelines  the input the footprints were derived from, so the
                      before and after can be compared in one view
  contour lines       a neutral height reference, so relief is readable
                      without adding a second thematic colour

They are written as plain GeoJSON-ish arrays of lon/lat/height rather than as
tile content, because they are presentation, not data with measurements
attached. Keeping them out of the tileset keeps the distinction honest.
"""
import json
import math
from typing import List, Tuple

import numpy as np
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform as shp_transform


def write_source_lines(path: str, features_path: str, terrain, src_epsg: int = 4326,
                       class_field: str = "piste:difficulty",
                       filter_field: str = None, filter_value: str = None,
                       lift: float = 1.25) -> dict:
    """Drape the input centrelines on the terrain and write them as lon/lat/height.

    `lift` raises the line above the terrain mesh so it is not swallowed by it.
    The terrain tile is meshed more coarsely than the DEM it came from, so a
    line laid exactly on the DEM surface disappears into the mesh in places.
    This offset is presentation only; no measurement uses it.
    """
    to_local = Transformer.from_crs(f"EPSG:{src_epsg}", f"EPSG:{terrain.epsg}", always_xy=True)
    to_wgs = Transformer.from_crs(f"EPSG:{terrain.epsg}", "EPSG:4326", always_xy=True)

    with open(features_path) as fh:
        gj = json.load(fh)

    out = []
    for feat in gj.get("features", []):
        props = feat.get("properties", {})
        if filter_field and props.get(filter_field) != filter_value:
            continue
        geom = shape(feat["geometry"])
        if geom.geom_type == "LineString":
            parts = [geom]
        elif geom.geom_type == "MultiLineString":
            parts = list(geom.geoms)
        else:
            continue

        for part in parts:
            coords = []
            for lon, lat in list(part.coords):
                e, n = to_local.transform(lon, lat)
                x, y = e - terrain.left, n - terrain.bottom
                if not (0 <= x <= terrain.width and 0 <= y <= terrain.height):
                    continue
                z = terrain.height_at(x, y) + lift
                wlon, wlat = to_wgs.transform(e, n)
                coords.append([round(wlon, 7), round(wlat, 7), round(z, 2)])
            if len(coords) >= 2:
                out.append({
                    "name": props.get("name") or "",
                    "difficulty": props.get(class_field) or "unknown",
                    "coordinates": coords,
                })

    with open(path, "w") as fh:
        json.dump({"features": out}, fh)
    return {"lines": len(out), "vertices": sum(len(f["coordinates"]) for f in out)}


def write_contours(path: str, terrain, interval: float = 100.0, lift: float = 0.5,
                   min_vertices: int = 8, simplify: float = 1.0) -> dict:
    """Trace contour lines across the DEM at a fixed vertical interval.

    `simplify` is a Douglas-Peucker tolerance in grid cells. Traced at full DEM
    resolution a 100 m contour over this area runs to hundreds of thousands of
    vertices, almost all of them invisible at any sane zoom; dropping the ones
    that move the line by less than a cell cuts the file by an order of
    magnitude without a visible change.
    """
    zmin = float(np.nanmin(terrain.grid))
    zmax = float(np.nanmax(terrain.grid))
    first = math.ceil(zmin / interval) * interval

    to_wgs = Transformer.from_crs(f"EPSG:{terrain.epsg}", "EPSG:4326", always_xy=True)

    from shapely.geometry import LineString

    features = []
    level = first
    while level < zmax:
        for line in _trace_level(terrain.grid, level):
            if len(line) < min_vertices:
                continue
            if simplify > 0 and len(line) > 2:
                line = list(LineString(line).simplify(simplify).coords)
                if len(line) < 2:
                    continue
            coords = []
            for (col, row) in line:
                x = col * terrain.step
                y = terrain.height - row * terrain.step
                lon, lat = to_wgs.transform(terrain.left + x, terrain.bottom + y)
                coords.append([round(lon, 7), round(lat, 7), round(level + lift, 2)])
            features.append({
                "type": "Feature",
                "properties": {"elevationM": level},
                "geometry": {"type": "LineString", "coordinates": coords},
            })
        level += interval

    with open(path, "w") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh)
    return {"contours": len(features), "intervalM": interval,
            "levels": int(round((zmax - first) / interval))}


# --- marching squares -----------------------------------------------------
#
# Written out rather than taken from a plotting or image-processing library:
# the whole pipeline otherwise depends only on numpy, shapely, pyproj, rasterio
# and a triangulator, and a contour tracer is not worth a heavy dependency.

_EDGES = {
    # case -> list of (edge_a, edge_b) segments, edges numbered
    # 0 top, 1 right, 2 bottom, 3 left
    1: [(3, 2)], 2: [(2, 1)], 3: [(3, 1)], 4: [(0, 1)],
    5: [(3, 0), (2, 1)], 6: [(2, 0)], 7: [(3, 0)],
    8: [(3, 0)], 9: [(2, 0)], 10: [(3, 2), (0, 1)], 11: [(0, 1)],
    12: [(3, 1)], 13: [(2, 1)], 14: [(3, 2)],
}


def _trace_level(grid: np.ndarray, level: float) -> List[List[Tuple[float, float]]]:
    """Return polylines, in (column, row) grid coordinates, at one height.

    The case number for every cell is computed with numpy, then only the cells
    the contour actually crosses are visited. Walking all of them in Python once
    per level is what made this the slowest step in the build.
    """
    above = grid > level
    tl = above[:-1, :-1]
    tr = above[:-1, 1:]
    br = above[1:, 1:]
    bl = above[1:, :-1]
    case = (tl.astype(np.uint8) << 3) | (tr.astype(np.uint8) << 2) \
        | (br.astype(np.uint8) << 1) | bl.astype(np.uint8)

    rows, cols = np.nonzero((case > 0) & (case < 15))
    if rows.size == 0:
        return []

    g = grid
    segments = {}
    for j, i in zip(rows.tolist(), cols.tolist()):
        v = (g[j, i], g[j, i + 1], g[j + 1, i + 1], g[j + 1, i])
        for a, b in _EDGES[case[j, i]]:
            pa = _edge_point(i, j, a, v, level)
            pb = _edge_point(i, j, b, v, level)
            segments.setdefault(pa, []).append(pb)
            segments.setdefault(pb, []).append(pa)

    return _chain(segments)


def _edge_point(i: int, j: int, edge: int, v, level: float) -> Tuple[float, float]:
    """Interpolate where the level crosses one edge of cell (i, j)."""
    tl, tr, br, bl = v
    if edge == 0:                       # top, between tl and tr
        t = _frac(tl, tr, level)
        p = (i + t, float(j))
    elif edge == 1:                     # right, between tr and br
        t = _frac(tr, br, level)
        p = (float(i + 1), j + t)
    elif edge == 2:                     # bottom, between bl and br
        t = _frac(bl, br, level)
        p = (i + t, float(j + 1))
    else:                               # left, between tl and bl
        t = _frac(tl, bl, level)
        p = (float(i), j + t)
    return (round(p[0], 4), round(p[1], 4))


def _frac(a: float, b: float, level: float) -> float:
    d = b - a
    if d == 0:
        return 0.5
    return min(max((level - a) / d, 0.0), 1.0)


def _chain(segments: dict) -> List[List[Tuple[float, float]]]:
    """Walk the segment graph into continuous polylines."""
    remaining = {k: list(v) for k, v in segments.items()}
    lines = []

    def walk(start):
        line = [start]
        current = start
        while True:
            nbrs = remaining.get(current)
            if not nbrs:
                break
            nxt = nbrs.pop()
            back = remaining.get(nxt)
            if back and current in back:
                back.remove(current)
            line.append(nxt)
            current = nxt
        return line

    # open lines first, so they are not broken mid-way by a closed loop walk
    for node in [k for k, v in remaining.items() if len(v) == 1]:
        if remaining.get(node):
            lines.append(walk(node))
    for node in list(remaining):
        if remaining.get(node):
            lines.append(walk(node))
    return [l for l in lines if len(l) >= 2]
