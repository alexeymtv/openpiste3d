"""Write OGC 3D Tiles 1.1 – glTF tile content with per-feature metadata.

Two extensions do the work that makes this 1.1 rather than 1.0:

  EXT_mesh_features        gives every vertex a feature id, so a click picks
                           a whole piste rather than one triangle
  EXT_structural_metadata  carries a typed property table alongside the mesh,
                           so the terrain-derived measurements travel with the
                           geometry instead of living in a separate sidecar

Tile content is glTF directly (`.glb`), which 3D Tiles 1.1 allows and 1.0 did not.
"""
import json
import math
import struct
from typing import List

import numpy as np
from pyproj import Transformer

GLTF_FLOAT = 5126
GLTF_UINT32 = 5125
GLTF_ARRAY_BUFFER = 34962
GLTF_ELEMENT_ARRAY_BUFFER = 34963

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)


class GLB:
    """Minimal glTF 2.0 binary writer – only what the pipeline emits."""

    def __init__(self):
        self.bin = bytearray()
        self.buffer_views: List[dict] = []
        self.accessors: List[dict] = []

    def _align(self, n=4, pad=b"\x00"):
        while len(self.bin) % n:
            self.bin += pad

    def add_view(self, data: bytes, target=None, stride=None) -> int:
        self._align(4)
        offset = len(self.bin)
        self.bin += data
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target:
            view["target"] = target
        if stride:
            view["byteStride"] = stride
        self.buffer_views.append(view)
        return len(self.buffer_views) - 1

    def add_accessor(self, view: int, component_type: int, count: int, type_: str,
                     minimum=None, maximum=None) -> int:
        acc = {"bufferView": view, "componentType": component_type,
               "count": count, "type": type_}
        if minimum is not None:
            acc["min"] = [float(v) for v in minimum]
            acc["max"] = [float(v) for v in maximum]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def write(self, gltf: dict, path: str):
        self._align(4)
        gltf["buffers"] = [{"byteLength": len(self.bin)}]
        gltf["bufferViews"] = self.buffer_views
        gltf["accessors"] = self.accessors
        js = json.dumps(gltf, separators=(",", ":")).encode()
        while len(js) % 4:
            js += b" "
        blob = bytes(self.bin)
        total = 12 + 8 + len(js) + 8 + len(blob)
        with open(path, "wb") as fh:
            fh.write(struct.pack("<III", 0x46546C67, 2, total))
            fh.write(struct.pack("<II", len(js), 0x4E4F534A))
            fh.write(js)
            fh.write(struct.pack("<II", len(blob), 0x004E4942))
            fh.write(blob)
        return total


# --- geodesy ------------------------------------------------------------
def geodetic_to_ecef(lon_deg, lat_deg, h):
    lon, lat = math.radians(lon_deg), math.radians(lat_deg)
    s, c = math.sin(lat), math.cos(lat)
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * s * s)
    return ((n + h) * c * math.cos(lon),
            (n + h) * c * math.sin(lon),
            (n * (1 - WGS84_E2) + h) * s)


def enu_to_ecef_matrix(lon_deg, lat_deg, h):
    """Column-major 4x4 placing a local east-north-up frame on the ellipsoid."""
    lon, lat = math.radians(lon_deg), math.radians(lat_deg)
    sl, cl = math.sin(lon), math.cos(lon)
    sp, cp = math.sin(lat), math.cos(lat)
    east = (-sl, cl, 0.0)
    north = (-sp * cl, -sp * sl, cp)
    up = (cp * cl, cp * sl, sp)
    ox, oy, oz = geodetic_to_ecef(lon_deg, lat_deg, h)
    return [east[0], east[1], east[2], 0.0,
            north[0], north[1], north[2], 0.0,
            up[0], up[1], up[2], 0.0,
            ox, oy, oz, 1.0]


# --- property tables ----------------------------------------------------
_NUMERIC = {"FLOAT32": (GLTF_FLOAT, "<f4"), "UINT32": (GLTF_UINT32, "<u4")}


def _string_property(glb: GLB, values: List[str]):
    blob = b"".join(v.encode("utf-8") for v in values)
    offsets = [0]
    for v in values:
        offsets.append(offsets[-1] + len(v.encode("utf-8")))
    vi = glb.add_view(blob if blob else b"\x00")
    oi = glb.add_view(np.array(offsets, dtype="<u4").tobytes())
    return {"values": vi, "stringOffsets": oi, "stringOffsetType": "UINT32"}


def _scalar_property(glb: GLB, values, dtype="<f4"):
    arr = np.array(values, dtype=dtype)
    return {"values": glb.add_view(arr.tobytes())}


