import sys
import os
import traceback

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aoe4_monitor_error.log")

def write_log(text):
    with open(LOG_FILE, "w") as f:
        f.write(text)
    print(f"\nError saved to: {LOG_FILE}")

try:
    import numpy as np
except ImportError as e:
    msg = f"MISSING PACKAGE: numpy\nRun: pip install numpy\n\nDetail: {e}"
    write_log(msg); print(msg); input("\nPress ENTER to close..."); sys.exit(1)

try:
    from PIL import ImageGrab, Image, ImageDraw
except ImportError as e:
    msg = f"MISSING PACKAGE: pillow\nRun: pip install pillow\n\nDetail: {e}"
    write_log(msg); print(msg); input("\nPress ENTER to close..."); sys.exit(1)

try:
    import winsound
except ImportError as e:
    msg = f"MISSING: winsound — are you on Windows?\nDetail: {e}"
    write_log(msg); print(msg); input("\nPress ENTER to close..."); sys.exit(1)

try:
    import psutil
except ImportError as e:
    msg = f"MISSING PACKAGE: psutil\nRun: pip install psutil\n\nDetail: {e}"
    write_log(msg); print(msg); input("\nPress ENTER to close..."); sys.exit(1)

import ctypes
import time
import json

# ── Config ────────────────────────────────────────────────────────────────────

CHECK_INTERVAL       = 0.5      # seconds between checks
ALERT_COOLDOWN       = 25      # seconds between repeated beeps for houses
ALERT_COOLDOWNVILLS       = 6      # seconds between repeated beeps for villagers
CONSECUTIVE_NEEDED   = 3      # consecutive detections before alerting

ORANGE_THRESHOLD_PCT = 0.4
RED_THRESHOLD_PCT    = 0.3
BLUE_PIXEL_COUNT_MIN = 10     # min blue pixels to count as "idle villagers present"

CALIBRATION_FILE     = "aoe4_calibration.json"

# ── Game detection ────────────────────────────────────────────────────────────

def is_match_active():
    """
    Detect whether an AoE4 match is actually in progress by checking for the
    game timer at the top-center of the screen.

    The timer (MM:SS) only appears during a live match — not in menus, lobbies,
    or the loading screen. We look for its signature: white digit pixels and a
    dark background box in a narrow center-top strip.
    """
    try:
        sw, sh = get_physical_screen_size()
        x1 = int(0.46 * sw); x2 = int(0.54 * sw)
        y1 = int(0.05 * sh); y2 = int(0.13 * sh)
        arr = np.array(ImageGrab.grab(bbox=(x1, y1, x2, y2)))
        r = arr[:,:,0].astype(int); g = arr[:,:,1].astype(int); b = arr[:,:,2].astype(int)
        white = ((r > 175) & (g > 175) & (b > 175)).sum()
        dark  = ((r + g + b) // 3 < 60).sum()
        return int(white) >= 8 and int(dark) >= 15
    except Exception:
        return False

# ── Screen helpers ────────────────────────────────────────────────────────────

def get_physical_screen_size():
    """Physical pixels — used for screenshot region coordinates."""
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

def default_regions(sw, sh):
    housing  = (0,             int(0.785*sh), int(0.120*sw), int(0.840*sh))
    villager = (int(0.050*sw), int(0.765*sh), int(0.115*sw), int(0.830*sh))
    return housing, villager

def load_calibration(sw, sh):
    key = f"{sw}x{sh}"
    if os.path.exists(CALIBRATION_FILE):
        with open(CALIBRATION_FILE) as f:
            data = json.load(f)
        if key in data:
            d = data[key]
            print(f"  Loaded calibration for {key}")
            return tuple(d["housing"]), tuple(d["villager"]), d.get("px_per_villager")
        print(f"  No calibration for {key} — using defaults. Run --calibrate for accuracy.")
    else:
        print("  No calibration file — using defaults. Run --calibrate for accuracy.")
    h, v = default_regions(sw, sh)
    return h, v, None

def save_calibration(sw, sh, housing, villager, px_per_villager):
    key  = f"{sw}x{sh}"
    data = {}
    if os.path.exists(CALIBRATION_FILE):
        with open(CALIBRATION_FILE) as f:
            data = json.load(f)
    data[key] = {"housing": list(housing), "villager": list(villager),
                 "px_per_villager": px_per_villager}
    with open(CALIBRATION_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Saved → {CALIBRATION_FILE}")

# ── Colour detection ──────────────────────────────────────────────────────────

def count_blue(arr):
    r = arr[:,:,0].astype(int); g = arr[:,:,1].astype(int); b = arr[:,:,2].astype(int)
    return int(((b > 140) & (b > r+25) & (b > g+15)).sum())

def pct_red(arr):
    r = arr[:,:,0].astype(int); g = arr[:,:,1].astype(int); b = arr[:,:,2].astype(int)
    return ((r>175) & (g<85) & (b<85) & (r > g*2.0)).sum() / arr[:,:,0].size * 100

def pct_orange(arr):
    r = arr[:,:,0].astype(int); g = arr[:,:,1].astype(int); b = arr[:,:,2].astype(int)
    return ((r>155) & (g>70) & (g<150) & (b<65) & (r > g*1.35)).sum() / arr[:,:,0].size * 100

def analyse_housing(region):
    arr = np.array(ImageGrab.grab(bbox=region))
    r, o = pct_red(arr), pct_orange(arr)
    if r >= RED_THRESHOLD_PCT:    return 'danger',  o, r
    if o >= ORANGE_THRESHOLD_PCT: return 'warning', o, r
    return 'ok', o, r

def analyse_villager(region, px_per_villager):
    arr     = np.array(ImageGrab.grab(bbox=region))
    blue_px = count_blue(arr)
    active  = blue_px >= BLUE_PIXEL_COUNT_MIN
    if active:
        if px_per_villager and px_per_villager > 0:
            est = max(1, round(blue_px / px_per_villager))
        else:
            est = max(1, round(blue_px / 25))   # uncalibrated default
    else:
        est = 0
    return active, est, blue_px

# ── Sound ─────────────────────────────────────────────────────────────────────

SOUND_DIR = os.path.dirname(__file__)

def beep_housing_warning():
    sound_path = os.path.join(SOUND_DIR, "fr_house.wav")
    winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)

def beep_housing_danger():
    sound_path = os.path.join(SOUND_DIR, "fr_housenow.wav")
    winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)

