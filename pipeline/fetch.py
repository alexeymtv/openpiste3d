"""Fetch the full public inputs for a configuration.

The repository ships a small sample that builds with no network at all
(`config/sample.json`). This script gets the full Garmisch inputs instead: the
DGM1 tiles from the Bavarian open-data portal and an Overpass extract of the
piste layer.

    python -m pipeline.fetch --config config/garmisch.json

Both sources are open data. Their licences and the required attribution are in
DATA-LICENSES.md; this script does not restate them, it just records what it
downloaded so a build report can point at it.

Run it with `--check` first. That asks both hosts whether the addresses resolve
and answer, downloads nothing, and takes a few seconds:

    python -m pipeline.fetch --config config/garmisch.json --check

NOTE: the downloading path has not been executed by its author – the environment
it was written in has no route to either host. It is written defensively: it
verifies sizes, records SHA-256 of everything it writes, and refuses to overwrite
a file that already exists. Treat the first real run as a test and report what
breaks.
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.request

UA = "OpenPiste3D/0.1 (open geospatial research; contact via repository)"

# Bavarian DGM1 is delivered per 1 km tile, named <easting_km>_<northing_km>.tif
DGM1_TILE = "https://download1.bayernwolke.de/a/dgm1/dgm1_{e}_{n}.tif"

OVERPASS = "https://overpass-api.de/api/interpreter"
OVERPASS_QUERY = """[out:json][timeout:180];
(
  way["piste:type"="downhill"]({s},{w},{n},{e});
  relation["piste:type"="downhill"]({s},{w},{n},{e});
  way["aerialway"]({s},{w},{n},{e});
  node["aerialway"="station"]({s},{w},{n},{e});
);
out geom;"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get(url, dest, data=None):
    if os.path.exists(dest):
        print(f"  have {os.path.basename(dest)}")
        return False
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    tmp = dest + ".part"
    with urllib.request.urlopen(req, timeout=180) as r, open(tmp, "wb") as fh:
        fh.write(r.read())
    if os.path.getsize(tmp) < 1024:
        os.remove(tmp)
        raise IOError(f"suspiciously small response from {url}")
    os.replace(tmp, dest)
    print(f"  got  {os.path.basename(dest)}  {os.path.getsize(dest)//1024} KB")
    return True


def head(url, data=None):
    """Ask whether a URL answers, without downloading it. Returns a status line."""
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    if data is None:
        req.get_method = lambda: "HEAD"
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            size = r.headers.get("Content-Length")
            return f"{r.status} {r.reason}" + (f", {int(size)//1024} KB" if size else "")
    except Exception as exc:                        # noqa: BLE001
        return f"FAILED – {type(exc).__name__}: {exc}"


def check(cfg, tiles, bbox):
    """Dry run: do the addresses this script uses actually answer?"""
    (e0, e1), (n0, n1) = [tuple(int(v) for v in part.split("-")) for part in tiles.split(",")]
    probes = [DGM1_TILE.format(e=e0, n=n0), DGM1_TILE.format(e=e1, n=n1)]
    print("· DGM1 tile URLs")
    ok = True
    for url in probes:
        status = head(url)
        ok = ok and status.startswith("200")
        print(f"  {status:28s} {url}")

    print("· Overpass")
    s, w, n, e = bbox.split(",")
    import urllib.parse
    q = "[out:json][timeout:25];way[\"piste:type\"=\"downhill\"]" \
        f"({s},{w},{n},{e});out count;"
    status = head(OVERPASS, data=urllib.parse.urlencode({"data": q}).encode())
    ok = ok and status.startswith("200")
    print(f"  {status:28s} {OVERPASS}")

    print()
    if ok:
        print("Both hosts answer. A real run should work; nothing was downloaded.")
    else:
        print("Something did not answer. Fix the URL above before the real run –")
        print("the tile naming on the Bavarian portal is the usual culprit.")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--check", action="store_true",
                    help="only test that the addresses answer; download nothing")
    ap.add_argument("--tiles", default="655-657,5257-5260",
                    help="UTM32 km ranges: <e0>-<e1>,<n0>-<n1>")
    ap.add_argument("--bbox", default="47.42,11.05,47.50,11.16",
                    help="south,west,north,east for the Overpass extract")
    args = ap.parse_args(argv)

    with open(args.config) as fh:
        cfg = json.load(fh)

    if args.check:
        return check(cfg, args.tiles, args.bbox)

    dem_dir = os.path.dirname(cfg["dem_glob"].replace("**/", "").replace("*.tif", "")) or "data/dem"
    (e0, e1), (n0, n1) = [tuple(int(v) for v in part.split("-"))
                          for part in args.tiles.split(",")]
    print(f"· DGM1 tiles {e0}-{e1} x {n0}-{n1} → {dem_dir}")
    written = []
    for e in range(e0, e1 + 1):
        for n in range(n0, n1 + 1):
            dest = os.path.join(dem_dir, f"{e}_{n}.tif")
            try:
                get(DGM1_TILE.format(e=e, n=n), dest)
                written.append(dest)
            except Exception as exc:
                print(f"  !! {e}_{n}: {exc}")

    print(f"· Overpass extract → {cfg['features']}")
    s, w, n, e = args.bbox.split(",")
    q = OVERPASS_QUERY.format(s=s, w=w, n=n, e=e).encode()
    try:
        import urllib.parse
        get(OVERPASS, cfg["features"], data=urllib.parse.urlencode({"data": q}).encode())
        written.append(cfg["features"])
    except Exception as exc:
        print(f"  !! overpass: {exc}")

    manifest = {p: sha256(p) for p in written if os.path.exists(p)}
    with open("data/FETCHED.json", "w") as fh:
        json.dump({"tiles": args.tiles, "bbox": args.bbox, "sha256": manifest}, fh, indent=2)
    print(f"· recorded {len(manifest)} files in data/FETCHED.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
