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
    import tkinter as tk
except ImportError as e:
    msg = f"MISSING: tkinter (built into Python on Windows)\nDetail: {e}"
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
import threading
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

HOUSING_WARNING_BEEP = (800,  300)
HOUSING_DANGER_BEEP  = (1100, 200)
VILLAGER_BEEP        = (500,  500)

CALIBRATION_FILE     = "aoe4_calibration.json"

# Overlay Y position as % of LOGICAL screen height (what tkinter uses)
# AoE4 timer ends at ~9% of screen; 18% gives clear space below it
OVERLAY_Y_PCT = 0.18

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

# ── Game detection ────────────────────────────────────────────────────────────

AOE4_PROCESS = "AoE4DE.exe"

def is_game_running():
    """Returns True if AoE4DE.exe is currently running."""
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and proc.info['name'].lower() == AOE4_PROCESS.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
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

# ── Overlay ───────────────────────────────────────────────────────────────────

class Overlay:
    C_BG       = "#0e0c09"
    C_BORDER   = "#7a5c1e"
    C_GOLD     = "#c9a84c"
    C_GOLD_DIM = "#3a2a0a"
    C_OK       = "#4caf6e"
    C_WARNING  = "#d4820a"
    C_DANGER   = "#c0392b"
    C_VILLAGER = "#3a9fd4"
    C_TEXT_DIM = "#4a3e28"

    W = 520
    H = 84

    def __init__(self):
        self._pending  = None
        self._flash_on = False
        self._flashing = False

        root = tk.Tk()
        self.root = root
        root.title("AoE4 Monitor")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.93)
        root.configure(bg=self.C_BG)

        # ── Canvas for angular border ─────────────────────────────
        self.canvas = tk.Canvas(root, width=self.W, height=self.H,
                                bg=self.C_BG, highlightthickness=0)
        self.canvas.pack()
        self._draw_border()

        # ── Content ───────────────────────────────────────────────
        inner = tk.Frame(root, bg=self.C_BG)
        inner.place(x=16, y=10, width=self.W-32, height=self.H-20)

        # LEFT: Housing
        left = tk.Frame(inner, bg=self.C_BG)
        left.pack(side="left", fill="y", padx=(2, 0))

        self.house_icon = tk.Label(left, text="🏠", font=("Segoe UI Emoji", 26),
                                   bg=self.C_BG, fg=self.C_OK)
        self.house_icon.pack(side="left", padx=(0, 8))

        ht = tk.Frame(left, bg=self.C_BG)
        ht.pack(side="left", fill="y")
        tk.Label(ht, text="HOUSING", font=("Consolas", 8, "bold"),
                 bg=self.C_BG, fg=self.C_TEXT_DIM).pack(anchor="w")
        self.house_msg = tk.Label(ht, text="All good", font=("Consolas", 15, "bold"),
                                  bg=self.C_BG, fg=self.C_OK, anchor="w")
        self.house_msg.pack(anchor="w")

        # Divider
        tk.Frame(inner, bg=self.C_GOLD_DIM, width=1).pack(
            side="left", fill="y", padx=18, pady=2)

        # RIGHT: Villagers
        right = tk.Frame(inner, bg=self.C_BG)
        right.pack(side="left", fill="y", padx=(0, 2))

        self.vil_icon = tk.Label(right, text="👷", font=("Segoe UI Emoji", 26),
                                 bg=self.C_BG, fg=self.C_OK)
        self.vil_icon.pack(side="left", padx=(0, 8))

        vt = tk.Frame(right, bg=self.C_BG)
        vt.pack(side="left", fill="y")
        tk.Label(vt, text="IDLE VILLAGERS", font=("Consolas", 8, "bold"),
                 bg=self.C_BG, fg=self.C_TEXT_DIM).pack(anchor="w")
        self.vil_msg = tk.Label(vt, text="Good", font=("Consolas", 15, "bold"),
                                bg=self.C_BG, fg=self.C_OK, anchor="w")
        self.vil_msg.pack(anchor="w")

        # Drag
        for w in (self.canvas, inner, left, right,
                  self.house_icon, self.house_msg, self.vil_icon, self.vil_msg):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>",     self._drag_move)

        # ── Position using LOGICAL screen size from tkinter ───────
        # tkinter's winfo_screenwidth/height() returns logical pixels,
        # matching geometry() coordinates — DPI-safe on all monitors.
        root.update_idletasks()
        logical_sw = root.winfo_screenwidth()
        logical_sh = root.winfo_screenheight()
        ow = root.winfo_reqwidth()
        x  = (logical_sw - ow) // 2
        y  = int(logical_sh * OVERLAY_Y_PCT)
        root.geometry(f"+{x}+{y}")
        print(f"  Logical screen : {logical_sw}x{logical_sh}")
        print(f"  Overlay position: x={x}, y={y}  ({OVERLAY_Y_PCT*100:.0f}% of screen height)")

        self._drag_x = 0
        self._drag_y = 0
        self._poll_queue()

    # ── Drawing ───────────────────────────────────────────────────

    def _draw_border(self):
        c = self.canvas
        w, h, n = self.W, self.H, 10
        pts = [n,0, w-n,0, w,n, w,h-n, w-n,h, n,h, 0,h-n, 0,n]
        c.create_polygon(pts, fill=self.C_BG, outline=self.C_BORDER,
                         width=1, tags="border_main")
        acc = 18
        for ox, oy, dx, dy in [(0,0,1,1),(w,0,-1,1),(0,h,1,-1),(w,h,-1,-1)]:
            c.create_line(ox, oy+dy*n, ox, oy+dy*(n+acc), fill=self.C_GOLD, width=2)
            c.create_line(ox+dx*n, oy, ox+dx*(n+acc), oy,  fill=self.C_GOLD, width=2)
        ins = 3
        ip = [n+ins,ins, w-n-ins,ins, w-ins,n+ins, w-ins,h-n-ins,
              w-n-ins,h-ins, n+ins,h-ins, ins,h-n-ins, ins,n+ins]
        c.create_polygon(ip, fill="", outline="#1e1608", width=1)
        mid = w // 2
        c.create_line(mid-30, 2, mid+30, 2, fill=self.C_GOLD, width=1)

    # ── Drag ──────────────────────────────────────────────────────

    def _drag_start(self, e):
        self._drag_x = e.x_root - self.root.winfo_x()
        self._drag_y = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root-self._drag_x}+{e.y_root-self._drag_y}")

    # ── Thread-safe update ────────────────────────────────────────

    def _poll_queue(self):
        if self._pending is not None:
            self._apply(*self._pending)
            self._pending = None
        self.root.after(200, self._poll_queue)

    def update(self, house_state, vil_active, vil_count):
        self._pending = (house_state, vil_active, vil_count)

    def set_status(self, status):
        """Switch overlay between 'waiting' and 'active' display modes."""
        if status == "waiting":
            self._pending = ("__waiting__", False, 0)
        else:
            # Active: reset to ok state, monitor_loop will update immediately
            pass

    def _apply(self, house_state, vil_active, vil_count):
        if house_state == '__waiting__':
            self.house_icon.configure(fg=self.C_TEXT_DIM)
            self.house_msg .configure(fg=self.C_TEXT_DIM, text="Waiting...")
            self.vil_icon  .configure(fg=self.C_TEXT_DIM)
            self.vil_msg   .configure(fg=self.C_TEXT_DIM, text="No match")
            self._stop_flash()
            return

        if house_state == 'danger':
            hc, hm = self.C_DANGER,  "Build NOW!"
        elif house_state == 'warning':
            hc, hm = self.C_WARNING, "Build soon"
        else:
            hc, hm = self.C_OK,      "Good"

        if vil_active:
            vc = self.C_VILLAGER