def beep_villager():
    sound_path = os.path.join(SOUND_DIR, "fr_idle.wav")
    winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)

# ── Monitor loop ──────────────────────────────────────────────────────────────

def monitor_loop(h_region, v_region, px_per_villager):
    h_consec = 0; h_last_state = 'ok'; h_last_alert = 0.0
    v_consec = 0; v_was_active = False; v_last_alert = 0.0

    # ── Wait for a match to start ─────────────────────────────────
    print("  Waiting for a match to start (watching for game timer)...")
    while not is_match_active():
        time.sleep(3)
    print(f"  [{time.strftime('%H:%M:%S')}] Match detected — monitoring started!")

    while True:
        try:
            now = time.time(); ts = time.strftime('%H:%M:%S')

            # Check if match ended (timer gone)
            if not is_match_active():
                print(f"  [{ts}] Match ended — waiting for next match...")
                h_consec = 0; h_last_state = 'ok'; h_last_alert = 0.0
                v_consec = 0; v_was_active = False; v_last_alert = 0.0
                while not is_match_active():
                    time.sleep(3)
                print(f"  [{time.strftime('%H:%M:%S')}] New match detected!")
                continue

            h_state, opct, rpct        = analyse_housing(h_region)
            v_active, v_count, blue_px = analyse_villager(v_region, px_per_villager)

            # Housing
            if h_state != 'ok':
                h_consec += 1
            else:
                if h_last_state != 'ok':
                    print(f"[{ts}] [OK]  Housing back to normal")
                h_consec = 0
            h_last_state = h_state

            if h_consec >= CONSECUTIVE_NEEDED and (now - h_last_alert) >= ALERT_COOLDOWN:
                if h_state == 'danger':
                    print(f"[{ts}] *** HOUSING DANGER – BUILD NOW! ***")
                    beep_housing_danger()
                else:
                    print(f"[{ts}] *** HOUSING WARNING ***")
                    beep_housing_warning()
                h_last_alert = now

            # Villager
            if v_active:
                v_consec += 1
            else:
                if v_was_active:
                    print(f"[{ts}] [OK]  No idle villagers")
                v_consec = 0
            v_was_active = v_active

            if v_consec >= CONSECUTIVE_NEEDED and (now - v_last_alert) >= ALERT_COOLDOWNVILLS:
                print(f"[{ts}] *** IDLE VILLAGERS (~{v_count}) – put them to work! ***")
                beep_villager()
                v_last_alert = now

        except Exception:
            err = traceback.format_exc()
            print(f"[monitor error]\n{err}")
            write_log(err)

        time.sleep(CHECK_INTERVAL)

# ── Calibration ───────────────────────────────────────────────────────────────

def save_debug_crop(screenshot, region, filename, label):
    crop = screenshot.crop(region)
    crop = crop.resize((crop.width*6, crop.height*6), Image.NEAREST)
    draw = ImageDraw.Draw(crop)
    draw.rectangle([0,0,crop.width-1,crop.height-1], outline="lime", width=3)
    draw.text((4,4), label, fill="lime")
    crop.save(filename)
    print(f"    → {filename}")

