# Prototype performance

One laptop-class container, single process, no GPU. These are characteristics of the prototype, not a claim about scale.

| Build | Features | mapped / swept | Cell | Piste tri | Piste GLB | Terrain tri | Terrain GLB | Wall clock |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sample | 10 | 29 / 187 | 10 m | 15,182 | 0.46 MB | 102,312 | 2.47 MB | 6.2 s |
| garmisch | 21 | 29 / 187 | 10 m | 31,302 | 0.96 MB | 299,530 | 7.21 MB | 20.5 s |

`sample` builds from data committed to this repository and needs no network. `garmisch` needs the full DGM1 set fetched with `python -m pipeline.fetch`.

The terrain tileset dominates both size and time; it is a single tile with no level of detail, which is the first thing that would have to change for a larger area.
