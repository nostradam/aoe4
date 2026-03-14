"""
AoE4 Monitor — Visual Calibration Tool
Double-click to run. Drag the colored boxes over the HUD elements, then click Save.
"""

import sys, os, json, time, threading, traceback
import tkinter as tk

try:
    import numpy as np
except ImportError:
    import subprocess; subprocess.call([sys.executable, "-m", "pip", "install", "numpy"])
    import numpy as np

try:
    import mss as _mss
    _MSS = _mss.mss()
    def grab(bbox):
        mon = {"left": bbox[0], "top": bbox[1],
               "width": bbox[2]-bbox[0], "height": bbox[3]-bbox[1]}
        raw = _MSS.grab(mon)
        arr = np.frombuffer(raw.bgra, dtype=np.uint8).reshape(raw.height, raw.width, 4)
        return arr[:,:,2::-1]
except ImportError:
    from PIL import ImageGrab as _IG
    def grab(bbox):
        return np.array(_IG.grab(bbox=bbox))

import ctypes
def get_screen_size():
    u = ctypes.windll.user32
    u.SetProcessDPIAware()
    return u.GetSystemMetrics(0), u.GetSystemMetrics(1)

CALIBRATION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aoe4_calibration.json")

def load_existing(sw, sh):
    key = f"{sw}x{sh}"
    if os.path.exists(CALIBRATION_FILE):
        with open(CALIBRATION_FILE) as f:
            data = json.load(f)
        if key in data:
            d = data[key]
            return tuple(d["housing"]), tuple(d["villager"]), d.get("px_per_villager")
    h = (int(0.003*sw), int(0.782*sh), int(0.048*sw), int(0.867*sh))
    v = (int(0.049*sw), int(0.726*sh), int(0.104*sw), int(0.960*sh))
    return h, v, None

def save_calibration(sw, sh, housing, villager, px_per_villager):
    key = f"{sw}x{sh}"
    data = {}
    if os.path.exists(CALIBRATION_FILE):
        with open(CALIBRATION_FILE) as f:
            data = json.load(f)
    data[key] = {
        "housing":  [int(x) for x in housing],
        "villager": [int(x) for x in villager],
        "px_per_villager": float(px_per_villager) if px_per_villager else None
    }
    with open(CALIBRATION_FILE, "w") as f:
        json.dump(data, f, indent=2)

def analyse_housing(region):
    try:
        arr = grab(region)
        if arr.size == 0: return 0.0, 0.0
        r=arr[:,:,0].astype(int); g=arr[:,:,1].astype(int); b=arr[:,:,2].astype(int)
        total = arr.shape[0]*arr.shape[1]
        red_pct    = ((r>175)&(g<85)&(b<85)&(r>g*2.0)).sum() / total * 100
        orange_pct = ((r>155)&(g>70)&(g<150)&(b<65)&(r>g*1.35)).sum() / total * 100
        return red_pct, orange_pct
    except Exception:
        return 0.0, 0.0

def analyse_villager(region):
    try:
        arr = grab(region)
        if arr.size == 0: return 0
        r=arr[:,:,0].astype(int); g=arr[:,:,1].astype(int); b=arr[:,:,2].astype(int)
        return int(((b>140)&(b>r+25)&(b>g+15)).sum())
    except Exception:
        return 0

C_BG       = "#0a0908"
C_GOLD     = "#c9a84c"
C_GOLD_DIM = "#3a2a0a"
C_BORDER   = "#5a4820"
C_RED      = "#c0392b"
C_ORANGE   = "#d4820a"
C_BLUE     = "#3a9fd4"
C_GREEN    = "#4caf6e"
C_TEXT     = "#d4c49a"
C_DIM      = "#5a5040"
C_HOUSING  = "#e05030"
C_VILLAGER = "#3090d0"


