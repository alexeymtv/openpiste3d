# The width model, measured against mapped areas

How wrong is the width model, and does it change the published numbers?

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

Source: `data/osm_garmisch.geojson` · DEM `data/dgm1/**/*.tif` at 5.0 m · tessellation cell 10 m · width model `ski_piste.width.v1` · stations every 20 m

**7 runs** cleared the overlap test (at least 10 stations and 25% of the centreline inside the mapped area); 12 did not.

## Result

| | median | range |
|---|---|---|
| model width / mapped width | 0.54 | 0.21 – 0.98 |
| mean slope, swept − mapped | +1.6° | -1.7° – +5.6° |
| p90 slope, swept − mapped | +1.3° | -2.1° – +8.0° |

Mean slope agrees within 2° on 4 of 7 runs.

## Per run

| run | grade | stations | coverage | mapped width (m) | model width (m) | model / mapped (p10–p90) | mean slope mapped → swept | p90 mapped → swept |
|---|---|---|---|---|---|---|---|---|
| Kandahar-Abfahrt | advanced | 287 | 93% | 62 | 22 | 0.36 (0.16–0.57) | 20.0° → 18.3° | 30.0° → 27.9° |
| Standard-Tonihütten Abfahrt | intermediate | 100 | 39% | 31 | 29 | 0.90 (0.59–1.91) | 17.2° → 19.7° | 27.9° → 34.2° |
| Horn-Abfahrt | advanced | 82 | 94% | 52 | 22 | 0.37 (0.27–0.79) | 18.6° → 19.3° | 25.5° → 25.9° |
| Osterfelder-Abfahrt | intermediate | 72 | 44% | 49 | 27 | 0.54 (0.27–1.02) | 18.4° → 20.0° | 27.4° → 29.6° |
| Olympia Abfahrt | intermediate | 23 | 36% | 123 | 26 | 0.21 (0.12–0.52) | 17.6° → 23.2° | 25.8° → 33.8° |
| Längenfelder Abfahrt I | intermediate | 22 | 92% | 33 | 29 | 0.86 (0.54–1.25) | 17.6° → 17.3° | 24.5° → 23.5° |
| Längenfelder Abfahrt II | intermediate | 13 | 57% | 30 | 29 | 0.98 (0.88–1.08) | 17.7° → 21.9° | 27.3° → 28.6° |

### Not compared

- **Aspen Run** – too little overlap between the two mappings
- **Brunntal** – too little overlap between the two mappings
- **Mittlerer Skiweg** – too little overlap between the two mappings
- **Oberes weißes Tal** – too little overlap between the two mappings
- **Panoramaabfahrt** – too little overlap between the two mappings
- **Sonnenkar** – too little overlap between the two mappings
- **Super-G** – too little overlap between the two mappings
- **Weißes Tal** – too little overlap between the two mappings
- **Weißes Tal Süd** – too little overlap between the two mappings
- **Wetterwandeck** – too little overlap between the two mappings
- **Wetterwandeck Ost** – too little overlap between the two mappings
- **Wetterwandeck West** – too little overlap between the two mappings

## What this looks like

The width model comes out about half the mapped width, and on the two runs
with near-total overlap – the ones whose numbers are least likely to be an
artefact of the comparison – it is off by a factor of roughly three. The
consequence for what the tileset publishes is much smaller: the median mean
slope moves by a degree or two, because a wider or narrower band on the same
hillside is still on that hillside.

There is a plausible reason for a *systematic* shortfall rather than scatter,
and it is a definition problem, not a tuning problem. The model's parameters
are typical **groomed widths** – the lane a snowcat shapes. An OpenStreetMap
area traced from summer orthoimagery is most likely the **cleared corridor** –
the forest cut and graded shelf, which is wider. Those are the two objects
distinguished in the README, and this project's stated object is the corridor.
If that reading is right, the model is not merely imprecise: it is
parameterised for the wrong one of the two.

That remains a hypothesis here. It is testable – trace a handful of corridors
directly from DOP20 orthophotos and compare all three – and the test has not
been run. Nothing in the pipeline has been retuned on the strength of it:
fitting the width table to seven non-random runs would be fitting noise, and
would destroy the independence that makes this comparison worth anything.

## Reading this honestly

A mapped area is not ground truth. It is one OpenStreetMap contributor's
tracing, usually from aerial imagery, with no stated accuracy. What this
measures is agreement between two independent constructions of the same run,
and disagreement does not say which one is wrong.

The sample is small and it is not random: a run is here only because somebody
chose to map it as an area as well as a line, and the runs that get that
treatment are the prominent ones. Read the numbers as an order of magnitude
for the model's error, not as a calibration of it.

Where both geometries exist the pipeline uses the mapped area – `prefer_mapped`
is on by default – and every swept footprint is labelled
`source = "swept-from-centreline"` in the tileset. This experiment measures
what that label costs when no mapped area is available, which is the normal
case: in this extract, most runs have only a centreline.