def calibrate():
    sw, sh = get_physical_screen_size()
    print("\n" + "="*60)
    print("  AoE4 Monitor – Calibration")
    print("="*60)
    print(f"\n  Physical screen: {sw}x{sh}")
    print()
    print("  STEPS:")
    print("  1. Launch a game in AoE IV")
    print("  2. Best if pop cap is nearly full + at least 1 idle villager")
    print("  3. Alt-Tab here, press ENTER, then QUICKLY switch back")
    print()
    input("  → Press ENTER when ready... ")
    print("\n  Capturing in 3 seconds...")
    for i in range(3,0,-1): print(f"    {i}..."); time.sleep(1)

    screenshot = ImageGrab.grab()
    full       = np.array(screenshot)
    print(f"  Captured.\n")

    x_max   = int(sw * 0.20)
    y_start = int(sh * 0.70)

    # Housing
    print("  Scanning for housing indicator (red/orange)...")
    best_housing = None; best_h = 0
    for y1 in range(y_start, sh-10, 3):
        for hs in [25, 35, 50]:
            y2 = min(y1+hs, sh)
            s  = full[y1:y2, 0:x_max]
            r=s[:,:,0].astype(int); g=s[:,:,1].astype(int); b=s[:,:,2].astype(int)
            sc = ((r>175)&(g<85)&(b<85)&(r>g*2.0)).sum() + \
                 ((r>155)&(g>70)&(g<150)&(b<65)&(r>g*1.35)).sum()
            if sc > best_h: best_h=sc; best_housing=(0,y1,x_max,y2)
    if best_h < 3:
        print("  WARNING: Not found — using defaults.\n")
        best_housing, _ = default_regions(sw, sh)
    else:
        print(f"  ✓ Housing: {best_housing}  (score={best_h})\n")

    # Villager icon
    print("  Scanning for idle villager indicator (blue)...")
    best_villager = None; best_v = 0
    for y1 in range(y_start, sh-10, 3):
        for hs in [25, 35, 50]:
            y2 = min(y1+hs, sh)
            s  = full[y1:y2, 0:x_max]
            r=s[:,:,0].astype(int); g=s[:,:,1].astype(int); b=s[:,:,2].astype(int)
            sc = ((b>140)&(b>r+25)&(b>g+15)).sum()
            if sc > best_v: best_v=sc; best_villager=(0,y1,x_max,y2)

    px_per_villager = None
    if best_v < 5:
        print("  WARNING: Not found — using defaults.\n")
        _, best_villager = default_regions(sw, sh)
    else:
        print(f"  ✓ Villager: {best_villager}  (blue_px={best_v})\n")

        # Count calibration
        print("  ─────────────────────────────────────────────────────")
        print("  IDLE COUNT CALIBRATION")
        print("  Enter the idle villager number shown in your HUD")
        print("  when you took this screenshot. Press ENTER to skip.")
        print("  ─────────────────────────────────────────────────────")
        ans = input("  Idle villagers in HUD right now: ").strip()
        if ans.isdigit() and int(ans) > 0:
            known = int(ans)
            # Measure blue pixels in the found region
            reg = best_villager
            slice_ = full[reg[1]:reg[3], reg[0]:reg[2]]
            r=slice_[:,:,0].astype(int); g=slice_[:,:,1].astype(int); b=slice_[:,:,2].astype(int)
            cal_blue = int(((b>140)&(b>r+25)&(b>g+15)).sum())
            if cal_blue > 0:
                px_per_villager = cal_blue / known
                print(f"  ✓ {cal_blue} blue px / {known} villagers = {px_per_villager:.1f} px/villager\n")
            else:
                print("  Could not read blue pixels. Skipping count calibration.\n")
        else:
            print("  Skipped.\n")

    # Previews
    print("  Saving previews...")
    save_debug_crop(screenshot, best_housing,  "calibration_housing.png",  "Housing")
    save_debug_crop(screenshot, best_villager, "calibration_villager.png", "Villager")

    print()
    print("  Check the two PNG files to confirm correct areas.")
    print()
    ans = input("  Save calibration? [Y/n]: ").strip().lower()
    if ans in ("", "y", "yes"):
        save_calibration(sw, sh, best_housing, best_villager, px_per_villager)
        print("  ✓ Done! Run the script normally to start monitoring.\n")
    else:
        print("  Discarded.\n")

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        if "--calibrate" in sys.argv:
            calibrate()
        else:
            print("=" * 56)
            print("  AoE4 Housing + Idle Villager Monitor  –  Windows")
            print("=" * 56)

            sw, sh = get_physical_screen_size()
            h_region, v_region, px_per_villager = load_calibration(sw, sh)

            print(f"\n  Physical screen : {sw}x{sh}")
            print(f"  Housing region  : {h_region}")
            print(f"  Villager region : {v_region}")
            ppv = f"{px_per_villager:.1f}" if px_per_villager else "uncalibrated (~25 default)"
            print(f"  px/villager     : {ppv}")
            print(f"  Check interval  : {CHECK_INTERVAL}s  |  Cooldown: {ALERT_COOLDOWN}s")
            print("\n  Press Ctrl+C to stop.\n")

            monitor_loop(h_region, v_region, px_per_villager)

    except Exception:
        err = traceback.format_exc()
        write_log(err)
        print("\n--- FATAL ERROR ---")
        print(err)
        input("\nPress ENTER to close...")
