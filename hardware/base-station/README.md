# GNSS base station

A dual-band receiver on a permanent village control pillar, logging raw observations while the drone flies.
Firmware: [`firmware/base-station`](../../firmware/base-station). Target hardware cost about Rs 6,000 (design target).

## Why a pillar

The pillar is a reusable control point. Its coordinates are fixed once by a long static session against the
nearest CORS station (`software/ppk-processing/run_ppk.py`, step 1). Every later resurvey of the village reuses
those coordinates, so the datum stays consistent between surveys.

## Setup

1. Mount the antenna on the pillar with a ground plane, level, with a clear sky view above ~15 degrees.
2. Record the antenna height above the pillar mark and the antenna model.
3. Start logging **before** the drone takes off and stop **after** it lands.
4. For the one-time pillar coordinate: log at least 2 h, preferably more; then pull RINEX for the nearest CORS station covering the same period.

## Data to keep per session

`baseNNN.ubx` (raw), pillar ID, antenna height, date/time, weather note, operator.

## Known limits

CORS baselines can be tens of kilometres; whether integer ambiguities fix at that length depends on session length,
ionosphere and receiver quality. Check solution quality (Q flag, ratio, standard deviations) and verify against
independent checkpoints before trusting results.
