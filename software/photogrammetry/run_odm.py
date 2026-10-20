#!/usr/bin/env python3
"""Run OpenDroneMap (Docker) on a PPK-geotagged project.

Expected layout:  <project>/images/*.jpg  and  <project>/geo.txt  (from align_events.py)
Outputs (ODM defaults): odm_orthophoto/odm_orthophoto.tif, odm_dem/dsm.tif, odm_dem/dtm.tif
"""
import argparse
import os
import subprocess


def build_cmd(project, gps_accuracy, ortho_cm, dem_cm):
    project = os.path.abspath(project)
    parent, name = os.path.split(project)
    return ["docker", "run", "--rm", "-v", f"{parent}:/datasets", "opendronemap/odm",
            "--project-path", "/datasets", name,
            "--geo", f"/datasets/{name}/geo.txt",
            "--gps-accuracy", str(gps_accuracy),
            "--dsm", "--dtm",
            "--orthophoto-resolution", str(ortho_cm),
            "--dem-resolution", str(dem_cm)]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--gps-accuracy", type=float, default=0.1, help="m; tune to your PPK quality")
    ap.add_argument("--ortho-cm", type=float, default=3.0)
    ap.add_argument("--dem-cm", type=float, default=5.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cmd = build_cmd(a.project, a.gps_accuracy, a.ortho_cm, a.dem_cm)
    print(" ".join(cmd))
    if not a.dry_run:
        subprocess.run(cmd, check=True)
