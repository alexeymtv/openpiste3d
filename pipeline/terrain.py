"""Terrain: load a DEM, sample heights, derive gradients.

The DEM is the only source of elevation in the pipeline. Nothing here knows
about ski pistes – it works for any linear or areal feature class.
"""
from dataclasses import dataclass
import glob
import math

import numpy as np


@dataclass
class Terrain:
    """A regular elevation grid in a projected CRS.

    grid[0] is the NORTH edge. x runs east from `left`, y runs north from `bottom`.
    """
    grid: np.ndarray          # (ny, nx) float32, metres
    left: float               # easting of column 0, projected CRS units
    bottom: float             # northing of the last row
    step: float               # post spacing, metres
    epsg: int                 # projected CRS of the grid

    @property
    def width(self) -> float:
        return (self.grid.shape[1] - 1) * self.step

    @property
    def height(self) -> float:
        return (self.grid.shape[0] - 1) * self.step

    @classmethod
    def from_tiles(cls, pattern: str, step: float = 5.0, epsg: int = 25832) -> "Terrain":
        """Merge a directory of DEM tiles, resampling to `step` metres."""
        import rasterio
        from rasterio.merge import merge

        files = sorted(glob.glob(pattern, recursive=True))
        if not files:
            raise FileNotFoundError(f"no DEM tiles matched {pattern}")
        sources = [rasterio.open(f) for f in files]
        arr, transform = merge(sources, res=(step, step), nodata=-9999)
        for s in sources:
            s.close()
        g = arr[0].astype("float32")
        g[g == -9999] = np.nan
        if np.isnan(g).any():
            g = _fill_nodata(g)
        left = transform.c
        top = transform.f
        bottom = top - g.shape[0] * step
        return cls(grid=g, left=left, bottom=bottom, step=step, epsg=epsg)

    def crop(self, minx: float, miny: float, maxx: float, maxy: float, margin: float = 200.0) -> "Terrain":
        """Crop to a projected-CRS bounding box plus a margin."""
        s = self.step
        i0 = max(0, int((minx - margin - self.left) // s))
        i1 = min(self.grid.shape[1], int((maxx + margin - self.left) // s) + 2)
        top = self.bottom + self.height
        j0 = max(0, int((top - (maxy + margin)) // s))
        j1 = min(self.grid.shape[0], int((top - (miny - margin)) // s) + 2)
        sub = self.grid[j0:j1, i0:i1].copy()
        return Terrain(
            grid=sub,
            left=self.left + i0 * s,
            bottom=top - j1 * s,
            step=s,
            epsg=self.epsg,
        )

    # --- sampling -------------------------------------------------------
    def height_at(self, x: float, y: float) -> float:
        """Bilinear height. x east of `left`, y north of `bottom`, both metres."""
        ny, nx = self.grid.shape
        fx = x / self.step
        fy = (self.height - y) / self.step
        i0 = min(max(int(math.floor(fx)), 0), nx - 2)
        j0 = min(max(int(math.floor(fy)), 0), ny - 2)
        tx = min(max(fx - i0, 0.0), 1.0)
        ty = min(max(fy - j0, 0.0), 1.0)
        g = self.grid
        a, b = g[j0, i0], g[j0, i0 + 1]
        c, d = g[j0 + 1, i0], g[j0 + 1, i0 + 1]
        return float((a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty)

    def gradient_at(self, x: float, y: float):
        """(dz/dx, dz/dy) by central differences at one DEM post spacing."""
        d = self.step
        hx = (self.height_at(min(self.width, x + d), y) - self.height_at(max(0.0, x - d), y)) / (2 * d)
        hy = (self.height_at(x, min(self.height, y + d)) - self.height_at(x, max(0.0, y - d))) / (2 * d)
        return hx, hy

    def slope_at(self, x: float, y: float) -> float:
        """Slope as a ratio (rise/run), i.e. tan(angle)."""
        hx, hy = self.gradient_at(x, y)
        return math.hypot(hx, hy)


def _fill_nodata(g: np.ndarray) -> np.ndarray:
    """Nearest-neighbour fill of small nodata holes so sampling never returns NaN."""
    mask = np.isnan(g)
    if not mask.any():
        return g
    try:
        from scipy import ndimage
        idx = ndimage.distance_transform_edt(mask, return_distances=False, return_indices=True)
        return g[tuple(idx)]
    except ImportError:
        out = g.copy()
        med = float(np.nanmedian(g))
        out[mask] = med
        return out
