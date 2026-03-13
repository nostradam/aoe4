# AoE4 Housing & Idle Villager Monitor

A lightweight Windows overlay that watches your Age of Empires IV HUD in real time and alerts you with sound and a visual flash when your housing cap is nearly full or when villagers go idle — so you can stay focused on the game without micromanaging your attention.

---

## Features

- Plays a custom `.wav` alert when housing turns **orange** (warning) or **red** (full/blocked)
- Plays a custom `.wav` alert when **idle villagers** are detected
- Always-on-top **overlay panel** shows live housing and villager status
- Overlay **flashes red** on danger or idle alert
- **Auto-detects match start/end** by watching for the in-game timer — does nothing while you're in menus or lobbies, activates automatically when a game begins, and resets when it ends
- **Calibration tool** to precisely locate your HUD on any resolution
- Draggable overlay — position it wherever you want

---

## Requirements

### 1. Python 3.10 or newer (Windows)

Download from: https://www.python.org/downloads/

> **Important:** During installation, check the box **"Add Python to PATH"** before clicking Install.

To verify Python is installed, open Command Prompt and run:
```
python --version
```
You should see something like `Python 3.11.x`.

### 2. Python packages

Open Command Prompt and run:
```
pip install pillow numpy psutil
```

The following are **built into Python on Windows** and do not need to be installed:
- `tkinter` — used for the overlay window
- `winsound` — used for playing `.wav` sound files
- `ctypes`, `threading`, `json` — standard library modules

### 3. Sound files (.wav)

The script plays three `.wav` sound files for alerts. You provide these yourself — use any sounds you like.

Place them in the **same folder as `AOE4.py`** with these exact filenames:

| Filename | When it plays |
|---|---|
| `fr_house.wav` | Housing indicator turns orange (warning — getting close) |
| `fr_housenow.wav` | Housing indicator turns red (danger — cap full, units blocked) |
| `fr_idle.wav` | One or more idle villagers detected |

> To use different filenames, see the **Customisation** section below.

---

## Folder layout

Keep all files together in one folder:

```
AOE4.py                    ← the main script
fr_house.wav               ← housing warning sound
fr_housenow.wav            ← housing danger sound
fr_idle.wav                ← idle villager sound
README.md                  ← this file

aoe4_calibration.json      ← created automatically after calibration
aoe4_monitor_error.log     ← created automatically if the script crashes
calibration_housing.png    ← created by --calibrate (preview image)
calibration_villager.png   ← created by --calibrate (preview image)
```

---

## First run — calibration

Calibration tells the script exactly where to find the HUD indicators on your screen. It needs to be done **once per monitor resolution**. If you change resolution or move to a different PC, run it again.

**Step 1** — Start a match in AoE IV. For best results, have your population close to the cap (so the housing indicator is visible and coloured) and leave at least one villager idle.

**Step 2** — Alt-Tab to Command Prompt and run:
```
python AOE4.py --calibrate
```

**Step 3** — Press Enter when prompted, then **immediately switch back to the game**. The script captures a screenshot after a 3-second countdown.

**Step 4** — Two preview images will be saved: `calibration_housing.png` and `calibration_villager.png`. Open them to confirm the correct HUD regions were detected (you should see the bottom-left panel with the house and villager icons highlighted in green).

**Step 5** — When asked to save, press Enter (or type `Y`).

---

## Normal usage

Run the script:
```
python AOE4.py
```

Or simply double-click `AOE4.py` if Python is associated with `.py` files on your system.

The overlay will appear near the top-center of your screen. It starts in **waiting mode** (dim, shows "Waiting... / No match") and activates automatically once a match timer is detected on screen.

```
┌──────────────────────────────────────┐
│  🏠  HOUSING    │  👷  IDLE VILLAGERS │
│      Good            Good            │
└──────────────────────────────────────┘
```

States you will see:

| Panel | Text | Colour | Meaning |
|---|---|---|---|
| Housing | Good | Green | Population has room |
| Housing | Build soon | Orange | Getting close to cap |
| Housing | Build NOW! | Red + flash | Cap full, units are blocked |
| Idle Villagers | Good | Green | All villagers working |
| Idle Villagers | Idle | Blue + flash | One or more villagers are idle |
| Both panels | Waiting... / No match | Dim gold | No active match detected |

The overlay is **draggable** — click and drag it anywhere on screen.

To stop the script, close the overlay window.

---

## Customisation

Open `AOE4.py` in any text editor (Notepad works). All settings are near the top of the file under `# ── Config ──`.

