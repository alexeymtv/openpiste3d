"""Ski piste profile – the only file in the repository that knows about skiing.

A profile supplies three things to the generic core:

  SCHEMA      the EXT_structural_metadata class written into the tileset
  width_model how wide the ground object is, when the source gives only a line
  PROPERTIES  which measured attributes are carried, and in what order
"""

CLASS_NAME = "piste"

# The width model is a heuristic, not a measurement. It is versioned so a build
# report can say which one produced a given footprint, and so changing it is a
# visible event rather than a silent drift.
WIDTH_MODEL_VERSION = "ski_piste.width.v1"
WIDTH_MODEL_PARAMS = {
    "version": WIDTH_MODEL_VERSION,
    "stationM": 8.0,
    "baseWidthM": {"novice": 55.0, "easy": 45.0, "intermediate": 32.0,
                   "advanced": 24.0, "expert": 20.0, "unknown": 30.0},
    "linkPathWidthM": 12.0,
    "taper": "0.72 + 0.28 * (1 - |2s-1|^1.6)",
    "note": "Typical groomed widths, chosen by the author from cartographic practice. "
            "They are not survey values. An explicit tagged width always overrides them, "
            "and footprints built this way are labelled swept-from-centreline.",
}

SCHEMA = {
    "id": "openpiste3d",
    "name": "Terrain-conforming surfaces",
    "classes": {
        CLASS_NAME: {
            "name": "Ski piste surface",
            "description": "A piste footprint draped on a digital elevation model, "
                           "with attributes measured from the terrain.",
            "properties": {
                "name": {"name": "Name", "type": "STRING"},
                "difficulty": {
                    "name": "Mapped difficulty", "type": "STRING",
                    "description": "The categorical grade as published. A local convention that "
                                   "reflects width, grooming, obstacles and local standards as "
                                   "well as steepness – not a measurement."},
                "source": {"name": "Footprint source", "type": "STRING",
                           "description": "mapped-area or swept-from-centreline."},
                "meanSlope": {
                    "name": "Mean slope", "type": "SCALAR", "componentType": "FLOAT32",
                    "description": "Area-weighted mean gradient of the surface (rise/run)."},
                "medianSlope": {"name": "Median slope", "type": "SCALAR", "componentType": "FLOAT32"},
                "p90Slope": {
                    "name": "90th-percentile slope", "type": "SCALAR", "componentType": "FLOAT32",
                    "description": "Gradient below which 90% of the surface area lies. A robust "
                                   "indicator of steep terrain, not a located pitch."},
                "p95Slope": {"name": "95th-percentile slope", "type": "SCALAR", "componentType": "FLOAT32"},
                "areaM2": {"name": "Surface area", "type": "SCALAR", "componentType": "FLOAT32"},
                "verticalExtentM": {"name": "Vertical extent", "type": "SCALAR", "componentType": "FLOAT32"},
                "minElevationM": {"name": "Lowest point", "type": "SCALAR", "componentType": "FLOAT32"},
                "maxElevationM": {"name": "Highest point", "type": "SCALAR", "componentType": "FLOAT32"},
            },
        }
    },
}

PROPERTIES = list(SCHEMA["classes"][CLASS_NAME]["properties"].keys())
STRING_PROPERTIES = ("name", "difficulty", "source")

# Typical groomed widths by grade, metres. Beginner terrain is broad, expert
# terrain is narrow, and link paths are narrow whatever they are graded.
_BASE_WIDTH = WIDTH_MODEL_PARAMS["baseWidthM"]


def width_model(cls, props, explicit=None):
    """Return width(s) in metres for normalised distance s along a centreline.

    An explicit tagged width always wins. Otherwise the grade sets a base width,
    link paths (Skiweg, Verbindung) are forced narrow, and the run is given a
    gentle spindle profile – narrower at the ends where it joins other runs,
    widest in the middle. It is a model, and it is labelled as one: footprints
    produced this way carry source = "swept-from-centreline".
    """
    if explicit and explicit > 0:
        return lambda s: explicit

    name = (props.get("name") or "").lower()
    base = _BASE_WIDTH.get(cls, _BASE_WIDTH["unknown"])
    if any(k in name for k in ("skiweg", "verbindung", "ziehweg", "verbindungsweg")):
        base = WIDTH_MODEL_PARAMS["linkPathWidthM"]

    def width(s):
        taper = 0.72 + 0.28 * (1.0 - abs(2.0 * s - 1.0) ** 1.6)
        return base * taper

    return width
