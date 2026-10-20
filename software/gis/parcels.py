"""Parcel geometry, area comparison against recorded area, GeoJSON export."""
from __future__ import annotations

import json
import numpy as np


def shoelace_area(ring):
    r = np.asarray(ring, float)
    x, y = r[:, 0], r[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def perimeter(ring):
    r = np.asarray(ring, float)
    return float(np.sum(np.hypot(*(np.roll(r, -1, axis=0) - r).T)))


def parcel_table(parcels, record_area=None):
    """parcels: {id: ring}. record_area: {id: m2 from 7/12 or historical map}."""
    rows = []
    for pid, ring in parcels.items():
        a = shoelace_area(ring)
        row = {"id": pid, "area_m2": a, "perimeter_m": perimeter(ring)}
        if record_area and pid in record_area:
            row["record_area_m2"] = record_area[pid]
            row["area_delta_pct"] = 100 * (a - record_area[pid]) / record_area[pid]
        rows.append(row)
    return rows


def to_geojson(parcels, table, crs="EPSG:32643", path=None):
    """Export rings as a GeoJSON FeatureCollection (coordinates in `crs`).
    `ulpin` is left null: ULPIN is assigned by the land-records authority."""
    by_id = {r["id"]: r for r in table}
    feats = []
    for pid, ring in parcels.items():
        ring = [list(map(float, p)) for p in ring]
        ring.append(ring[0])
        feats.append({"type": "Feature", "properties": {**by_id[pid], "ulpin": None},
                      "geometry": {"type": "Polygon", "coordinates": [ring]}})
    fc = {"type": "FeatureCollection",
          "crs": {"type": "name", "properties": {"name": crs}}, "features": feats}
    if path:
        with open(path, "w") as f:
            json.dump(fc, f, indent=1)
    return fc
