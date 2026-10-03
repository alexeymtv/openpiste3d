"""Turn areal features into terrain-conforming surfaces, and measure them.

A polygon on its own is flat. Laying it on relief means subdividing it until its
triangles follow the terrain, rather than touching the terrain only at the
polygon's own vertices.
"""
from dataclasses import dataclass, field
import math
from typing import List, Optional

import numpy as np
from shapely.geometry import box, shape, mapping
from shapely.ops import unary_union, transform as shp_transform

from .terrain import Terrain

try:
    import mapbox_earcut as earcut
except ImportError:  # pragma: no cover
    earcut = None


@dataclass
class Surface:
    """One feature: its footprint, its terrain-conforming mesh, its measurements."""
    fid: int
    name: str
    difficulty: str
    polygon: object                     # shapely (Multi)Polygon in local metres
    source: str = "mapped-area"         # or "swept-from-centreline"
    vertices: np.ndarray = field(default=None)   # (n,3) local x,y,z metres
    triangles: np.ndarray = field(default=None)  # (m,3) indices
    metrics: dict = field(default_factory=dict)
    display_z: np.ndarray = field(default=None)  # (n,) metres, presentation only


MIN_TRIANGLE_AREA = 0.5     # m², in plan
MIN_TRIANGLE_ASPECT = 0.02  # altitude on the longest edge, relative to that edge


def tessellate(polygon, terrain: Terrain, cell: float = 20.0, lift: float = 0.35,
               min_piece_area: float = 0.05):
    """Subdivide a polygon on a regular grid and drape it on the terrain.

    Clipping against a grid keeps the polygon's real boundary exactly while
    giving the interior enough vertices to follow relief. `lift` raises the
    surface slightly so it does not z-fight with a terrain layer underneath.

    Every triangle is kept, including the slivers that grid clipping produces
    where the boundary grazes a cell edge. Dropping them here used to leave the
    rendered surface full of small holes, and a published area that the mesh did
    not actually cover. They are excluded from the slope statistics instead –
    see `measure`, which applies the same test.
    """
    if earcut is None:
        raise ImportError("mapbox_earcut is required: pip install mapbox-earcut")


    minx, miny, maxx, maxy = polygon.bounds
    verts: List[tuple] = []
    index = {}
    tris: List[tuple] = []

    def vid(x, y):
        key = (round(x, 3), round(y, 3))
        got = index.get(key)
        if got is None:
            got = len(verts)
            index[key] = got
            verts.append((x, y, terrain.height_at(x, y) + lift))
        return got

    x = math.floor(minx / cell) * cell
    while x < maxx:
        y = math.floor(miny / cell) * cell
        while y < maxy:
            piece = polygon.intersection(box(x, y, x + cell, y + cell))
            if not piece.is_empty and piece.area > min_piece_area:
                parts = [piece] if piece.geom_type == "Polygon" else [
                    g for g in getattr(piece, "geoms", []) if g.geom_type == "Polygon"
                ]
                for pc in parts:
                    ring = np.array(pc.exterior.coords[:-1], dtype=np.float64)
                    if len(ring) < 3:
                        continue
                    pts = ring
                    rings = np.array([len(ring)])
                    for hole in pc.interiors:
                        hr = np.array(hole.coords[:-1], dtype=np.float64)
                        if len(hr) < 3:
                            continue
                        pts = np.vstack([pts, hr])
                        rings = np.append(rings, len(pts))
                    try:
                        idx = earcut.triangulate_float64(pts, rings)
                    except Exception:
                        continue
                    for t in range(0, len(idx), 3):
                        a, b, c = (pts[idx[t]], pts[idx[t + 1]], pts[idx[t + 2]])
                        tris.append((vid(*a), vid(*b), vid(*c)))
            y += cell
        x += cell

    if not tris:
        return None, None
    return np.array(verts, dtype=np.float64), np.array(tris, dtype=np.int32)