#            vm = f"Idle: ~{vil_count}"
            vm = f"Idle"
        else:
            vc = self.C_OK
            vm = "Good"

        self.house_icon.configure(fg=hc)
        self.house_msg .configure(fg=hc, text=hm)
        self.vil_icon  .configure(fg=vc)
        self.vil_msg   .configure(fg=vc, text=vm)

        if house_state == 'danger' or vil_active:
            self._start_flash()
        else:
            self._stop_flash()

    def _start_flash(self):
        if not self._flashing:
            self._flashing = True; self._do_flash()

    def _stop_flash(self):
        self._flashing = False
        try: self.canvas.itemconfig("border_main", outline=self.C_BORDER)
        except Exception: pass

    def _do_flash(self):
        if not self._flashing: return
        self._flash_on = not self._flash_on
        c = self.C_DANGER if self._flash_on else self.C_BORDER
        try: self.canvas.itemconfig("border_main", outline=c)
        except Exception: pass
        self.root.after(500, self._do_flash)

    def run(self):
        self.root.mainloop()

# ── Monitor loop ──────────────────────────────────────────────────────────────

def monitor_loop(h_region, v_region, px_per_villager, overlay):
    h_consec = 0; h_last_state = 'ok'; h_last_alert = 0.0
    v_consec = 0; v_was_active = False; v_last_alert = 0.0

    # ── Wait for a match to start ─────────────────────────────────
    print("  Waiting for a match to start (watching for game timer)...")
    overlay.set_status("waiting")
    while not is_match_active():
        time.sleep(3)
    print(f"  [{time.strftime('%H:%M:%S')}] Match detected — monitoring started!")
    overlay.set_status("active")

    while True:
        try:
            now = time.time(); ts = time.strftime('%H:%M:%S')

            # Check if match ended (timer gone)
            if not is_match_active():
                print(f"  [{ts}] Match ended — waiting for next match...")
                overlay.set_status("waiting")
                h_consec = 0; h_last_state = 'ok'; h_last_alert = 0.0
                v_consec = 0; v_was_active = False; v_last_alert = 0.0
                while not is_match_active():
                    time.sleep(3)
                print(f"  [{time.strftime('%H:%M:%S')}] New match detected!")
                overlay.set_status("active")
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
                    threading.Thread(target=beep_housing_danger, daemon=True).start()
                else:
                    print(f"[{ts}] *** HOUSING WARNING ***")
                    threading.Thread(target=beep_housing_warning, daemon=True).start()
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
                threading.Thread(target=beep_villager, daemon=True).start()
                v_last_alert = now

            h_alert = h_consec >= CONSECUTIVE_NEEDED
            v_alert = v_consec >= CONSECUTIVE_NEEDED
            overlay.update(h_state if h_alert else 'ok', v_alert, v_count)

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
            print("  Skipped. Overlay will show rough estimate.\n")

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
            print(f"  Overlay Y       : {OVERLAY_Y_PCT*100:.0f}% of logical screen height")
            print("\n  Overlay is draggable. Close it to stop.\n")

            overlay = Overlay()
            t = threading.Thread(target=monitor_loop,
                                 args=(h_region, v_region, px_per_villager, overlay),
                                 daemon=True)
            t.start()
            overlay.run()

    except Exception:
        err = traceback.format_exc()
        write_log(err)
        print("\n--- FATAL ERROR ---")
        print(err)
        input("\nPress ENTER to close...")
