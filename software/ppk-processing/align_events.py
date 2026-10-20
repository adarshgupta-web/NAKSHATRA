#!/usr/bin/env python3
"""Turn STM32 logger events (local micros) into GPST camera-event times, then
interpolate the PPK trajectory at each event to produce an ODM geo.txt.

events.csv record types written by firmware/drone-logger:
  P,<pps_count>,<micros>            PPS rising edge
  T,<micros>,<gps_week>,<tow_ms>    UBX NAV-TIMEGPS received (1 Hz, follows its PPS)
  C,<cam_count>,<micros>            camera shutter / flash-sync edge

Assumption (verify on your receiver): each NAV-TIMEGPS describes the PPS edge that
immediately precedes it, so that edge's GPST second is round(tow_ms / 1000).
"""
import argparse
import bisect
import datetime as dt

GPS_EPOCH = dt.datetime(1980, 1, 6)
ROLL = 1 << 32


def unwrap(vals):
    out, add, prev = [], 0, None
    for v in vals:
        if prev is not None and v < prev - ROLL // 2:
            add += ROLL
        out.append(v + add)
        prev = v
    return out


def parse_events(lines):
    P, T, C = [], [], []
    for ln in lines:
        f = ln.strip().split(",")
        if f[0] == "P":
            P.append(int(f[2]))
        elif f[0] == "T":
            T.append((int(f[1]), int(f[2]), int(f[3])))
        elif f[0] == "C":
            C.append(int(f[2]))
    return P, T, C


def camera_gpst(lines, shutter_delay_s=0.0):
    """Return GPST datetimes for each camera event."""
    P, T, C = parse_events(lines)
    allm = unwrap(P + [t[0] for t in T] + C)
    P, Tm, C = allm[:len(P)], allm[len(P):len(P) + len(T)], allm[len(P) + len(T):]
    pps_gpst = {}
    for (_, wk, tow), tm in zip(T, Tm):
        k = bisect.bisect_right(P, tm) - 1          # PPS edge preceding this message
        if k >= 0:
            pps_gpst[k] = GPS_EPOCH + dt.timedelta(weeks=wk, seconds=round(tow / 1000))
    out = []
    for c in C:
        k = bisect.bisect_right(P, c) - 1
        if k in pps_gpst:
            out.append(pps_gpst[k] + dt.timedelta(seconds=(c - P[k]) / 1e6 - shutter_delay_s))
        else:
            out.append(None)
    return out


def parse_pos(lines):
    t, lat, lon, h = [], [], [], []
    for ln in lines:
        if not ln.strip() or ln.startswith("%"):
            continue
        c = ln.split()
        t.append(dt.datetime.strptime(f"{c[0]} {c[1]}", "%Y/%m/%d %H:%M:%S.%f"))
        lat.append(float(c[2])); lon.append(float(c[3])); h.append(float(c[4]))
    return t, lat, lon, h


def interp_at(pos, when):
    t, lat, lon, h = pos
    i = bisect.bisect_left(t, when)
    if i == 0 or i >= len(t):
        return None                                   # outside trajectory: do not extrapolate
    f = (when - t[i - 1]).total_seconds() / (t[i] - t[i - 1]).total_seconds()
    lerp = lambda a: a[i - 1] + f * (a[i] - a[i - 1])
    return lerp(lat), lerp(lon), lerp(h)


def write_geo(path, names, times, pos, antenna_to_camera_z=0.0):
    skipped = 0
    with open(path, "w") as out:
        out.write("EPSG:4326\n")
        for name, when in zip(names, times):
            r = interp_at(pos, when) if when else None
            if r is None:
                skipped += 1
                continue
            lat, lon, h = r
            out.write(f"{name} {lon:.9f} {lat:.9f} {h - antenna_to_camera_z:.4f}\n")
    return skipped


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True); ap.add_argument("--pos", required=True)
    ap.add_argument("--images", required=True, help="text file, one image name per line, shutter order")
    ap.add_argument("--out", default="geo.txt")
    ap.add_argument("--shutter-delay", type=float, default=0.0)
    ap.add_argument("--lever-z", type=float, default=0.0, help="antenna above camera, m")
    a = ap.parse_args()
    times = camera_gpst(open(a.events).readlines(), a.shutter_delay)
    names = [n.strip() for n in open(a.images) if n.strip()]
    if len(names) != len(times):
        print(f"WARNING: {len(names)} images vs {len(times)} camera events - check missed triggers")
    skipped = write_geo(a.out, names, times, parse_pos(open(a.pos).readlines()), a.lever_z)
    print(f"wrote {a.out} ({skipped} images skipped)")
