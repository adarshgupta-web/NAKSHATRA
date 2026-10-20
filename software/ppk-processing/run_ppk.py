#!/usr/bin/env python3
"""Two-step PPK driver around RTKLIB (convbin + rnx2rtkp).

Step 1  pillar vs nearest CORS (static)   -> village pillar coordinates
Step 2  drone vs pillar (kinematic)       -> PPK drone trajectory (.pos)

  python run_ppk.py --pillar pillar.obs --cors cors.obs --nav brdc.nav \
         --drone drone.obs --cors-llh 19.0760 72.8777 15.0 --outdir out [--dry-run]

RINEX inputs are expected. To convert raw u-blox logs first:
  convbin -r ubx -v 3.04 -od -os -oi -ot -o drone.obs -n drone.nav drone.ubx
Not validated against real flight data yet; treat output as unverified until
checked against independent ground checkpoints.
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def parse_pos(text):
    """Parse an RTKLIB llh .pos file -> list of dicts."""
    rows = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("%"):
            continue
        c = line.split()
        rows.append({"time": f"{c[0]} {c[1]}", "lat": float(c[2]), "lon": float(c[3]),
                     "h": float(c[4]), "Q": int(c[5]), "ns": int(c[6]),
                     "sdn": float(c[7]), "sde": float(c[8]), "sdu": float(c[9])})
    return rows


def mean_fixed(rows):
    fx = [r for r in rows if r["Q"] == 1] or rows
    n = len(fx)
    return (sum(r["lat"] for r in fx) / n, sum(r["lon"] for r in fx) / n,
            sum(r["h"] for r in fx) / n)


def run(cmd, dry):
    print(" ".join(cmd))
    if not dry:
        subprocess.run(cmd, check=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("pillar", "cors", "nav", "drone"):
        ap.add_argument(f"--{k}", required=True)
    ap.add_argument("--cors-llh", nargs=3, type=float, required=True, metavar=("LAT", "LON", "H"))
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if not a.dry_run and not shutil.which("rnx2rtkp"):
        sys.exit("rnx2rtkp not found: install RTKLIB (e.g. RTKLIB-demo5) and add it to PATH")
    os.makedirs(a.outdir, exist_ok=True)

    pillar_pos = os.path.join(a.outdir, "pillar.pos")
    run(["rnx2rtkp", "-k", os.path.join(HERE, "static.conf"),
         "-l", *map(str, a.cors_llh), "-o", pillar_pos, a.pillar, a.cors, a.nav], a.dry_run)
    if a.dry_run:
        lat, lon, h = a.cors_llh  # placeholder so the second command can be printed
    else:
        lat, lon, h = mean_fixed(parse_pos(open(pillar_pos).read()))
        print(f"pillar: {lat:.9f} {lon:.9f} {h:.4f}")

    run(["rnx2rtkp", "-k", os.path.join(HERE, "ppk.conf"), "-l", str(lat), str(lon), str(h),
         "-o", os.path.join(a.outdir, "drone.pos"), a.drone, a.pillar, a.nav], a.dry_run)


if __name__ == "__main__":
    main()
