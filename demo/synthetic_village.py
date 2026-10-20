"""Synthetic village for exercising the NAKSHATRA pipeline without field data.

Local metric frame (metres). 3x3 parcels on a jittered 4x4 vertex grid.
  truth      : the real boundaries
  historical : an old map of the same vertices - rotated/scaled/shifted + smooth warp + noise
  GCPs       : 8 vertices surveyed on the ground (0.05 m GNSS noise)
  DSM        : bunds as 0.3 m ridges; some faint (ploughed out), some with a decoy ridge
"""
import numpy as np

NX, NY, DX, DY = 3, 3, 80.0, 60.0
CELL = 0.25
ORIGIN = (-10.0, -10.0)


def _seg_dist(X, Y, a, b):
    ab = b - a
    t = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1]) / (ab @ ab), 0, 1)
    return np.hypot(X - (a[0] + t * ab[0]), Y - (a[1] + t * ab[1]))


def build(seed=7):
    rng = np.random.default_rng(seed)
    idx = lambda i, j: j * (NX + 1) + i
    truth = np.array([[i * DX, j * DY] for j in range(NY + 1) for i in range(NX + 1)])
    for j in range(1, NY):
        for i in range(1, NX):
            truth[idx(i, j)] += rng.uniform(-3, 3, 2)
    edges = [(idx(i, j), idx(i + 1, j)) for j in range(NY + 1) for i in range(NX)]
    edges += [(idx(i, j), idx(i, j + 1)) for j in range(NY) for i in range(NX + 1)]
    parcels = {f"P{j * NX + i + 1:02d}": [idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1)]
               for j in range(NY) for i in range(NX)}

    # historical map = distorted copy of truth
    th, s = np.deg2rad(1.2), 1.0015
    R = s * np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    hist = truth @ R.T + np.array([14.0, -9.0])
    hist += np.c_[2.0 * np.sin(2 * np.pi * truth[:, 1] / 300), 1.5 * np.cos(2 * np.pi * truth[:, 0] / 400)]
    hist += rng.normal(0, 0.6, hist.shape)

    gcp_ids = [0, 3, 5, 6, 9, 10, 12, 15]
    gcp_src = hist[gcp_ids]
    gcp_dst = truth[gcp_ids] + rng.normal(0, 0.05, (len(gcp_ids), 2))

    # DSM
    cols = int((NX * DX + 20) / CELL)
    rows = int((NY * DY + 20) / CELL)
    X, Y = np.meshgrid(ORIGIN[0] + (np.arange(cols) + .5) * CELL, ORIGIN[1] + (np.arange(rows) + .5) * CELL)
    dsm = 0.5 * X / (NX * DX) + rng.normal(0, 0.04, X.shape)      # gentle slope + noise
    faint = set(rng.choice(len(edges), 7, replace=False).tolist())
    decoy = set(rng.choice([e for e in range(len(edges)) if e not in faint], 3, replace=False).tolist())
    amp = {}
    for k, (a, b) in enumerate(edges):
        amp[k] = 0.06 if k in faint else 0.30
        d = _seg_dist(X, Y, truth[a], truth[b])
        dsm += amp[k] * np.exp(-d ** 2 / (2 * 0.25 ** 2))
        if k in decoy:                                             # parallel old bund / channel bank
            t = (truth[b] - truth[a]) / np.hypot(*(truth[b] - truth[a]))
            n = np.array([-t[1], t[0]])
            d2 = _seg_dist(X, Y, truth[a] + 3.5 * n, truth[b] + 3.5 * n)
            dsm += 0.26 * np.exp(-d2 ** 2 / (2 * 0.25 ** 2))
    road = [truth[idx(i, 0)] for i in range(NX + 1)]               # mapped road along the south side
    return {"truth": truth, "hist": hist, "edges": edges, "parcels": parcels, "gcp_ids": gcp_ids,
            "gcp_src": gcp_src, "gcp_dst": gcp_dst, "dsm": dsm, "origin": ORIGIN, "cell": CELL,
            "faint": faint, "decoy": decoy, "road": [np.array(road)]}
