# AoE4 Housing + Idle Villager Monitor

A background Python script for Windows that watches your AoE4 HUD and alerts you with sound when your housing is full or you have idle villagers.

---

## Requirements

- Windows
- Python 3.8+
- The following packages:

```
pip install numpy pillow mss psutil
```

> `mss` is optional but strongly recommended — it's 5–10x faster than the Pillow fallback for screen capture. The script will tell you which backend is active on startup.

---

## Files

Place all of these in the same folder:

```
AOE4NoOverlayMSS.py     ← the script
fr_house.wav            ← housing warning sound
fr_housenow.wav         ← housing danger sound
fr_idle.wav             ← idle villager sound
```

`aoe4_calibration.json` and `aoe4_monitor_error.log` are created automatically.

---

## First-time setup

Run calibration **once per screen resolution**, while a game is running:

```
python AOE4NoOverlayMSS.py --calibrate
```

**Steps:**
1. Launch a game in AoE4
2. Get to a point where your pop cap is nearly full and you have at least 1 idle villager
3. Alt-Tab to the console, press Enter — then **quickly** switch back to the game
4. The script captures the screen and auto-detects the HUD regions
5. Check the two saved PNGs (`calibration_housing.png`, `calibration_villager.png`) to confirm they look right
6. Enter the idle villager count shown in your HUD when prompted, then save

Calibration is saved per resolution. If you change monitor or resolution, run it again.

---

## Normal usage

```
python AOE4NoOverlayMSS.py
```

The script runs in a console window. It waits for a match to start, then begins monitoring. Output looks like:

```
  Waiting for a match to start...
  [23:15:02] Match detected — monitoring started!
[23:15:33] *** HOUSING WARNING ***
[23:16:01] *** HOUSING DANGER – BUILD NOW! ***
[23:16:08] [OK]  Housing back to normal
[23:17:12] *** IDLE VILLAGERS (~3) – put them to work! ***
[23:17:18] [OK]  No idle villagers
```

Press **Ctrl+C** to stop. When the match ends it automatically waits for the next one.

---

## Configuration

Edit these values at the top of the script:

| Setting | Default | Description |
|---|---|---|
| `CHECK_INTERVAL` | `0.5` | Seconds between screen checks |
| `ALERT_COOLDOWN` | `25` | Seconds between repeated housing alerts |
| `ALERT_COOLDOWNVILLS` | `6` | Seconds between repeated villager alerts |
| `CONSECUTIVE_NEEDED` | `3` | Detections in a row before alerting (reduces false positives) |
| `ORANGE_THRESHOLD_PCT` | `0.4` | % of housing region that must be orange to trigger a warning |
| `RED_THRESHOLD_PCT` | `0.3` | % of housing region that must be red to trigger a danger alert |
| `BLUE_PIXEL_COUNT_MIN` | `10` | Min blue pixels in villager region to count as idle |

---

## How it works

**Match detection** — checks the bottom-left HUD panel. This region is solid black during a match and varies in the menus, so it reliably distinguishes in-game from everything else.

**Housing** — samples a region of the bottom-left HUD and counts red and orange pixels. Orange = warning (build soon), red = danger (build now).

**Idle villagers** — counts blue pixels in the idle villager icon area. Blue means the icon is active (villagers are idle).

**Sounds** — plays `.wav` files via `winsound`. All three sounds play asynchronously so they don't block the check loop.

---

## Troubleshooting

**"Waiting for a match to start..." never ends**
Run with `--debug` to see what the script is actually reading from your screen:
```
python AOE4NoOverlayMSS.py --debug
```
This prints raw values every second. Share the output if you need help diagnosing.

**Idle villager counts are way off**
Run `--calibrate` with at least 1 idle villager visible in your HUD. The calibration saves a pixels-per-villager ratio for your resolution.

**No sound**
Make sure `fr_house.wav`, `fr_housenow.wav`, and `fr_idle.wav` are in the same folder as the script.

**Script crashes on startup**
Check `aoe4_monitor_error.log` in the same folder for the full error.

**Housing alerts not triggering**
The default regions are estimates. Run `--calibrate` and check `calibration_housing.png` to confirm the script is looking at the right part of your screen.
