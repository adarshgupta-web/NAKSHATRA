"""Multi-hypothesis boundary scoring.

For each parcel edge we start from the (fused) historical line and scan
perpendicular offsets in the DSM ridge-response map. Every ridge peak becomes a
hypothesis; the historical line itself (offset 0) is always kept. Each hypothesis
is scored on three kinds of evidence and routed by confidence. Nothing is
discarded: all hypotheses are returned for the officer / surveyor to inspect.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.signal import find_peaks

W = {"ridge": 0.55, "hist": 0.30, "feat": 0.15}
SIGMA_HIST = 2.5       # m, how far a boundary may sit from the fused map line
FEAT_RANGE = 8.0       # m, mapped road/hedge only counts when this close
MERGE_M = 1.0          # m, hypotheses closer than this are the same boundary
TEMP = 0.12            # softmax temperature on scores
P_HIGH, S_HIGH = 0.75, 0.55   # routing thresholds


def ridge_response(dsm, cell, blur_m=3.0, smooth_m=0.4, amp=0.2):
    """High-pass the DSM to isolate bunds, normalise to 0..1."""
    hp = dsm - gaussian_filter(dsm, blur_m / cell)
    hp = gaussian_filter(hp, smooth_m / cell)
    return np.clip(hp / amp, 0.0, 1.0)


def _unit_normal(p0, p1):
    d = np.asarray(p1, float) - np.asarray(p0, float)
    L = np.hypot(*d)
    return d / L, np.array([-d[1], d[0]]) / L, L


def offset_profile(resp, origin, cell, p0, p1, offsets, step=0.5, trim=3.0):
    t, n, L = _unit_normal(p0, p1)
    s = np.arange(trim, max(L - trim, trim + step), step)
    pts = np.asarray(p0, float)[None, :] + s[:, None] * t[None, :]
    prof = []
    for o in offsets:
        q = pts + o * n[None, :]
        rows = (q[:, 1] - origin[1]) / cell
        cols = (q[:, 0] - origin[0]) / cell
        prof.append(map_coordinates(resp, [rows, cols], order=1, mode="nearest").mean())
    return np.array(prof)


def _dist_to_polyline(pt, line):
    line = np.asarray(line, float)
    best = np.inf
    for a, b in zip(line[:-1], line[1:]):
        ab = b - a
        u = np.clip(np.dot(pt - a, ab) / np.dot(ab, ab), 0, 1)
        best = min(best, np.hypot(*(pt - (a + u * ab))))
    return best


def score_edge(resp, origin, cell, p0, p1, features=None, search=6.0, df=0.25):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    _, n, _ = _unit_normal(p0, p1)
    offsets = np.arange(-search, search + df / 2, df)
    prof = offset_profile(resp, origin, cell, p0, p1, offsets)
    # distance= merges near-duplicate peaks on a flat-topped bund into one hypothesis
    pk, _ = find_peaks(prof, height=0.12, prominence=0.08, distance=max(1, int(MERGE_M / df)))
    cand = sorted(float(offsets[i]) for i in pk)
    if not any(abs(o) < MERGE_M for o in cand):     # always keep the historical line itself
        cand = sorted(cand + [0.0])
    mid = (p0 + p1) / 2
    hyps = []
    for o in cand:
        ridge = float(np.interp(o, offsets, prof))
        hist = float(np.exp(-o ** 2 / (2 * SIGMA_HIST ** 2)))
        terms, weights = {"ridge": ridge, "hist": hist}, dict(W)
        feat = None
        if features:
            d = min(_dist_to_polyline(mid + o * n, f) for f in features)
            if d < FEAT_RANGE:
                feat = float(np.exp(-(d / 1.0) ** 2))
                terms["feat"] = feat
        if feat is None:
            weights.pop("feat")
        z = sum(weights.values())
        score = sum(weights[k] * terms[k] for k in terms) / z
        hyps.append({"offset": o, "ridge": ridge, "hist": hist, "feat": feat,
                     "score": score, "p0": (p0 + o * n).tolist(), "p1": (p1 + o * n).tolist()})
    sc = np.array([h["score"] for h in hyps])
    pr = np.exp((sc - sc.max()) / TEMP)
    pr /= pr.sum()
    for h, p in zip(hyps, pr):
        h["prob"] = float(p)
    hyps.sort(key=lambda h: -h["score"])
    top = hyps[0]
    route = "HIGH" if (top["prob"] >= P_HIGH and top["score"] >= S_HIGH) else "FIELD_CHECK"
    return {"hypotheses": hyps, "top_offset": top["offset"], "confidence": top["prob"],
            "top_score": top["score"], "route": route}
