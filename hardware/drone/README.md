# Drone platform

F450-class quadcopter carrying the survey payload.

| Item | Role | Notes |
|---|---|---|
| F450 frame, motors, ESCs, battery | airframe | size the battery for 15-20 min mapping legs |
| Flight controller | flight + waypoint missions | any controller that can fly grid missions and fire the camera |
| Mapping camera | imagery | global-shutter or fast rolling-shutter, fixed focus; trigger via flash-sync out |
| Dual-band GNSS receiver + antenna | raw L1/L2 (or L1/L5) observations | antenna on a ground plane, clear of the camera and video link |
| STM32 logger | time-sync logging | see [`hardware/stm32-logger`](../stm32-logger/README.md) |
| IMU | attitude | used for orientation priors; PPK handles position |
| Optional LiDAR | under-canopy ground returns | only where crop/trees hide bunds |

Target budget for the drone kit is about Rs 35,000 (a design target, not a measured cost).

## Mounting rules

- Keep the GNSS antenna as close to directly above the camera as practical and **measure the offset** (lever arm, metres).
- Keep the antenna away from the FPV transmitter and ESC wiring; interference degrades carrier-phase tracking.
- Rigidly fix camera, antenna and IMU relative to each other. Anything that flexes adds position error.
- Fly post-harvest, at a fixed altitude, with high forward/side overlap (typically 75-80 % / 65-70 %).
- Respect Drone Rules 2021 for the airspace zone and any permissions required.

## Pre-flight checklist

- [ ] Base station logging and antenna levelled over the pillar mark
- [ ] Drone GNSS has a 3D lock; logger shows PPS and a test camera event
- [ ] Camera clock/exposure fixed (no auto-ISO surprises), card empty
- [ ] Mission altitude, overlap and area loaded; return-to-home set
