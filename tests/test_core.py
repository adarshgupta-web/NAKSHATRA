import datetime as dt
import json
import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("record-fusion", "boundary-intelligence", "gis", "sealed-baseline", "ppk-processing"):
    sys.path.insert(0, os.path.join(ROOT, "software", sub))
sys.path.insert(0, os.path.join(ROOT, "demo"))

import fusion, scoring, parcels, seal, align_events, run_ppk  # noqa: E402
from synthetic_village import build  # noqa: E402


def test_helmert_recovers_known_transform():
    rng = np.random.default_rng(0)
    src = rng.uniform(0, 100, (6, 2))
    th, s, t = 0.03, 1.002, np.array([5.0, -3.0])
    R = s * np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    dst = src @ R.T + t
    out = fusion.helmert_apply(fusion.helmert_fit(src, dst), src)
    assert np.abs(out - dst).max() < 1e-9


def test_fusion_reduces_error_and_reports_loocv():
    v = build()
    f, rep = fusion.fuse(v["gcp_src"], v["gcp_dst"])
    raw = np.linalg.norm(v["hist"] - v["truth"], axis=1)
    fused = np.linalg.norm(f(v["hist"]) - v["truth"], axis=1)
    assert fused.mean() < raw.mean() / 5
    assert all("rmse_loocv" in s for s in rep["stages"].values())


def test_intact_bund_is_high_and_missing_bund_is_not():
    v = build()
    resp = scoring.ridge_response(v["dsm"], v["cell"])
    t = v["truth"]
    results = {}
    for k, (a, b) in enumerate(v["edges"]):
        if k in v["decoy"]:
            continue
        r = scoring.score_edge(resp, v["origin"], v["cell"], t[a], t[b])   # perfect map -> isolates DSM evidence
        results.setdefault("faint" if k in v["faint"] else "intact", []).append(r["route"])
    assert results["intact"].count("HIGH") >= 0.8 * len(results["intact"])
    assert results["faint"].count("HIGH") == 0


def test_area_shoelace():
    assert abs(parcels.shoelace_area([(0, 0), (10, 0), (10, 5), (0, 5)]) - 50) < 1e-9


def test_seal_detects_tamper_and_chains():
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "a.txt"), "w").write("one")
        m1 = os.path.join(tempfile.gettempdir(), "t1.seal.json")
        m2 = os.path.join(tempfile.gettempdir(), "t2.seal.json")
        b1 = seal.seal(d, m1)
        assert seal.verify(d, m1) == []
        open(os.path.join(d, "a.txt"), "w").write("two")
        assert any("changed: a.txt" in p for p in seal.verify(d, m1))
        b2 = seal.seal(d, m2, parent=m1)
        assert b2["version"] == 2 and b2["parent_seal_hash"] == b1["seal_hash"]
        assert seal.compare(m1, m2)["changed"] == ["a.txt"]


def test_event_alignment_and_interpolation():
    # two PPS edges 1 s apart; camera fires 0.25 s after the first
    ev = ["P,1,1000000", "T,1000500,2400,100000", "P,2,2000000", "T,2000500,2400,101000",
          "C,1,1250000"]
    times = align_events.camera_gpst(ev)
    base = align_events.GPS_EPOCH + dt.timedelta(weeks=2400, seconds=100)
    assert abs((times[0] - (base + dt.timedelta(seconds=0.25))).total_seconds()) < 1e-6
    pos = ([base, base + dt.timedelta(seconds=1)], [19.0, 19.0001], [72.0, 72.0], [10.0, 12.0])
    lat, lon, h = align_events.interp_at(pos, times[0])
    assert abs(lat - 19.000025) < 1e-9 and abs(h - 10.5) < 1e-9


def test_micros_rollover_unwrapped():
    out = align_events.unwrap([4294967000, 100, 700])
    assert out[1] > out[0] and out[2] > out[1]


def test_pos_parser():
    txt = "% header\n2026/10/20 05:12:33.200   19.076000000   72.877700000    15.1000   1  12   0.01   0.01   0.02\n"
    r = run_ppk.parse_pos(txt)[0]
    assert r["Q"] == 1 and abs(r["lat"] - 19.076) < 1e-9