class DragBox:
    HANDLE = 12

    def __init__(self, canvas, x1, y1, x2, y2, color, label, scale):
        self.canvas = canvas
        self.color  = color
        self.label  = label
        self.scale  = scale
        self.lx1 = int(x1 * scale)
        self.ly1 = int(y1 * scale)
        self.lx2 = int(x2 * scale)
        self.ly2 = int(y2 * scale)
        self._drag_mode = None
        self._drag_ox = 0
        self._drag_oy = 0
        self._items = []
        self.draw()

    def physical(self):
        s = self.scale
        return (int(self.lx1/s), int(self.ly1/s),
                int(self.lx2/s), int(self.ly2/s))

    def draw(self):
        for i in self._items:
            try: self.canvas.delete(i)
            except: pass
        self._items = []
        c = self.canvas
        x1,y1,x2,y2 = self.lx1,self.ly1,self.lx2,self.ly2
        h = self.HANDLE
        self._items.append(c.create_rectangle(x1,y1,x2,y2,
            fill=self.color, stipple="gray25", outline=""))
        self._items.append(c.create_rectangle(x1,y1,x2,y2,
            outline=self.color, width=2, fill=""))
        for hx,hy in [(x1,y1),(x2-h,y1),(x1,y2-h),(x2-h,y2-h)]:
            self._items.append(c.create_rectangle(hx,hy,hx+h,hy+h,
                fill=self.color, outline="white", width=1))
        self._items.append(c.create_text(x1+8,y1+6,
            text=self.label, fill="white", anchor="nw",
            font=("Consolas",10,"bold")))

    def hit_test(self, mx, my):
        x1,y1,x2,y2 = self.lx1,self.ly1,self.lx2,self.ly2
        h = self.HANDLE
        for name,(cx1,cy1,cx2,cy2) in [
            ("tl",(x1,y1,x1+h,y1+h)), ("tr",(x2-h,y1,x2,y1+h)),
            ("bl",(x1,y2-h,x1+h,y2)), ("br",(x2-h,y2-h,x2,y2))]:
            if cx1<=mx<=cx2 and cy1<=my<=cy2: return name
        if x1<=mx<=x2 and y1<=my<=y2: return "move"
        return None

    def start_drag(self, mx, my):
        self._drag_mode = self.hit_test(mx, my)
        self._drag_ox = mx; self._drag_oy = my
        return self._drag_mode is not None

    def do_drag(self, mx, my, sw_log, sh_log):
        if not self._drag_mode: return
        dx = mx - self._drag_ox; dy = my - self._drag_oy
        self._drag_ox = mx; self._drag_oy = my
        MIN = 20
        m = self._drag_mode
        if m == "move":
            bw = self.lx2 - self.lx1; bh = self.ly2 - self.ly1
            self.lx1 = max(0, min(sw_log-bw, self.lx1+dx))
            self.ly1 = max(0, min(sh_log-bh, self.ly1+dy))
            self.lx2 = self.lx1 + bw; self.ly2 = self.ly1 + bh
        elif m == "tl":
            self.lx1 = max(0, min(self.lx2-MIN, self.lx1+dx))
            self.ly1 = max(0, min(self.ly2-MIN, self.ly1+dy))
        elif m == "tr":
            self.lx2 = max(self.lx1+MIN, min(sw_log, self.lx2+dx))
            self.ly1 = max(0, min(self.ly2-MIN, self.ly1+dy))
        elif m == "bl":
            self.lx1 = max(0, min(self.lx2-MIN, self.lx1+dx))
            self.ly2 = max(self.ly1+MIN, min(sh_log, self.ly2+dy))
        elif m == "br":
            self.lx2 = max(self.lx1+MIN, min(sw_log, self.lx2+dx))
            self.ly2 = max(self.ly1+MIN, min(sh_log, self.ly2+dy))
        self.draw()

    def stop_drag(self):
        self._drag_mode = None