```python
CHECK_INTERVAL       = 0.5   # How often to take a screenshot and check (seconds)
                              # Lower = more responsive, slightly more CPU usage

ALERT_COOLDOWN       = 25    # Minimum seconds between repeated housing alert sounds
                              # Prevents the same alert from spamming every 0.5s

ALERT_COOLDOWNVILLS  = 6     # Minimum seconds between repeated idle villager alert sounds

CONSECUTIVE_NEEDED   = 3     # How many checks in a row must show the same state before alerting
                              # Prevents false positives from brief screen glitches
                              # e.g. 3 checks × 0.5s = alert fires after ~1.5s of sustained state

ORANGE_THRESHOLD_PCT = 0.4   # % of the housing scan region that must be orange to trigger warning
RED_THRESHOLD_PCT    = 0.3   # % of the housing scan region that must be red to trigger danger
BLUE_PIXEL_COUNT_MIN = 10    # Minimum blue pixels in villager region to count as "idle villagers present"

OVERLAY_Y_PCT = 0.18         # Vertical position of the overlay as a fraction of screen height
                              # 0.18 = 18% from the top — safely below the in-game timer
                              # Increase to move the overlay lower (e.g. 0.25 = 25%)
```

### Changing sound files

Find these three functions and update the filename strings:

```python
def beep_housing_warning():
    sound_path = os.path.join(SOUND_DIR, "fr_house.wav")      # ← change this filename

def beep_housing_danger():
    sound_path = os.path.join(SOUND_DIR, "fr_housenow.wav")   # ← change this filename

def beep_villager():
    sound_path = os.path.join(SOUND_DIR, "fr_idle.wav")       # ← change this filename
```

You can also use an absolute path if your sound files are stored elsewhere:
```python
sound_path = r"C:\Users\YourName\Sounds\my_alert.wav"
```

---

## Troubleshooting

### The script closes immediately or shows a crash
A file called `aoe4_monitor_error.log` will be created in the same folder. Open it — the error message will usually tell you exactly what went wrong.

### "MISSING PACKAGE" error on startup
Run the install command shown in the error. For example:
```
pip install pillow numpy psutil
```
If `pip` itself is not found, Python was not added to PATH during installation. Reinstall Python from python.org and check the **"Add Python to PATH"** box.

### "MISSING: winsound — are you on Windows?"
This script is Windows-only. `winsound` is a module built into Python on Windows and is not available on Mac or Linux.

### "MISSING: tkinter"
tkinter is included with the standard Python installer from python.org. If it is missing, you may have installed a minimal or non-standard Python build. Reinstall Python from https://www.python.org/downloads/

### The overlay appears in the wrong position
Either drag it with your mouse, or edit `OVERLAY_Y_PCT` in the script. The value `0.18` places it at 18% from the top of the screen. Increase it to move it lower (e.g. `0.30` for 30%).

### Alerts fire when I'm not in a game
This should not happen — the script only activates when it detects the in-game timer on screen. If it does occur, make sure `CONSECUTIVE_NEEDED` is at least `2` or `3`, which requires the indicator to be consistently detected across multiple checks before alerting.

### Alerts don't trigger during a game
Run `python AOE4.py --calibrate` while in a live match and check the two preview PNG images it saves. If the highlighted regions don't show the correct HUD area, the scan regions need recalibrating. Make sure the game is in fullscreen or fullscreen windowed mode.

### The script doesn't detect the game starting
Detection works by looking for the MM:SS match timer at the top-center of your screen. It only appears once a match has actually started — not in the lobby or on the loading screen. If detection consistently fails, ensure the game is in fullscreen or borderless windowed mode.

### A sound file fails to play / no sound
- Confirm the `.wav` file exists in the same folder as `AOE4.py`
- Confirm the filename matches exactly (including capitalisation)
- Confirm it is a valid `.wav` file — MP3 and other formats will not work with `winsound`

---

## How it works

Every `CHECK_INTERVAL` seconds the script takes a screenshot of two small regions in the bottom-left corner of the screen — the housing indicator area and the idle villager indicator area — and analyses the pixel colours:

- **Housing detection:** counts red and orange pixels in the housing region. If they exceed `RED_THRESHOLD_PCT` or `ORANGE_THRESHOLD_PCT` of the region, the danger or warning state is triggered.
- **Idle villager detection:** counts blue pixels in the villager region. The idle villager icon in the AoE4 HUD turns distinctly blue when villagers are idle.
- **Game detection:** samples the top-center of the screen where the MM:SS match timer lives. White digit pixels on a dark background = a match is in progress. If the timer disappears (match over, back to menu), monitoring pauses automatically until the next match starts.

Calibration stores the exact pixel coordinates of the HUD regions for your screen resolution in `aoe4_calibration.json`. Without calibration the script falls back to percentage-based defaults that work on common resolutions but may be slightly off on unusual setups.