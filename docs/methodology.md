# Methodology

## 1. Time-synchronised PPK

The drone receiver and the village-pillar receiver log raw dual-frequency observations. The pillar is first tied to
the nearest CORS station with a static baseline (long session). The drone is then processed kinematically against the
pillar (RTKLIB `rnx2rtkp`, configs in `software/ppk-processing`). Solution quality (Q flag, ambiguity ratio, standard
deviations) is kept per epoch and should be reviewed before use.

**Camera positions.** The STM32 logs PPS edges and camera events on one microsecond counter. Each NAV-TIMEGPS message
labels the preceding PPS edge with a GPST second, so a camera event at local time `c` gets
`GPST = GPST(PPS_k) + (c - t_k)`. Position is linearly interpolated between PPK epochs; events outside the trajectory
are skipped rather than extrapolated. The antenna-to-camera lever arm and shutter delay are explicit parameters.

## 2. Historical record fusion

Control points are pairs (historical-map coordinate `s`, surveyed ground coordinate `g`). Three stages are fitted:

1. **Helmert** (4 parameters: scale, rotation, 2 shifts): `x' = a x - b y + tx`, `y' = b x + a y + ty`.
2. **Affine** (6 parameters): captures anisotropic scale and shear from paper shrinkage.
3. **Thin-plate spline** on affine residuals: absorbs smooth local distortion.

A TPS passes exactly through its control points, so fit residuals are meaningless for it. Each stage is therefore
scored by **leave-one-out cross-validation**: refit without point *i*, predict *i*, record the error. The more flexible
stage is accepted only if LOOCV RMSE improves by more than 10 %. Control points whose LOOCV residual exceeds
`median + 3.5 x 1.4826 x MAD` are flagged for review.

## 3. Multi-hypothesis boundary scoring

For each edge, the fused historical line is the starting point. A DSM high-pass (`DSM - gaussian(DSM, 3 m)`, lightly
smoothed, normalised to 0..1) isolates bunds. The mean ridge response along the edge is evaluated at perpendicular
offsets in [-6 m, +6 m]; each peak becomes a hypothesis (peaks within 1 m merge), and the unshifted historical line is
always kept. Each hypothesis `h` gets

```
score(h) = ( 0.55 ridge + 0.30 hist + 0.15 feat ) / sum of weights present
hist(h)  = exp(-offset^2 / (2 * 2.5^2))
feat(h)  = exp(-d^2)  when a mapped road/hedge lies within 8 m, else the term is dropped
prob(h)  = softmax(score / 0.12) over the edge's hypotheses
```

Weights, the 2.5 m prior and the temperature are **initial engineering guesses**, not calibrated values.
Calibrate them on real surveyed villages with independent ground truth before relying on the routing.

## 4. Sealed baseline

All survey files are hashed with SHA-256 into a manifest with version, UTC time and metadata; the manifest hash is
stored in the manifest, and a new version records its parent's hash, forming a chain. `verify` detects added,
removed or modified files. This proves **integrity**; proving **who** sealed it needs a digital signature on top.

## 5. Validation plan (not yet done)

| What | How | Report |
|---|---|---|
| PPK position accuracy | independent RTK-rover checkpoints on visible targets across the site | RMSE E/N/U, fix rate |
| Orthomosaic accuracy | same checkpoints in the orthomosaic | RMSE, 95th percentile |
| Fusion error | withheld control points | LOOCV and holdout RMSE |
| Boundary routing | compare auto-ranked boundaries with officer-verified ones | precision/recall of HIGH, share routed to field |
| Event timing | bench test with a pulse generator on PPS and camera inputs | latency and jitter |

Until these are measured, all accuracy figures describe design targets only.

## 6. Limits

- Crops, trees and shadows hide bunds; capture post-harvest and use the DSM, or LiDAR where needed.
- Long CORS baselines may not fix ambiguities; independent checks are mandatory.
- Disputed or encroached boundaries cannot be resolved from imagery; they go to officers and field work.
- The demo uses synthetic data; its numbers show the code works, not how accurate the system is in the field.
