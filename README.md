# OpenPiste3D – from lines to surfaces

An open pipeline that turns geospatial features – **lines or areas** – into
**terrain-conforming surfaces with measured attributes**, and publishes them as
**OGC 3D Tiles 1.1** with per-feature metadata.

A line on a map is usually an abstraction of something that occupies ground. The
pipeline recovers the footprint, lays it on a digital elevation model, measures
the surface, and ships geometry and measurements together.

**[Live demo](https://alexeymtv.github.io/openpiste3d/viewer/)** – CesiumJS, no
account and no Cesium ion token required. Click any surface to read the metadata
out of the tileset itself.

By [Aleksei Matveev](https://github.com/alexeymtv), cartographer, Germany. Code MIT;
data licences are per dataset in [DATA-LICENSES.md](DATA-LICENSES.md).

## What that means, on one run

OpenStreetMap says the Osterfelder-Abfahrt is a **red** piste. That is the whole
of what a consumer can read from it: one word, a local convention that folds
together steepness, width, grooming and habit.

After the pipeline, the same run is a surface on the terrain, and it carries:

| | |
|---|---|
| vertical extent | 355 m |
| surface area | 5.35 ha |
| mean slope | 18.7° (34%) |
| steepest tenth (p90) | 27.6° (52%) |
| footprint source | mapped-area |

**Every one of those values is attached to the 3D feature itself**, not to a
spreadsheet beside it. Click the run in a viewer and the numbers come back from
the tileset. That is the difference between exporting geometry to a 3D format
and publishing a queryable geospatial artifact: the semantics travel with the
mesh, so a client can style, filter and query on measurements without ever
loading a second file.

Ski pistes in Garmisch-Partenkirchen are the first validation case. They are not
the point: they are the hardest case, because they are wide, their width varies,
they branch, and getting them wrong has a cost.

## Why this is not `buffer() + drape()`

The naive path – buffer a centreline, drape the polygon on terrain, export – breaks
in five places, and this pipeline is the five fixes:

0. **`buffer()` is one distance for the whole geometry.** A run that opens out and
   then chokes comes back the same width at both. `surfaces.variable_width_footprint`
   evaluates the half-width at every station from a model that can depend on
   position, class or a tagged attribute, and closes the two offset chains into a
   polygon. Footprints made this way are labelled `swept-from-centreline` in the
   metadata, so a consumer can always tell a model from a survey.
1. **A flat polygon does not follow relief.** Draping only its own vertices leaves
   long triangles that cut through ridges and float over hollows. `surfaces.tessellate`
   clips the footprint against a regular grid first, so the interior gains vertices
   while the real boundary is preserved exactly.
2. **Attributes have to come from the terrain, not from the tag.** `surfaces.measure`
   takes the slope of every triangle, area-weighted, and reports mean, median,
   90th and 95th percentile – no maximum, for the reason in point 4. A single
   `piste:difficulty` tag cannot express that.
3. **Metadata has to travel with the geometry.** The output carries
   `EXT_structural_metadata` with a typed schema, so a client can style and query
   by measured slope without a sidecar file.
4. **Grid clipping makes slivers.** Where a boundary grazes a cell edge the
   triangle is nearly degenerate in plan, its normal is decided by height noise, and
   its apparent slope explodes – an early build reported a maximum slope of 89.97° on
   a groomed piste. These triangles stay in the mesh, because dropping them left the
   rendered surface holed, but they are excluded from the statistics. Area weighting
   alone does not save you here: a triangle that is a sliver in plan can be large in
   three dimensions when its corners sit at different heights, and on one run that
   pushed the mean from 24° to 78°. No maximum is published either; see *What is
   measured* below.
5. **The result has to be reproducible.** One command, public inputs, a build report
   recording the inputs, their checksums and every free parameter.

## What it produces

```
out/
  pistes.json        3D Tiles 1.1 tileset  (asset.version = "1.1")
  pistes.glb         glTF tile content, EXT_mesh_features + EXT_structural_metadata
  terrain.json       3D Tiles 1.1 tileset of the DEM itself
  terrain.glb        glTF tile content
  build-report.json  every measurement, plus input paths and checksums
  source-lines.json  the input centrelines, draped – reference only
  contours.json      contours traced from the DEM, 50 m – reference only
```

Tile content is glTF directly, which 3D Tiles 1.1 permits and 1.0 did not.
The terrain tileset means the demo needs **no terrain service and no account**.

The last two files are not data in the sense the tileset is. They carry no
measurements and no metadata; they exist so the viewer can show the centrelines
the footprints came from, and a height reference when one is wanted. Both are
off until switched on, and keeping them outside the tileset is the point:
everything inside the tileset is measured. The contour interval is
`contour_interval` in the configuration.

## Run it – from a clean clone, with no downloads

The repository ships a sample area: a 2.2 x 2.6 km crop of DGM1 (173 KB) and the
OpenStreetMap extract. Nothing else is needed.

```bash
git clone https://github.com/alexeymtv/openpiste3d.git
cd openpiste3d
python3 -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m pipeline.cli --config config/sample.json --out out
python validate.py out/pistes.glb
python check_viewer_contract.py
```

That is the acceptance criterion for this project, and it is meant to be taken
literally: **a developer who has never spoken to the author clones the repository,
runs three commands on committed public inputs, and gets the same generated tileset.**
(The build report carries a timestamp, so the *directory* is not byte-identical run
to run; the tileset and its measurements are.) About six seconds on a laptop-class
machine; see BENCHMARK.md.

For the full Garmisch area – nine by seven kilometres of DGM1, fetched from the
Bavarian open-data portal:

```bash
python -m pipeline.fetch --config config/garmisch.json     # see the caveat in that file
python -m pipeline.cli   --config config/garmisch.json --out out
```

Other checks:

```bash
python experiments/cell_size.py     # cell-size sensitivity  → experiments/cell_size.md
python experiments/width_model.py   # width model vs mapped areas → experiments/width_model.md
python benchmark.py                 # timings and sizes     → BENCHMARK.md
```

### Open the viewer

**Double-clicking `viewer/index.html` will not work, and cannot be made to.** A page
opened from disk is not allowed to fetch the tileset – that is a browser rule, not a
missing feature here. The page detects it and says what to do instead. Served over
HTTP, including from GitHub Pages, it just works.

(The viewer reads `../out/`, so build into `out` as above.)

**Windows:** double-click `start-windows.bat`
**macOS / Linux:** double-click `start-mac-linux.command`

Or from a terminal, in the folder that contains `serve.py`:

```bash
python3 serve.py           # Windows: py serve.py
# or:  python3 -m http.server 8000   → http://localhost:8000/viewer/
```

`start-windows.bat` and `start-mac-linux.command` are wrappers around `serve.py`,
which picks a free port, serves this folder and opens the viewer itself.

CesiumJS comes from a CDN at a pinned version, so the page renders the same way
later; the version is written into the panel at runtime, and it appears in three
places at the top of `viewer/index.html` if it needs moving.
`check_viewer_contract.py` keeps the page and the build in step, but it is a static
check – it reads the source, it does not run the page.

## Swapping the input

The pipeline does not know where polygons come from. `config/*.json` names a
feature file and its fields:

```json
{ "features": "data/osm_garmisch.geojson", "features_epsg": 4326,
  "name_field": "name", "class_field": "piste:difficulty" }
```

Point it at hand-digitised outlines from orthoimagery, a survey layer, or another
feature class entirely – hiking trails, forest roads, avalanche paths, river beds.
Nothing above this line is about skiing.

## What is measured, and what is not

**Measured, and deterministic.** Slope statistics are taken over the surface
triangles, area-weighted: mean, median, 90th and 95th percentile. Elevation range,
vertical extent and surface area come from the DEM and the footprint. For a given
input dataset, DEM and processing configuration these numbers are reproducible to
the digit.

**Modelled, and labelled as such.** Where the source gives only a centreline, the
footprint comes from an explicit width model – typical groomed widths by grade and
a gentle taper, chosen from cartographic practice, *not* from survey. The model is
versioned (`ski_piste.width.v1`), its parameters are written into
`build-report.json`, and every footprint it produces is tagged
`source = "swept-from-centreline"` in the tileset. A mapped area always wins over a
swept one for the same run. The model produces a **candidate footprint**; it does
not claim to reconstruct the real piste edge.

**And it is measurably too narrow.** `experiments/width_model.py` compares the model
against the runs OpenStreetMap maps *twice* – once as a centreline, once as an area –
by casting a perpendicular at every station along the centreline that falls inside
the mapped area and clipping it to that area. Across the seven Garmisch runs with
enough overlap to compare, the model's width comes out at a median **0.54** of the
mapped width, and on the two runs with ~93% overlap it is off by nearly threefold.
The effect on what is published is much smaller – mean slope moves a median **+1.6°**,
p90 **+1.3°** – because a band of the wrong width on the same hillside is still on
that hillside.

The likely cause is a definition error rather than bad tuning: the model's parameters
are groomed-lane widths, while a mapped area traced from summer imagery is the cleared
corridor, which is the object this project actually claims to model. That is a
hypothesis, it is testable against DOP20 orthophotos, and the test has not been run.
The width table has deliberately **not** been refitted to these seven runs: they are a
small, self-selected sample, and fitting to them would spend the only independent
check available.

**No maximum slope is reported.** A maximum over DEM-derived triangle normals is not
a property of the mountain – it is whatever the noisiest triangle happens to be.

**The 90th percentile is not a located pitch.** It is the gradient below which 90% of
the surface *area* lies. Calling it "the steep section" would be wrong: it does not
identify where that terrain is. The viewer reports it as "steepest tenth" and does
not colour by it, for the same reason: a whole run painted by the gradient of its
steepest tenth tells the reader something about the run that is not true.

**The viewer's slope classes come from this dataset, not from a convention.** Mean
slope here runs from 9.6° to 26.4° with a median of 18.4°, so the classes break at
14°, 18° and 22°. An alpine 14/22/30 ramp, applied to the same numbers, puts fifteen
of twenty-one runs in one class and leaves the steepest class empty. Breaks chosen to
fit the variable are classification; changing which variable is drawn until the map
looks livelier is not, and this project did that once before noticing.

**The percentile depends on mesh resolution, the mean does not.**
`experiments/cell_size.py` measures this across four runs and an eightfold change in
cell size: the mean moves by at most 4.4%, the 90th percentile by at most 16.3%, always
downward as cells coarsen. The mean survives a change of mesh resolution; the percentile
does not, and is not comparable between datasets unless the cell size is quoted with it.
So the tessellation cell is not a chosen constant – it is derived as two DEM post
spacings, and both the value and the rule are written into `build-report.json`.

The earlier version of this paragraph said ~3% and ~7%. Those were measured on one run,
and the figures were not revised when the experiment grew to three. The script now
computes its own summary, so the two cannot drift apart again.

**Source DEM 1 m, processing grid 5 m.** DGM1 is a 1 m product; this prototype
resamples it to 5 m before measuring. Measurements are therefore 5 m measurements.

**Not measured – and this matters.** The pipeline reconstructs *the terrain under a
footprint*. It does not reconstruct the engineered piste: grooming, snow depth,
cut-and-fill, seasonal shaping and obstacles are all invisible to a summer DEM. A
narrow Skiweg bulldozed flat across a hillside will still measure as the hillside.
Read the numbers as terrain-derived measurements that *complement* the published
grade, never as a correction of it.

**DEM resolution is not accuracy.** Grid spacing says nothing about vertical
accuracy, and slope is a derivative – noisier than the heights it comes from.

**The rendered surface sits slightly above the measured one.** The surfaces are
draped on the DEM, but the terrain tileset is a coarser mesh sampled every 15 m,
and between its posts that mesh can rise above the DEM – on this build by up to
about 3 m. Wherever it did, the terrain poked through and the viewer showed ragged
holes. So each vertex is written at a height that clears whichever is higher, the
DEM or the terrain mesh, by a small margin: a median of 0.4 m, more only where it
is needed. This is presentation, it is recorded in the build report as such, and
no published measurement uses those heights – `Surface.vertices` keeps the draped
DEM heights and every number comes from them.

**The footprint is the permanent corridor, not the groomed extent.** These are two
different objects and the pipeline models only the first. The *permanent corridor* is
the cleared, cut-and-filled ground a run occupies: a forest cut, a graded shelf, a
retaining wall. It is visible in summer imagery and in the DEM, and it is the same
from one year to the next. The *groomed extent* is what a snowcat actually shaped on
a given day; it varies with snowfall, with the season and with the operator, and it
is not a property of the terrain at all.

This is also a consistency requirement, not only a definition. Every measurement here
is derived from DGM1, which is a snow-free product. A footprint traced from winter
imagery over a summer elevation model would put geometry and relief in different
states of the ground – snow fills hollows and rounds edges, and it does so exactly
where the slope percentiles are most sensitive. So the footprint is digitised from
snow-free sources, and winter imagery is useful here as a *check* on whether a
corridor is actually skied, never as the source of its outline.

**Slope along a line and slope over a surface are different numbers.** An earlier
prototype measured the descent gradient along OSM centrelines; this pipeline measures
the gradient of the surface. Both are correct and they do not agree, because one
follows a chosen path and the other describes the whole footprint.

## Licences

Code: MIT. Data: see [DATA-LICENSES.md](DATA-LICENSES.md) – inputs and outputs carry
different licences and they are listed per dataset.

## Repository shape

The core knows nothing about skiing. Everything domain-specific lives in one
profile file, which is the extension point.

```
pipeline/
  terrain.py      load a DEM, sample heights, derive gradients      generic
  surfaces.py     sweep, tessellate, drape, measure                 generic
  tiles3d.py      glTF 2.0 and 3D Tiles 1.1 writer                  generic
  overlays.py     source centrelines and contours, for reference    generic
  cli.py          orchestration: config in, out/ directory out
  fetch.py        download the full public inputs (see its caveat)
  profiles/
    ski_piste.py  the only file that knows about skiing: metadata
                  schema, width model, published property list

config/
  sample.json     self-contained; builds from committed data, no network
  garmisch.json   the full area; needs fetch.py first

data/
  sample/         a 2.2 x 2.6 km crop of DGM1, committed on purpose
  osm_garmisch.geojson   the OpenStreetMap piste extract

viewer/index.html        CesiumJS reference implementation, no account needed
serve.py                 local HTTP server, because file:// cannot load the tileset
start-windows.bat
start-mac-linux.command  double-click wrappers around serve.py

validate.py              reads the GLB back and checks the metadata round-trips
check_viewer_contract.py checks the viewer against the schema and against out/
benchmark.py             timings and sizes            → BENCHMARK.md
experiments/
  cell_size.py           how much the numbers move with mesh resolution
  width_model.py         the width model against independently mapped areas
```

Adding a feature class – hiking trails, forest roads, avalanche paths – means adding
one profile, not touching the core.

## Status, stated precisely

This is a proof of concept. What it demonstrates:

- a 3D Tiles 1.1 tileset whose content is glTF, carrying `EXT_mesh_features` and
  `EXT_structural_metadata`;
- `validate.py`, a project script that reads the GLB back, decodes the property
  table, checks index ranges and asserts the metadata round-trips. **It is a smoke
  test, not an independent conformance check** – the tileset has not yet been run
  through an external OGC validator;
- `check_viewer_contract.py`, which fails if the viewer asks for a property the
  schema does not publish, or fetches a file the pipeline does not write. Both
  halves exist because both failures happened here. A property was removed from the
  profile while the click panel kept asking for it, showing NaN with nothing in the
  build complaining. Later the viewer gained two overlay layers that nothing
  generated, which worked only because the author's `out/` already held them;
- one tileset per layer, each a single tile. There is **no tile hierarchy and no
  level of detail**. Both are on the list of things the grant would fund; neither
  is claimed to exist.