class CalibrationApp:

    def __init__(self):
        self.sw, self.sh = get_screen_size()

        # Fullscreen transparent overlay
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.0)
        self.root.configure(bg="black")
        self.root.update_idletasks()

        self.lw    = self.root.winfo_screenwidth()
        self.lh    = self.root.winfo_screenheight()
        self.root.geometry(f"{self.lw}x{self.lh}+0+0")
        self.scale = self.lw / self.sw

        self.canvas = tk.Canvas(self.root, width=self.lw, height=self.lh,
                                bg="black", highlightthickness=0)
        self.canvas.place(x=0, y=0)

        h_reg, v_reg, self.ppv = load_existing(self.sw, self.sh)
        self.box_h = DragBox(self.canvas, *h_reg, C_HOUSING,  "HOUSING",  self.scale)
        self.box_v = DragBox(self.canvas, *v_reg, C_VILLAGER, "VILLAGER", self.scale)
        self._active_box = None

        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>",          self._on_motion)

        self._build_panel()
        self._fade(0.0, 0.70, 12)

        self._running = True
        self._stats   = {"red": 0.0, "orange": 0.0, "blue": 0}
        threading.Thread(target=self._stats_loop, daemon=True).start()
        self._refresh_ui()

    def _build_panel(self):
        # Separate Toplevel using ONLY real tk widgets — no canvas.create_window
        # This ensures buttons always receive clicks regardless of panel position
        p = tk.Toplevel(self.root)
        self.panel = p
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.attributes("-alpha", 0.96)
        p.configure(bg=C_BG)
        p.resizable(False, False)

        W = 310
        # Position top-right, ensuring it's fully on screen
        px = max(0, self.lw - W - 24)
        py = 24
        p.geometry(f"{W}x600+{px}+{py}")
        p.lift()
        p.focus_force()

        # Panel drag — bind to background frame only, not children
        self._pdx = 0; self._pdy = 0
        def _start(e): self._pdx=e.x_root-p.winfo_x(); self._pdy=e.y_root-p.winfo_y()
        def _move(e):  p.geometry(f"+{e.x_root-self._pdx}+{e.y_root-self._pdy}")

        def mk_sep():
            f = tk.Frame(p, bg=C_BORDER, height=1)
            f.pack(fill="x", padx=12, pady=3)
            f.bind("<ButtonPress-1>", _start)
            f.bind("<B1-Motion>",     _move)

        def mk_lbl(text, fg=C_DIM, font=("Consolas",8), **kw):
            l = tk.Label(p, text=text, bg=C_BG, fg=fg, font=font, anchor="w", **kw)
            l.pack(fill="x", padx=16, pady=1)
            l.bind("<ButtonPress-1>", _start)
            l.bind("<B1-Motion>",     _move)
            return l

        title = tk.Label(p, text="AoE4  CALIBRATION", bg=C_BG, fg=C_GOLD,
                         font=("Consolas",11,"bold"))
        title.pack(pady=(14,4))
        title.bind("<ButtonPress-1>", _start); title.bind("<B1-Motion>", _move)

        mk_sep()
        mk_lbl("Drag boxes over HUD elements.", C_TEXT)
        mk_lbl("Corner handles to resize.", C_TEXT)
        mk_lbl("")
        mk_lbl("  HOUSING  →  red house icon",   C_HOUSING,  ("Consolas",8,"bold"))
        mk_lbl("  VILLAGER →  teal idle box",     C_VILLAGER, ("Consolas",8,"bold"))
        mk_sep()

        mk_lbl("LIVE DETECTION", C_BORDER, ("Consolas",8,"bold"))

        self._sv_red    = tk.StringVar(value="Red    : —")
        self._sv_orange = tk.StringVar(value="Orange : —")
        self._sv_blue   = tk.StringVar(value="Blue px: —")
        self._sv_status = tk.StringVar(value="● Waiting for game...")

        self._lbl_red    = mk_lbl("", C_DIM, ("Consolas",9))
        self._lbl_orange = mk_lbl("", C_DIM, ("Consolas",9))
        self._lbl_blue   = mk_lbl("", C_DIM, ("Consolas",9))
        self._lbl_red   .config(textvariable=self._sv_red)
        self._lbl_orange.config(textvariable=self._sv_orange)
        self._lbl_blue  .config(textvariable=self._sv_blue)

        mk_sep()
        self._lbl_status = mk_lbl("", C_DIM, ("Consolas",10,"bold"))
        self._lbl_status.config(textvariable=self._sv_status)
        mk_sep()

        mk_lbl("Idle villagers now (count calibration):", C_TEXT)
        vf = tk.Frame(p, bg=C_BG)
        vf.pack(fill="x", padx=16, pady=(0,6))
        vf.bind("<ButtonPress-1>", _start); vf.bind("<B1-Motion>", _move)

        self._vil_var = tk.StringVar()
        tk.Entry(vf, textvariable=self._vil_var, width=5,
                 bg="#1a1508", fg=C_GOLD, insertbackground=C_GOLD,
                 relief="flat", font=("Consolas",11),
                 highlightthickness=1, highlightcolor=C_BORDER,
                 highlightbackground=C_BORDER).pack(side="left", padx=(0,8))
        tk.Label(vf, text="leave blank to skip",
                 bg=C_BG, fg=C_DIM, font=("Consolas",8)).pack(side="left")

        mk_sep()

        # Save and close buttons — plain tk.Button, no canvas involvement
        self._btn_save = tk.Button(p, text="✓  SAVE CALIBRATION",
                                   command=self._save,
                                   bg=C_GOLD_DIM, fg=C_GOLD,
                                   activebackground=C_GOLD, activeforeground=C_BG,
                                   relief="flat", font=("Consolas",10,"bold"),
                                   cursor="hand2", pady=7, bd=0)
        self._btn_save.pack(fill="x", padx=16, pady=(4,3))

        tk.Button(p, text="✕  Close without saving",
                  command=self._close,
                  bg=C_BG, fg=C_DIM,
                  activebackground="#1a1508", activeforeground=C_TEXT,
                  relief="flat", font=("Consolas",8),
                  cursor="hand2", pady=4, bd=0).pack(fill="x", padx=16, pady=(0,12))

        p.update_idletasks()
        self._keep_on_top()

    def _keep_on_top(self):
        # Re-assert topmost every 200ms so the game can't bury the panel
        try:
            self.panel.lift()
            self.panel.attributes("-topmost", True)
        except Exception:
            pass
        self.root.after(200, self._keep_on_top)

    def _fade(self, cur, target, steps):
        if steps <= 0:
            self.root.attributes("-alpha", target); return
        nxt = cur + (target-cur)/steps
        self.root.attributes("-alpha", nxt)
        self.root.after(30, lambda: self._fade(nxt, target, steps-1))

    def _on_press(self, e):
        self._active_box = None
        for box in (self.box_h, self.box_v):
            if box.start_drag(e.x, e.y):
                self._active_box = box; return

    def _on_drag(self, e):
        if self._active_box:
            self._active_box.do_drag(e.x, e.y, self.lw, self.lh)

    def _on_release(self, e):
        if self._active_box: self._active_box.stop_drag()
        self._active_box = None

    def _on_motion(self, e):
        cursor = "arrow"
        for box in (self.box_h, self.box_v):
            hit = box.hit_test(e.x, e.y)
            if hit in ("tl","br"): cursor = "size_nw_se"; break
            if hit in ("tr","bl"): cursor = "size_ne_sw"; break
            if hit == "move":      cursor = "fleur";      break
        self.canvas.config(cursor=cursor)

    def _stats_loop(self):
        while self._running:
            try:
                rp, op = analyse_housing(self.box_h.physical())
                bp     = analyse_villager(self.box_v.physical())
                self._stats = {"red": rp, "orange": op, "blue": bp}
            except Exception:
                pass
            time.sleep(0.5)

    def _refresh_ui(self):
        if not self._running: return
        s = self._stats
        rp = s["red"]; op = s["orange"]; bp = s["blue"]

        rc = C_RED    if rp >= 0.3 else (C_ORANGE if rp >= 0.1 else C_DIM)
        oc = C_ORANGE if op >= 0.4 else (C_GOLD   if op >= 0.1 else C_DIM)
        bc = C_BLUE   if bp >= 10  else C_DIM

        self._sv_red   .set(f"Red    : {rp:.3f}%  (need ≥0.30%)")
        self._sv_orange.set(f"Orange : {op:.3f}%  (need ≥0.40%)")
        self._sv_blue  .set(f"Blue px: {bp}  (need ≥10)")
        self._lbl_red   .config(fg=rc)
        self._lbl_orange.config(fg=oc)
        self._lbl_blue  .config(fg=bc)

        if rp >= 0.3:
            self._sv_status.set("HOUSING DANGER detected!")
            self._lbl_status.config(fg=C_RED)
        elif op >= 0.4:
            self._sv_status.set("HOUSING WARNING detected!")
            self._lbl_status.config(fg=C_ORANGE)
        elif bp >= 10:
            self._sv_status.set("IDLE VILLAGERS detected!")
            self._lbl_status.config(fg=C_BLUE)
        else:
            self._sv_status.set("● Monitoring... (in-game?)")
            self._lbl_status.config(fg=C_DIM)

        self.root.after(500, self._refresh_ui)

    def _save(self):
        h_reg = self.box_h.physical()
        v_reg = self.box_v.physical()
        ppv   = self.ppv
        raw   = self._vil_var.get().strip()
        if raw.isdigit() and int(raw) > 0:
            known = int(raw)
            arr = grab(v_reg)
            if arr.size > 0:
                r=arr[:,:,0].astype(int); g=arr[:,:,1].astype(int); b=arr[:,:,2].astype(int)
                blue_px = int(((b>140)&(b>r+25)&(b>g+15)).sum())
                if blue_px > 0:
                    ppv = blue_px / known
        try:
            save_calibration(self.sw, self.sh, h_reg, v_reg, ppv)
            self._btn_save.config(text="✓  Saved!", bg="#1a3a1a", fg=C_GREEN)
            self._sv_status.set("✓ Calibration saved!")
            self._lbl_status.config(fg=C_GREEN)
        except Exception as ex:
            self._btn_save.config(text="✗ Error saving", bg="#3a0a0a", fg=C_RED)
            self._sv_status.set(f"✗ {ex}")
            self._lbl_status.config(fg=C_RED)

    def _close(self):
        self._running = False
        try: self.root.destroy()
        except: pass

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        CalibrationApp().run()
    except Exception:
        err = traceback.format_exc()
        log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aoe4_calibrate_error.log")
        with open(log, "w") as f: f.write(err)
        print(err)
        input("\nPress ENTER to close...")