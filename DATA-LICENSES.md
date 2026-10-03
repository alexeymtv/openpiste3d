# Data licences

Code and data are licensed separately. Every input and output is listed here with
its own terms; nothing in this repository is redistributed under a licence it did
not arrive with.

## Inputs

| Dataset | Source | Licence | Redistribution | Required attribution |
|---|---|---|---|---|
| DGM1 – digital terrain model, 1 m | Bayerische Vermessungsverwaltung, OpenData portal | CC BY 4.0 | Permitted, including commercially | `Bayerische Vermessungsverwaltung – www.geodaten.bayern.de` |
| DOP20 RGB – orthophoto, 20 cm | Bayerische Vermessungsverwaltung, OpenData portal | CC BY 4.0 | Permitted, including commercially | as above |
| Piste footprints and centrelines | OpenStreetMap contributors | ODbL 1.0 | Permitted, share-alike on derived databases | `© OpenStreetMap contributors` |

Attribution used for modified Bavarian data:
`Geobasisdaten: Bayerische Vermessungsverwaltung – www.geodaten.bayern.de (Daten verändert), Lizenz: CC BY 4.0`

## Outputs

| Output | Derived from | Licence | Why |
|---|---|---|---|
| `out/terrain.glb`, `out/terrain.json` | DGM1 only | CC BY 4.0 | A derivative of CC BY 4.0 source; attribution carried in the viewer and in this file. |
| `out/pistes.glb`, `out/pistes.json` **as built today** | OSM polygons + DGM1 | ODbL 1.0 | The footprints are extracted from the OSM database, so the result is a derived database and inherits ODbL. |
| Piste surfaces **digitised from DOP20** (planned) | DOP20 + DGM1 | CC BY 4.0 | Geometry drawn from orthoimagery does not derive from the OSM database, so ODbL does not attach. |
| Pipeline source code | – | MIT | Maximum reuse across the open geospatial ecosystem. |

## Two notes that are easy to get wrong

**The demo tileset is ODbL, the planned dataset is CC BY 4.0.** They differ because
their footprints come from different sources. Keeping the two builds separate – and
labelled – is deliberate.

**Bavarian orthophotos cannot currently be used for OpenStreetMap.** The OSM community
wiki states this plainly: the 2023 letter from the LDBV settles attribution but does
not waive the CC BY 4.0 clause that the OSM Foundation considers incompatible with
ODbL, and the requested addendum was still unanswered as of August 2026. Geometry
digitised from DOP20 therefore must not be uploaded to OSM. This project does not
upload anything to OSM.

Nothing here is legal advice.
