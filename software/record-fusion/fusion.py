"""Progressive historical-map fusion: Helmert -> Affine -> TPS.

Control points are pairs (historical-map coordinate, surveyed ground coordinate).
Because a thin-plate spline interpolates its control points exactly, fit residuals
say nothing about its real error. We therefore report leave-one-out (LOOCV)
residuals for every stage and keep the stage that predicts held-out points best.
Mismatching control points are flagged for review, never silently dropped.
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import RBFInterpolator


# ---- stage 1: Helmert (4-parameter similarity) -------------------------------
def helmert_fit(src, dst):
    """x' = a x - b y + tx ; y' = b x + a y + ty  ->  returns (a, b, tx, ty)."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    n = len(src)
    A = np.zeros((2 * n, 4))
    A[0::2] = np.c_[src[:, 0], -src[:, 1], np.ones(n), np.zeros(n)]
    A[1::2] = np.c_[src[:, 1], src[:, 0], np.zeros(n), np.ones(n)]
    l = np.empty(2 * n)
    l[0::2], l[1::2] = dst[:, 0], dst[:, 1]
    return np.linalg.lstsq(A, l, rcond=None)[0]


def helmert_apply(p, pts):
    a, b, tx, ty = p
    pts = np.asarray(pts, float)
    return np.c_[a * pts[:, 0] - b * pts[:, 1] + tx, b * pts[:, 0] + a * pts[:, 1] + ty]


# ---- stage 2: affine (6-parameter) -------------------------------------------
def affine_fit(src, dst):
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    X = np.c_[np.ones(len(src)), src]
    px = np.linalg.lstsq(X, dst[:, 0], rcond=None)[0]
    py = np.linalg.lstsq(X, dst[:, 1], rcond=None)[0]
    return np.vstack([px, py])  # 2x3


def affine_apply(P, pts):
    pts = np.asarray(pts, float)
    return np.c_[np.ones(len(pts)), pts] @ P.T


# ---- stage 3: thin-plate spline on the affine residuals -----------------------
def _make_helmert(src, dst):
    p = helmert_fit(src, dst)
    return lambda q: helmert_apply(p, q)


def _make_affine(src, dst):
    P = affine_fit(src, dst)
    return lambda q: affine_apply(P, q)


def _make_tps(src, dst, smoothing=1e-3):
    P = affine_fit(src, dst)
    a = affine_apply(P, src)
    rbf = RBFInterpolator(a, np.asarray(dst, float) - a,
                          kernel="thin_plate_spline", smoothing=smoothing)

    def f(q):
        aq = affine_apply(P, q)
        return aq + rbf(aq)

    return f


STAGES = {"helmert": _make_helmert, "affine": _make_affine, "tps": _make_tps}
MIN_POINTS = {"helmert": 2, "affine": 3, "tps": 6}


def loocv_residuals(make, src, dst):
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    out = np.zeros(len(src))
    for i in range(len(src)):
        keep = np.arange(len(src)) != i
        f = make(src[keep], dst[keep])
        out[i] = np.linalg.norm(f(src[i:i + 1])[0] - dst[i])
    return out


def _rmse(x):
    return float(np.sqrt(np.mean(np.square(x))))


def fuse(src, dst, flag_k=3.5):
    """Fit all feasible stages; return (transform, report)."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    n = len(src)
    if n < 4:
        raise ValueError("need at least 4 control points")
    report = {"n_control": n, "stages": {}}
    best, best_cv = None, np.inf
    for name, make in STAGES.items():
        if n < MIN_POINTS[name] + 1:
            continue
        f = make(src, dst)
        fit_res = np.linalg.norm(f(src) - dst, axis=1)
        cv = loocv_residuals(make, src, dst)
        report["stages"][name] = {"rmse_fit": _rmse(fit_res), "rmse_loocv": _rmse(cv)}
        # require a >10 % LOOCV gain before accepting a more flexible model
        if _rmse(cv) < best_cv * (0.9 if best else 1.0):
            best, best_cv, best_cv_res = name, _rmse(cv), cv
    report["selected"] = best
    med = np.median(best_cv_res)
    mad = 1.4826 * np.median(np.abs(best_cv_res - med)) + 1e-9
    flagged = np.where(best_cv_res > med + flag_k * mad)[0]
    report["loocv_residuals"] = best_cv_res.tolist()
    report["flagged_control_points"] = flagged.tolist()
    return STAGES[best](src, dst), report