def clearance_above_terrain_mesh(vertices, terrain: Terrain, mesh_step: float,
                                 clearance: float = 0.4) -> np.ndarray:
    """Heights at which the surface clears the terrain tile, for display only.

    The surface is draped on the DEM at its own spacing, but the terrain tileset
    is a coarser mesh whose posts are sampled every `mesh_step` metres and joined
    by flat triangles. Between posts that mesh can sit *above* the DEM – on a
    concave slope by as much as a few metres here – and wherever it does, the
    terrain pokes through the surface and the viewer shows ragged holes in it.

    A single constant offset cannot fix that without floating the surface
    visibly: measured on the Garmisch build, a 0.35 m offset leaves 16% of the
    area below the terrain mesh and clearing the worst case outright would take
    more than 3 m. So the offset is computed per vertex instead – each one is
    raised to clear whichever is higher, the DEM or the terrain mesh, by
    `clearance`.

    The returned heights are never used for measurement. `Surface.vertices`
    keeps the draped DEM heights, and every published number comes from those.
    """
    nx = int(terrain.width // mesh_step) + 1
    ny = int(terrain.height // mesh_step) + 1
    xs = np.linspace(0, terrain.width, nx)
    ys = np.linspace(0, terrain.height, ny)
    posts = np.array([[terrain.height_at(x, y) for x in xs] for y in ys])
    dx = xs[1] - xs[0] if nx > 1 else 1.0
    dy = ys[1] - ys[0] if ny > 1 else 1.0

    out = np.empty(len(vertices), dtype=np.float64)
    for k, (x, y, z) in enumerate(vertices):
        fx = min(max(x / dx, 0.0), nx - 1.001)
        fy = min(max(y / dy, 0.0), ny - 1.001)
        i, j = int(fx), int(fy)
        tx, ty = fx - i, fy - j
        a, b = posts[j, i], posts[j, i + 1]
        c, d = posts[j + 1, i], posts[j + 1, i + 1]
        mesh_z = (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty
        out[k] = max(z, mesh_z) + clearance
    return out


def _is_sliver(a, b, c, min_area: float = MIN_TRIANGLE_AREA,
               min_aspect: float = MIN_TRIANGLE_ASPECT) -> bool:
    """True for triangles too small or too thin *in plan* to carry a normal.

    Judged on the horizontal footprint only. A triangle that is a sliver in plan
    can still be large in three dimensions, if its corners sit at very different
    heights – which is exactly why area weighting alone does not protect the
    statistics from it, and why it has to be named and excluded.
    """
    ax, ay = a; bx, by = b; cx, cy = c
    area2 = abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay))
    if area2 * 0.5 < min_area:
        return True
    longest = max(math.dist(a, b), math.dist(b, c), math.dist(c, a))
    if longest <= 0:
        return True
    # altitude onto the longest edge, relative to that edge
    return (area2 / longest) / longest < min_aspect


def measure(surface: Surface, terrain: Terrain, centreline=None) -> dict:
    """Terrain-derived attributes.

    Slope statistics are taken over the surface itself (area-weighted by
    triangle), not along a centreline, so the numbers describe the whole run
    rather than one chosen path down it.
    """
    v, t = surface.vertices, surface.triangles
    if v is None:
        return {}

    tri_slope = []
    tri_area = []
    skipped = 0
    for a, b, c in t:
        p, q, r = v[a], v[b], v[c]
        # Degenerate in plan: the normal is decided by height noise across two
        # nearly coincident points, so the slope it implies means nothing. Such a
        # triangle stays in the mesh – removing it would hole the surface – but it
        # does not get a vote here.
        if _is_sliver(p[:2], q[:2], r[:2]):
            skipped += 1
            continue
        n = np.cross(q - p, r - p)
        area = 0.5 * float(np.linalg.norm(n))
        if area <= 0 or n[2] == 0:
            continue
        # slope of the triangle plane = |horizontal normal| / |vertical normal|
        slope = math.hypot(n[0], n[1]) / abs(n[2])
        tri_slope.append(slope)
        tri_area.append(area)

    if not tri_slope:
        return {}

    s = np.array(tri_slope)
    w = np.array(tri_area)
    order = np.argsort(s)
    s_sorted, w_sorted = s[order], w[order]
    cum = np.cumsum(w_sorted) / w_sorted.sum()

    def weighted_quantile(q):
        return float(s_sorted[int(np.searchsorted(cum, q))])

    z = v[:, 2]
    # Quantiles only. A maximum over DEM-derived triangle normals is not a
    # geographic measurement – it is whatever the noisiest triangle happens to
    # be – so it is deliberately not reported.
    out = {
        "areaM2": float(surface.polygon.area),
        "minElevationM": float(z.min()),
        "maxElevationM": float(z.max()),
        "verticalExtentM": float(z.max() - z.min()),
        "meanSlope": float((s * w).sum() / w.sum()),
        "medianSlope": weighted_quantile(0.5),
        "p90Slope": weighted_quantile(0.9),
        "p95Slope": weighted_quantile(0.95),
    }
    out["trianglesMeasured"] = len(tri_slope)
    out["trianglesSkippedAsDegenerate"] = skipped
    if centreline is not None:
        out["centrelineLengthM"] = float(centreline.length)
        if out["centrelineLengthM"] > 0:
            out["meanWidthM"] = out["areaM2"] / out["centrelineLengthM"]
    out["meanSlopeDeg"] = math.degrees(math.atan(out["meanSlope"]))
    out["p90SlopeDeg"] = math.degrees(math.atan(out["p90Slope"]))
    return out


def variable_width_footprint(line, width_fn, station: float = 8.0):
    """Sweep a centreline into a footprint whose width varies along it.

    `buffer()` is not enough here, because it applies one distance to the whole
    geometry: a run that opens out and then chokes comes back the same width at
    both. Instead the half-width is evaluated at every station from a model that
    may depend on position, class or a measured attribute, and the two offset
    chains are closed into a polygon.

    width_fn(s) -> metres, where s is normalised distance along the line [0, 1].
    """
    from shapely.geometry import Polygon, LineString

    if line.length <= 0:
        return None
    n = max(2, int(line.length // station) + 1)
    stations = [line.interpolate(i / (n - 1), normalized=True) for i in range(n)]
    pts = [(p.x, p.y) for p in stations]

    left, right = [], []
    for i, (x, y) in enumerate(pts):
        j0, j1 = max(0, i - 1), min(n - 1, i + 1)
        tx, ty = pts[j1][0] - pts[j0][0], pts[j1][1] - pts[j0][1]
        tl = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / tl, tx / tl
        half = max(1.0, width_fn(i / (n - 1))) / 2.0
        left.append((x + nx * half, y + ny * half))
        right.append((x - nx * half, y - ny * half))

    ring = left + right[::-1]
    poly = Polygon(ring)
    if not poly.is_valid:
        poly = poly.buffer(0)            # resolve self-intersection on tight curves
    if poly.is_empty:
        return None
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    return poly


def load_features(path: str, terrain: Terrain, src_epsg: int = 4326,
                  name_field: str = "name", class_field: str = "piste:difficulty",
                  filter_field: Optional[str] = None, filter_value: Optional[str] = None,
                  width_model=None, width_field: Optional[str] = None,
                  prefer_mapped: bool = True):
    """Read features from GeoJSON/GeoPackage into terrain-local metres.

    Both geometry types are accepted:

      Polygon / MultiPolygon  used as the footprint directly (mapped areas,
                              hand-digitised outlines from orthoimagery)
      LineString              swept into a footprint by `variable_width_footprint`
                              using `width_model`, because a line is a
                              cartographic abstraction of something that
                              occupies ground

    The pipeline is source-agnostic: anything that yields a geometry, a name and
    a class works.
    """
    import json
    from pyproj import Transformer

    to_local_crs = Transformer.from_crs(f"EPSG:{src_epsg}", f"EPSG:{terrain.epsg}", always_xy=True)

    def to_local(geom):
        def f(x, y, z=None):
            e, n = to_local_crs.transform(x, y)
            return (e - terrain.left, n - terrain.bottom)
        return shp_transform(f, geom)

    if path.lower().endswith((".gpkg", ".shp")):
        import fiona
        with fiona.open(path) as src:
            records = [(dict(r["properties"]), shape(r["geometry"])) for r in src]
    else:
        with open(path) as fh:
            gj = json.load(fh)
        records = [(f.get("properties", {}), shape(f["geometry"])) for f in gj["features"]]

    window = box(0, 0, terrain.width, terrain.height)
    grouped = {}
    stats = {"polygon": 0, "line": 0, "skipped": 0}
    for props, geom in records:
        if filter_field and props.get(filter_field) != filter_value:
            continue
        cls = props.get(class_field) or "unknown"

        if geom.geom_type in ("Polygon", "MultiPolygon"):
            g = to_local(geom)
            if not g.is_valid:
                g = g.buffer(0)
            stats["polygon"] += 1
        elif geom.geom_type in ("LineString", "MultiLineString") and width_model is not None:
            lg = to_local(geom)
            lines = [lg] if lg.geom_type == "LineString" else list(lg.geoms)
            parts = []
            for ln in lines:
                if ln.length < 40:
                    continue
                explicit = props.get(width_field) if width_field else None
                try:
                    explicit = float(explicit) if explicit is not None else None
                except (TypeError, ValueError):
                    explicit = None
                fn = width_model(cls, props, explicit)
                fp = variable_width_footprint(ln, fn)
                if fp is not None:
                    parts.append(fp)
            if not parts:
                stats["skipped"] += 1
                continue
            g = unary_union(parts)
            stats["line"] += 1
        else:
            stats["skipped"] += 1
            continue

        g = g.intersection(window)
        if g.is_empty or g.area < 500:
            stats["skipped"] += 1
            continue
        key = (props.get(name_field) or "", cls,
               "mapped-area" if geom.geom_type in ("Polygon", "MultiPolygon")
               else "swept-from-centreline")
        grouped.setdefault(key, []).append(g)

    # A mapped area always beats a footprint swept from the centreline of the
    # same run: the sweep is a model, the area is someone's survey of the ground.
    if prefer_mapped:
        mapped = {(n, c) for (n, c, src) in grouped if src == "mapped-area"}
        grouped = {k: v for k, v in grouped.items()
                   if k[2] == "mapped-area" or (k[0], k[1]) not in mapped}

    surfaces = []
    for fid, ((name, cls, src), geoms) in enumerate(sorted(grouped.items())):
        merged = unary_union(geoms)
        surfaces.append(Surface(fid=fid, name=name or f"unnamed {fid}",
                                difficulty=cls, polygon=merged, source=src))
    return surfaces, stats
