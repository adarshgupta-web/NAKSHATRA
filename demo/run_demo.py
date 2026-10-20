#!/usr/bin/env python3
"""End-to-end NAKSHATRA demo on synthetic data (no hardware, no field data).

  record fusion -> ridge extraction -> multi-hypothesis scoring -> confidence routing
  -> parcel areas -> sealed baseline -> figures + data for the web console / field app
Run:  python demo/run_demo.py
"""
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("record-fusion", "boundary-intelligence", "gis", "sealed-baseline"):
    sys.path.insert(0, os.path.join(ROOT, "software", sub))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fusion, scoring, parcels, seal           # noqa: E402
from synthetic_village import build             # noqa: E402

OUT = os.path.join(ROOT, "demo", "output")
IMG = os.path.join(ROOT, "assets", "demo")
os.makedirs(OUT, exist_ok=True); os.makedirs(IMG, exist_ok=True)
GREEN, AMBER, GREY = "#1a9850", "#e08214", "#777777"


def main():
    v = build()
    truth, hist, edges = v["truth"], v["hist"], v["edges"]

    # 1 -- historical record fusion
    f, rep = fusion.fuse(v["gcp_src"], v["gcp_dst"])
    fused = f(hist)
    err = np.linalg.norm(fused - truth, axis=1)
    err_raw = np.linalg.norm(hist - truth, axis=1)
    print(f"[fusion] selected={rep['selected']}  vertex error vs truth: raw RMS {np.sqrt((err_raw**2).mean()):.2f} m "
          f"-> fused RMS {np.sqrt((err**2).mean()):.2f} m (max {err.max():.2f} m)")
    for k, s in rep["stages"].items():
        print(f"         {k:8s} fit RMSE {s['rmse_fit']:.3f}  LOOCV RMSE {s['rmse_loocv']:.3f}")

    # 2 -- boundary hypotheses per edge
    resp = scoring.ridge_response(v["dsm"], v["cell"])
    results = []
    for k, (a, b) in enumerate(edges):
        r = scoring.score_edge(resp, v["origin"], v["cell"], fused[a], fused[b], features=v["road"])
        t = (fused[b] - fused[a]) / np.hypot(*(fused[b] - fused[a]))
        n = np.array([-t[1], t[0]])
        true_off = float(np.mean([(truth[a] - fused[a]) @ n, (truth[b] - fused[b]) @ n]))
        r.update(edge=k, a=int(a), b=int(b), true_offset=true_off,
                 correct=abs(r["top_offset"] - true_off) < 0.5, faint=k in v["faint"], decoy=k in v["decoy"])
        results.append(r)
    hi = [r for r in results if r["route"] == "HIGH"]
    lo = [r for r in results if r["route"] != "HIGH"]
    acc = lambda rs: (100 * np.mean([r["correct"] for r in rs])) if rs else float("nan")
    print(f"[boundary] {len(results)} edges: HIGH {len(hi)} (top hypothesis within 0.5 m of truth: {acc(hi):.0f}%), "
          f"FIELD_CHECK {len(lo)} (top hypothesis correct: {acc(lo):.0f}%)")

    # 3 -- parcels from the chosen boundary lines
    off = {(r["a"], r["b"]): r["top_offset"] for r in results}
    ring = {}
    pts_final = fused.copy()
    for pid, vs in v["parcels"].items():
        ring[pid] = [pts_final[i] for i in vs]
    rec_area = {pid: parcels.shoelace_area([hist[i] for i in vs]) for pid, vs in v["parcels"].items()}
    table = parcels.parcel_table(ring, rec_area)
    parcels.to_geojson(ring, table, path=os.path.join(OUT, "parcels.geojson"))

    # 4 -- sealed baseline over the outputs
    json.dump({"fusion": rep, "edges": [{k: r[k] for k in ("edge", "route", "confidence", "top_offset")} for r in results]},
              open(os.path.join(OUT, "analysis.json"), "w"), indent=1)
    sealpath = os.path.join(ROOT, "demo", "baseline.seal.json")
    b = seal.seal(OUT, sealpath, meta={"village": "synthetic", "ps": "26010", "note": "demo data"})
    print(f"[seal] v{b['version']} {b['seal_hash'][:16]}...  verify -> {seal.verify(OUT, sealpath) or 'intact'}")

    # 5 -- figures
    X0, Y0 = v["origin"]
    ext = [X0, X0 + v["dsm"].shape[1] * v["cell"], Y0, Y0 + v["dsm"].shape[0] * v["cell"]]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    ax[0].imshow(v["dsm"], origin="lower", extent=ext, cmap="terrain"); ax[0].set_title("Synthetic DSM (bunds are 0.3 m ridges)")
    ax[1].imshow(resp, origin="lower", extent=ext, cmap="magma"); ax[1].set_title("Ridge response (DSM high-pass)")
    for a_ in ax: a_.set_xlabel("E (m)"); a_.set_ylabel("N (m)")
    fig.tight_layout(); fig.savefig(os.path.join(IMG, "01_dsm_ridges.png"), dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 6))
    for a, b in edges:
        ax.plot(*zip(truth[a], truth[b]), color="black", lw=2.2, alpha=.35)
        ax.plot(*zip(hist[a], hist[b]), color="#d73027", lw=1, ls="--")
        ax.plot(*zip(fused[a], fused[b]), color="#1a9850", lw=1.4)
    ax.scatter(*v["gcp_dst"].T, c="blue", s=45, zorder=5, label="ground control points")
    ax.plot([], [], "k", lw=2.2, alpha=.35, label="truth"); ax.plot([], [], "#d73027", ls="--", label="historical map (raw)")
    ax.plot([], [], "#1a9850", label=f"fused ({rep['selected']})")
    ax.set_aspect("equal"); ax.legend(loc="upper left", fontsize=8)
    ax.set_title(f"Historical record fusion: vertex RMS {np.sqrt((err_raw**2).mean()):.1f} m -> {np.sqrt((err**2).mean()):.2f} m")
    fig.tight_layout(); fig.savefig(os.path.join(IMG, "02_historical_fusion.png"), dpi=130); plt.close(fig)

    def draw_conf(ax):
        for r in results:
            a, b = r["a"], r["b"]
            col = GREEN if r["route"] == "HIGH" else AMBER
            ax.plot(*zip(fused[a], fused[b]), color=GREY, lw=.8, ls=":")
            h0 = r["hypotheses"][0]
            ax.plot(*zip(h0["p0"], h0["p1"]), color=col, lw=3)
            for h in r["hypotheses"][1:]:
                if h["prob"] > 0.05:
                    ax.plot(*zip(h["p0"], h["p1"]), color=AMBER, lw=1, ls="--")
        ax.set_aspect("equal")
    fig, ax = plt.subplots(figsize=(7.5, 6)); draw_conf(ax)
    ax.plot([], [], color=GREEN, lw=3, label=f"high confidence ({len(hi)})")
    ax.plot([], [], color=AMBER, lw=3, label=f"needs field check ({len(lo)})")
    ax.plot([], [], color=AMBER, lw=1, ls="--", label="alternative hypotheses")
    ax.legend(loc="upper left", fontsize=8); ax.set_title("Boundary hypotheses and confidence routing")
    fig.tight_layout(); fig.savefig(os.path.join(IMG, "03_boundary_confidence.png"), dpi=130); plt.close(fig)

    # dashboard-style overview
    fig = plt.figure(figsize=(12, 5.2))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.25, 1]); ax = fig.add_subplot(gs[0]); draw_conf(ax)
    for pid, rg in ring.items():
        c = np.mean(rg, axis=0); ax.text(*c, pid, ha="center", fontsize=8, color="#333")
    ax.set_title("Officer review - village overview"); ax2 = fig.add_subplot(gs[1]); ax2.axis("off")
    q = sorted(lo, key=lambda r: r["confidence"])[:9]
    rows_ = [[f"E{r['edge']:02d}", f"{r['confidence']:.2f}", f"{len(r['hypotheses'])}", "field check"] for r in q]
    tb = ax2.table(cellText=rows_, colLabels=["edge", "confidence", "hyps", "action"], loc="upper center", cellLoc="center")
    tb.auto_set_font_size(False); tb.set_fontsize(9); tb.scale(1, 1.5)
    ax2.set_title(f"Review queue (lowest confidence first)\n{len(hi)} edges auto-ready for accept, {len(lo)} to verify", fontsize=10)
    fig.tight_layout(); fig.savefig(os.path.join(ROOT, "assets", "dashboard", "console_overview.png"), dpi=130); plt.close(fig)

    # 6 -- data for web console and field app (plain JS so they work offline from file://)
    P = lambda p: [round(float(x), 2) for x in p]
    data = {"summary": {"edges": len(results), "high": len(hi), "field": len(lo), "synthetic": True},
            "parcels": [{"id": r["id"], "area": round(r["area_m2"], 1), "record": round(r["record_area_m2"], 1),
                         "delta": round(r["area_delta_pct"], 2), "ring": [P(p) for p in ring[r["id"]]]} for r in table],
            "edges": [{"id": f"E{r['edge']:02d}", "route": r["route"], "confidence": round(r["confidence"], 3),
                       "hyps": [{"offset": round(h["offset"], 2), "score": round(h["score"], 3), "prob": round(h["prob"], 3),
                                 "p0": P(h["p0"]), "p1": P(h["p1"])} for h in r["hypotheses"]]} for r in results]}
    open(os.path.join(ROOT, "web-console", "console_data.js"), "w").write("window.NAKSHATRA_DATA = " + json.dumps(data) + ";\n")
    tasks = [{"edge": f"E{r['edge']:02d}", "confidence": round(r["confidence"], 3),
              "where_m": P((np.array(r["hypotheses"][0]["p0"]) + np.array(r["hypotheses"][0]["p1"])) / 2)} for r in lo]
    open(os.path.join(ROOT, "field-app", "tasks.js"), "w").write("window.FIELD_TASKS = " + json.dumps(tasks) + ";\n")
    print("figures -> assets/demo, assets/dashboard ; console_data.js, tasks.js written")


if __name__ == "__main__":
    main()