def write_feature_glb(path: str, surfaces, origin_lonlat_h, schema: dict,
                      properties: dict, source_epsg: int, terrain_left: float,
                      terrain_bottom: float, class_name: str = "feature",
                      string_properties=("name",)):
    """One glTF holding every surface, each triangle tagged with its feature id.

    Vertices are written in the local ENU frame given by `origin_lonlat_h`; the
    tileset's `transform` puts that frame on the globe. glTF is Y-up, so the
    local frame is mapped east->x, up->y, north->-z.
    """
    glb = GLB()
    to_wgs = Transformer.from_crs(f"EPSG:{source_epsg}", "EPSG:4326", always_xy=True)
    lon0, lat0, h0 = origin_lonlat_h

    # local ENU metres relative to the origin, via geodetic coordinates
    positions = []
    normals = []
    feature_ids = []
    indices = []
    base = 0
    o_ecef = np.array(geodetic_to_ecef(lon0, lat0, h0))
    m = enu_to_ecef_matrix(lon0, lat0, h0)
    r = np.array([[m[0], m[4], m[8]], [m[1], m[5], m[9]], [m[2], m[6], m[10]]])
    r_inv = r.T  # orthonormal

    for s in surfaces:
        if s.vertices is None:
            continue
        v = s.vertices
        # `display_z`, when present, is what gets written: the measured surface
        # raised just enough to clear the coarser terrain mesh. The measurements
        # were taken on `v[:, 2]` and are not affected.
        z = s.display_z if getattr(s, "display_z", None) is not None else v[:, 2]
        lon, lat = to_wgs.transform(v[:, 0] + terrain_left, v[:, 1] + terrain_bottom)
        ecef = np.array([geodetic_to_ecef(lo, la, zz) for lo, la, zz in zip(lon, lat, z)])
        enu = (ecef - o_ecef) @ r_inv.T           # east, north, up
        gl = np.column_stack([enu[:, 0], enu[:, 2], -enu[:, 1]])  # glTF is Y-up
        positions.append(gl)
        feature_ids.append(np.full(len(gl), float(s.fid), dtype="<f4"))
        tri = s.triangles + base
        indices.append(tri)
        base += len(gl)

        n = np.zeros_like(gl)
        for a, b, c in s.triangles:
            fn = np.cross(gl[b] - gl[a], gl[c] - gl[a])
            n[a] += fn
            n[b] += fn
            n[c] += fn
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        ln[ln == 0] = 1
        normals.append(n / ln)

    pos = np.vstack(positions).astype("<f4")
    nrm = np.vstack(normals).astype("<f4")
    fid = np.concatenate(feature_ids).astype("<f4")
    idx = np.vstack(indices).astype("<u4").ravel()

    v_pos = glb.add_view(pos.tobytes(), GLTF_ARRAY_BUFFER)
    v_nrm = glb.add_view(nrm.tobytes(), GLTF_ARRAY_BUFFER)
    v_fid = glb.add_view(fid.tobytes(), GLTF_ARRAY_BUFFER)
    v_idx = glb.add_view(idx.tobytes(), GLTF_ELEMENT_ARRAY_BUFFER)

    a_pos = glb.add_accessor(v_pos, GLTF_FLOAT, len(pos), "VEC3",
                             pos.min(axis=0), pos.max(axis=0))
    a_nrm = glb.add_accessor(v_nrm, GLTF_FLOAT, len(nrm), "VEC3")
    a_fid = glb.add_accessor(v_fid, GLTF_FLOAT, len(fid), "SCALAR")
    a_idx = glb.add_accessor(v_idx, GLTF_UINT32, len(idx), "SCALAR")

    table = {"class": class_name, "count": len(surfaces), "properties": {}}
    for prop, spec in schema["classes"][class_name]["properties"].items():
        values = properties[prop]
        if prop in string_properties or spec["type"] == "STRING":
            table["properties"][prop] = _string_property(glb, values)
        else:
            table["properties"][prop] = _scalar_property(glb, values)

    gltf = {
        "asset": {"version": "2.0", "generator": "OpenPiste3D"},
        "extensionsUsed": ["EXT_mesh_features", "EXT_structural_metadata"],
        "extensions": {
            "EXT_structural_metadata": {"schema": schema, "propertyTables": [table]}
        },
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{
            "primitives": [{
                "attributes": {"POSITION": a_pos, "NORMAL": a_nrm, "_FEATURE_ID_0": a_fid},
                "indices": a_idx,
                "material": 0,
                "mode": 4,
                "extensions": {
                    "EXT_mesh_features": {
                        "featureIds": [{"attribute": 0, "featureCount": len(surfaces),
                                        "propertyTable": 0}]
                    }
                },
            }]
        }],
        "materials": [{
            "pbrMetallicRoughness": {"baseColorFactor": [0.85, 0.87, 0.9, 1.0],
                                     "metallicFactor": 0.0, "roughnessFactor": 0.95},
            "doubleSided": True,
        }],
    }
    size = glb.write(gltf, path)
    return {"vertices": int(len(pos)), "triangles": int(len(idx) // 3), "bytes": size}


def write_terrain_glb(path: str, terrain, origin_lonlat_h, step: float = 15.0):
    """The DEM itself as a glTF surface, so the demo needs no terrain service."""
    glb = GLB()
    to_wgs = Transformer.from_crs(f"EPSG:{terrain.epsg}", "EPSG:4326", always_xy=True)
    lon0, lat0, h0 = origin_lonlat_h
    o_ecef = np.array(geodetic_to_ecef(lon0, lat0, h0))
    m = enu_to_ecef_matrix(lon0, lat0, h0)
    r_inv = np.array([[m[0], m[4], m[8]], [m[1], m[5], m[9]], [m[2], m[6], m[10]]]).T

    nx = int(terrain.width // step) + 1
    ny = int(terrain.height // step) + 1
    xs = np.linspace(0, terrain.width, nx)
    ys = np.linspace(0, terrain.height, ny)
    gx, gy = np.meshgrid(xs, ys)
    gz = np.array([[terrain.height_at(x, y) for x in xs] for y in ys])

    lon, lat = to_wgs.transform(gx.ravel() + terrain.left, gy.ravel() + terrain.bottom)
    ecef = np.array([geodetic_to_ecef(lo, la, z) for lo, la, z in zip(lon, lat, gz.ravel())])
    enu = (ecef - o_ecef) @ r_inv.T
    gl = np.column_stack([enu[:, 0], enu[:, 2], -enu[:, 1]]).astype("<f4")

    tris = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            tris.append((a, a + nx, a + 1))
            tris.append((a + 1, a + nx, a + nx + 1))
    idx = np.array(tris, dtype="<u4").ravel()

    n = np.zeros_like(gl)
    tri_arr = np.array(tris)
    fn = np.cross(gl[tri_arr[:, 1]] - gl[tri_arr[:, 0]], gl[tri_arr[:, 2]] - gl[tri_arr[:, 0]])
    for k in range(3):
        np.add.at(n, tri_arr[:, k], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1
    n = (n / ln).astype("<f4")

    v_pos = glb.add_view(gl.tobytes(), GLTF_ARRAY_BUFFER)
    v_nrm = glb.add_view(n.tobytes(), GLTF_ARRAY_BUFFER)
    v_idx = glb.add_view(idx.tobytes(), GLTF_ELEMENT_ARRAY_BUFFER)
    a_pos = glb.add_accessor(v_pos, GLTF_FLOAT, len(gl), "VEC3", gl.min(axis=0), gl.max(axis=0))
    a_nrm = glb.add_accessor(v_nrm, GLTF_FLOAT, len(n), "VEC3")
    a_idx = glb.add_accessor(v_idx, GLTF_UINT32, len(idx), "SCALAR")

    gltf = {
        "asset": {"version": "2.0", "generator": "OpenPiste3D"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{
            "attributes": {"POSITION": a_pos, "NORMAL": a_nrm},
            "indices": a_idx, "material": 0, "mode": 4}]}],
        "materials": [{
            "pbrMetallicRoughness": {"baseColorFactor": [0.52, 0.56, 0.60, 1.0],
                                     "metallicFactor": 0.0, "roughnessFactor": 1.0},
            "doubleSided": True}],
    }
    size = glb.write(gltf, path)
    return {"vertices": int(len(gl)), "triangles": int(len(idx) // 3), "bytes": size}


def write_tileset(path: str, content_uri: str, origin_lonlat_h, region_deg,
                  geometric_error: float = 256.0):
    """A minimal valid 3D Tiles 1.1 tileset around one glTF content."""
    west, south, east, north, h_min, h_max = region_deg
    tileset = {
        "asset": {"version": "1.1", "tilesetVersion": "openpiste3d-0.1"},
        "geometricError": geometric_error,
        "root": {
            "transform": enu_to_ecef_matrix(*origin_lonlat_h),
            "boundingVolume": {"region": [math.radians(west), math.radians(south),
                                          math.radians(east), math.radians(north),
                                          h_min, h_max]},
            "geometricError": 0.0,
            "refine": "REPLACE",
            "content": {"uri": content_uri},
        },
    }
    with open(path, "w") as fh:
        json.dump(tileset, fh, indent=2)
    return tileset
