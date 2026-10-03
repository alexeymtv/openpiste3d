"""Prototype performance characteristics: a record, not a scalability claim.

Builds both configurations into throwaway directories, times them, and writes
BENCHMARK.md. The scratch directories are removed afterwards so that running
this never changes what `out/` holds.
"""
import json, os, shutil, subprocess, sys, time

RUNS = [("sample", "config/sample.json"), ("garmisch", "config/garmisch.json")]
rows = []
for name, cfg in RUNS:
    out = f"out-bench-{name}"
    t0 = time.time()
    subprocess.run([sys.executable, "-m", "pipeline.cli", "--config", cfg, "--out", out],
                   check=True, stdout=subprocess.DEVNULL)
    wall = time.time() - t0
    r = json.load(open(f"{out}/build-report.json"))
    rows.append(dict(name=name, wall=wall, feats=r["featureCount"],
                     src=r["footprintSource"], cell=r["inputs"]["tessellationCellM"],
                     ptri=r["pistes"]["triangles"], pmb=r["pistes"]["bytes"] / 1e6,
                     ttri=r["terrain"]["triangles"], tmb=r["terrain"]["bytes"] / 1e6))

with open("BENCHMARK.md", "w") as fh:
    fh.write("# Prototype performance\n\nOne laptop-class container, single process, no GPU. "
             "These are characteristics of the prototype, not a claim about scale.\n\n")
    fh.write("| Build | Features | mapped / swept | Cell | Piste tri | Piste GLB | Terrain tri | Terrain GLB | Wall clock |\n")
    fh.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in rows:
        fh.write(f"| {r['name']} | {r['feats']} | {r['src']['polygon']} / {r['src']['line']} | "
                 f"{r['cell']:.0f} m | {r['ptri']:,} | {r['pmb']:.2f} MB | {r['ttri']:,} | "
                 f"{r['tmb']:.2f} MB | {r['wall']:.1f} s |\n")
    fh.write("\n`sample` builds from data committed to this repository and needs no network. "
             "`garmisch` needs the full DGM1 set fetched with `python -m pipeline.fetch`.\n")
    fh.write("\nThe terrain tileset dominates both size and time; it is a single tile with no "
             "level of detail, which is the first thing that would have to change for a larger area.\n")
for name, _ in RUNS:
    shutil.rmtree(f"out-bench-{name}", ignore_errors=True)

for r in rows:
    print(f"{r['name']:10s} {r['feats']:3d} feats  {r['ptri']:6d} tri  {r['wall']:5.1f} s")
print("wrote BENCHMARK.md")
