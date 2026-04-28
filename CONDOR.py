"""CONDOR v5.1"""

import os
import re
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk
import sys
import time
import tempfile
import shutil
import json
import winsound

try:
    import pystray
    from PIL import Image
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

DANGEROUS_PATHS = [
    "c:\\", "c:\\windows", "c:\\program files", "c:\\users",
    "c:\\program files (x86)", "c:\\system32",
]

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".condor_config.json")


def _load_txt(filename: str) -> str:
    """Busca un .txt junto al exe/script y lo devuelve como string."""
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(sys._MEIPASS, filename))
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(script_dir, filename))
    candidates.append(os.path.join(os.getcwd(), filename))
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                print(f"[CONDOR] Error leyendo {filename}: {e}")
    return f"Error: {filename} no encontrado junto a condor.py"


PROMPT_TEXT = _load_txt("prompt.txt")
MINIP_TEXT  = _load_txt("minip.txt")


class AutoBuilder:
    def __init__(self):
        self.root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
        self.root.title("CONDOR v5.1")
        self.root.configure(bg="#0d1117")
        self.root.resizable(True, True)

        self.config = self._load_config()
        self.root.geometry(self.config.get("geometry", "900x600"))

        self.project_path   = tk.StringVar(value=self.config.get("last_dir", ""))
        self.md_path        = tk.StringVar(value="")
        self.is_running     = False
        self.skip_current   = False
        self.stop_all       = False
        self.instructions   = []
        self.cmd_sep_var    = tk.BooleanVar(value=True)
        self.dry_run        = tk.BooleanVar(value=False)
        self.auto_run       = tk.BooleanVar(value=False)
        self.backup_enabled = tk.BooleanVar(value=True)
        self.undo_stack     = []

        self.active_process      = None
        self.active_process_lock = threading.Lock()

        self.tray_icon    = None
        self.tray_running = False

        self.spinner_chars   = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.spinner_idx     = 0
        self.spinner_running = False
        self.spinner_text    = ""

        self.temp_dir = tempfile.mkdtemp(prefix="condor_")

        self.icon_path = self._find_file("condor.ico")
        if self.icon_path:
            try:
                self.root.iconbitmap(self.icon_path)
            except Exception:
                pass

        self.style = ttk.Style()
        self.style.theme_use("clam")
        for prefix, bg, active, fg in [
            ("P", "#7c3aed", "#6d28d9", "white"),
            ("G", "#10b981", "#059669", "white"),
            ("R", "#ef4444", "#dc2626", "white"),
            ("Y", "#f59e0b", "#d97706", "black"),
            ("C", "#3b82f6", "#2563eb", "white"),
            ("W", "#64748b", "#475569", "white"),
            ("T", "#06b6d4", "#0891b2", "white"),
            ("O", "#f97316", "#ea580c", "white"),
        ]:
            self.style.configure(f"{prefix}.TButton",
                background=bg, foreground=fg,
                font=("Consolas", 8), padding=(6, 2))
            self.style.map(f"{prefix}.TButton",
                background=[("active", active), ("disabled", "#333")])

        self.style.configure("Dark.TCheckbutton",
            background="#161b22", foreground="#8b949e",
            font=("Consolas", 8))

        self._check_node()
        self._build_ui()
        self._setup_keybindings()
        self._setup_drag_drop()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─── Helpers ───────────────────────────────────────────────────────────

    def _find_file(self, filename: str):
        candidates = []
        if getattr(sys, "frozen", False):
            candidates.append(os.path.join(sys._MEIPASS, filename))
        candidates.append(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), filename))
        candidates.append(os.path.join(os.getcwd(), filename))
        for p in candidates:
            if os.path.isfile(p):
                return p
        return None

    def _load_pil_image(self):
        if self.icon_path and HAS_TRAY:
            try:
                return Image.open(self.icon_path).convert("RGBA").resize((64, 64))
            except Exception:
                pass
        if HAS_TRAY:
            return Image.new("RGBA", (64, 64), (124, 58, 237, 255))
        return None

    # ─── Config ────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"recent_dirs": [], "recent_mds": [],
                "geometry": "900x600", "last_dir": ""}

    def _save_config(self):
        try:
            self.config["geometry"] = self.root.geometry()
            self.config["last_dir"] = self.project_path.get()
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass

    def _add_recent(self, key: str, path: str):
        lst = self.config.setdefault(key, [])
        if path in lst:
            lst.remove(path)
        lst.insert(0, path)
        self.config[key] = lst[:10]
        self._save_config()

    # ─── Proceso activo ─────────────────────────────────────────────────────

    def _set_process(self, proc):
        with self.active_process_lock:
            self.active_process = proc

    def _kill_process(self):
        with self.active_process_lock:
            proc = self.active_process
            self.active_process = None
        if proc:
            try:
                proc.kill()
                proc.wait(timeout=3)
            except Exception:
                pass

    # ─── Bandeja ───────────────────────────────────────────────────────────

    def _on_close(self):
        self._save_config()
        menu = tk.Menu(self.root, tearoff=0,
            bg="#1e293b", fg="#e2e8f0",
            activebackground="#7c3aed", activeforeground="#fff",
            font=("Consolas", 9), relief="flat", bd=0)

        if HAS_TRAY:
            menu.add_command(
                label="  Minimizar a bandeja  ",
                command=self._hide_to_tray)

        menu.add_command(label="  Cerrar CONDOR  ", command=self._quit_app)
        menu.add_separator()
        menu.add_command(label="  Cancelar  ", command=menu.destroy)

        x = self.root.winfo_x() + self.root.winfo_width() - 180
        y = self.root.winfo_y() + 30
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _hide_to_tray(self):
        self.root.withdraw()
        if self.tray_running:
            return
        image = self._load_pil_image()
        menu  = pystray.Menu(
            pystray.MenuItem("Abrir CONDOR", self._cb_show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Cerrar CONDOR", self._cb_exit),
        )
        self.tray_icon    = pystray.Icon("condor", image, "CONDOR v5.1", menu)
        self.tray_running = True
        threading.Thread(target=self._tray_loop, daemon=True).start()

    def _tray_loop(self):
        try:
            self.tray_icon.run()
        finally:
            self.tray_running = False

    def _cb_show(self, icon, item):
        self.root.after(0, self._restore)

    def _restore(self):
        self._stop_tray()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _cb_exit(self, icon, item):
        self.root.after(0, self._quit_app)

    def _stop_tray(self):
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon    = None
            self.tray_running = False

    def _quit_app(self):
        self._save_config()
        self.stop_all     = True
        self.skip_current = True
        self._kill_process()
        self._stop_tray()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.root.destroy()

    # ─── Node ──────────────────────────────────────────────────────────────

    def _check_node(self):
        def run(cmd):
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True,
                                   text=True, timeout=5)
                return r.stdout.strip() if r.returncode == 0 else None
            except Exception:
                return None
        v = run("node --version")
        self.node_status = f"node {v}" if v else "node: NOT FOUND"
        v = run("npm --version")
        self.npm_status  = f"npm {v}"  if v else "npm: NOT FOUND"

    def _validate_path(self, path: str) -> bool:
        norm = os.path.normpath(path).lower()
        return not any(
            norm == os.path.normpath(d).lower() for d in DANGEROUS_PATHS)

    # ─── Keybindings ───────────────────────────────────────────────────────

    def _setup_keybindings(self):
        b = self.root.bind
        b("<Control-v>", lambda e: self.paste_from_clipboard())
        b("<Control-r>", lambda e: self.run_all())
        b("<Control-s>", lambda e: self.parse_md())
        b("<Control-z>", lambda e: self.undo_last())
        b("<Control-o>", lambda e: self.open_explorer())
        b("<Escape>",    lambda e: self.stop_execution())

    # ─── DnD ───────────────────────────────────────────────────────────────

    def _setup_drag_drop(self):
        if not HAS_DND:
            return
        try:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)
            self.log_msg("Drag & Drop enabled", "ok")
        except Exception as e:
            self.log_msg(f"DnD not available: {e}", "dim")

    def _on_drop(self, event):
        path = event.data.strip("{}").strip('"')
        if os.path.isdir(path):
            if not self._validate_path(path):
                messagebox.showerror("Error", "Dangerous path!")
                return
            self.project_path.set(path)
            self._add_recent("recent_dirs", path)
            self.log_msg(f"DROP DIR: {path}", "path")
        elif path.endswith(".md"):
            self.md_path.set(path)
            self._add_recent("recent_mds", path)
            self.log_msg(f"DROP .MD: {path}", "path")
            self.parse_md()
        else:
            self.log_msg(f"DROP: unsupported → {path}", "warn")

    # ─── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        top = tk.Frame(self.root, bg="#161b22", padx=6, pady=4)
        top.pack(fill="x")

        # Fila paths
        paths = tk.Frame(top, bg="#161b22")
        paths.pack(fill="x", pady=1)

        tk.Label(paths, text="DIR", font=("Consolas", 8, "bold"),
            fg="#7c3aed", bg="#161b22", width=3).pack(side="left")
        self.folder_entry = tk.Entry(paths, textvariable=self.project_path,
            font=("Consolas", 8), bg="#0d1117", fg="#e2e8f0",
            insertbackground="#7c3aed", relief="flat", bd=0)
        self.folder_entry.pack(side="left", fill="x", expand=True, ipady=2, ipadx=3)
        self._tip(self.folder_entry, "Carpeta raíz del proyecto")
        ttk.Button(paths, text="..", style="P.TButton", width=2,
            command=self.select_folder).pack(side="left", padx=1)

        tk.Label(paths, text="MD", font=("Consolas", 8, "bold"),
            fg="#3b82f6", bg="#161b22", width=2).pack(side="left", padx=(4, 0))
        self.md_entry = tk.Entry(paths, textvariable=self.md_path,
            font=("Consolas", 8), bg="#0d1117", fg="#e2e8f0",
            insertbackground="#3b82f6", relief="flat", bd=0)
        self.md_entry.pack(side="left", fill="x", expand=True, ipady=2, ipadx=3)
        self._tip(self.md_entry, "Archivo .md con instrucciones")
        ttk.Button(paths, text="..", style="C.TButton", width=2,
            command=self.select_md).pack(side="left", padx=1)

        # Fila botones
        btns = tk.Frame(top, bg="#161b22")
        btns.pack(fill="x", pady=2)

        left = tk.Frame(btns, bg="#161b22")
        left.pack(side="left")

        def lb(text, style, cmd, tip, attr=None):
            b = ttk.Button(left, text=text, style=style, command=cmd)
            b.pack(side="left", padx=1)
            self._tip(b, tip)
            if attr:
                setattr(self, attr, b)

        lb("SCAN",  "P.TButton", self.parse_md,             "Analizar .md (Ctrl+S)")
        lb("RUN",   "G.TButton", self.run_all,              "Ejecutar todo (Ctrl+R)",    "run_btn")
        lb("SKIP",  "Y.TButton", self.skip_instruction,     "Saltar instrucción actual", "skip_btn")
        lb("STOP",  "R.TButton", self.stop_execution,       "Detener todo (Esc)",        "stop_btn")
        tk.Frame(left, bg="#30363d", width=1, height=16).pack(side="left", padx=4)
        lb("PASTE", "T.TButton", self.paste_from_clipboard, "Pegar .md (Ctrl+V)")
        lb("UNDO",  "O.TButton", self.undo_last,            "Deshacer último cambio (Ctrl+Z)")

        self.run_btn.state(["disabled"])
        self.skip_btn.state(["disabled"])
        self.stop_btn.state(["disabled"])

        right = tk.Frame(btns, bg="#161b22")
        right.pack(side="right")

        def rb(text, style, cmd, tip):
            b = ttk.Button(right, text=text, style=style, command=cmd)
            b.pack(side="right", padx=1)
            self._tip(b, tip)

        rb("PROMPT", "W.TButton", self.copy_prompt,  "Copiar instrucciones para IA")
        rb("CMD",    "C.TButton", self.open_cmd,      "Abrir terminal CMD")
        rb("OPEN",   "C.TButton", self.open_explorer, "Abrir en Explorer (Ctrl+O)")
        rb("CLR",    "P.TButton", self.clear_log,     "Limpiar log")

        # Fila checkboxes
        opts = tk.Frame(top, bg="#161b22")
        opts.pack(fill="x", pady=1)

        for text, var in [
            ("Auto-run", self.auto_run),
            ("Dry-run",  self.dry_run),
            ("Backup",   self.backup_enabled),
            ("CMD SEP",  self.cmd_sep_var),
        ]:
            ttk.Checkbutton(opts, text=text, variable=var,
                style="Dark.TCheckbutton").pack(side="left", padx=4)

        self.stats_label = tk.Label(opts, text="", font=("Consolas", 7),
            fg="#64748b", bg="#161b22")
        self.stats_label.pack(side="right", padx=4)

        # Barra de progreso
        self.progress_bar = tk.Canvas(self.root, height=3,
            bg="#161b22", highlightthickness=0)
        self.progress_bar.pack(fill="x")

        # Log
        self.log = scrolledtext.ScrolledText(self.root,
            font=("Consolas", 9), bg="#0d1117", fg="#e2e8f0",
            insertbackground="#7c3aed", relief="flat", bd=0,
            wrap="word", state="disabled", padx=8, pady=4)
        self.log.pack(fill="both", expand=True)

        # Barra de estado
        status = tk.Frame(self.root, bg="#161b22", height=18)
        status.pack(fill="x", side="bottom")

        self.status_label = tk.Label(status, text="Ready",
            font=("Consolas", 7), fg="#10b981", bg="#161b22")
        self.status_label.pack(side="left", padx=4)

        tk.Label(status, text=f"{self.node_status} | {self.npm_status}",
            font=("Consolas", 7), fg="#30363d", bg="#161b22").pack(side="right", padx=4)

        hint = "[X]=menu" if HAS_TRAY else ""
        tk.Label(status,
            text=f"Ctrl+V=paste  Ctrl+R=run  Esc=stop  {hint}",
            font=("Consolas", 7), fg="#21262d", bg="#161b22").pack(side="right", padx=8)

        # ── Botón secreto P (mini prompt) ──────────────────────────────────
        p_btn = tk.Label(status, text="p",
            font=("Consolas", 7, "bold"),
            fg="#21262d", bg="#161b22",
            cursor="hand2", padx=6, pady=1)
        p_btn.pack(side="right", padx=(0, 2))
        p_btn.bind("<Button-1>", lambda e: self._copy_minip())
        p_btn.bind("<Enter>",    lambda e: p_btn.config(fg="#7c3aed"))
        p_btn.bind("<Leave>",    lambda e: p_btn.config(fg="#21262d"))
        self._tip(p_btn, "Mini prompt compacto")

        # Tags de color
        for tag, color, bold in [
            ("ok",          "#10b981", False),
            ("err",         "#ef4444", False),
            ("warn",        "#f59e0b", False),
            ("info",        "#3b82f6", False),
            ("cmd",         "#7c3aed", False),
            ("path",        "#06b6d4", False),
            ("head",        "#7c3aed", True),
            ("dim",         "#30363d", False),
            ("white",       "#e2e8f0", False),
            ("interactive", "#f59e0b", True),
            ("replace",     "#06b6d4", True),
            ("dry",         "#f59e0b", True),
            ("undo",        "#f97316", True),
            ("block",       "#a78bfa", True),
        ]:
            font = ("Consolas", 9, "bold") if bold else ("Consolas", 9)
            self.log.tag_configure(tag, foreground=color, font=font)

    def _tip(self, widget, text: str):
        tip = None
        def enter(e):
            nonlocal tip
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + widget.winfo_height() + 2
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tk.Label(tip, text=text, font=("Consolas", 8),
                bg="#1f2937", fg="#e2e8f0", padx=6, pady=2).pack()
        def leave(e):
            nonlocal tip
            if tip:
                tip.destroy()
                tip = None
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    # ─── Progreso ──────────────────────────────────────────────────────────

    def _update_progress(self, current: int, total: int):
        self.progress_bar.delete("all")
        if total <= 0:
            return
        w  = self.progress_bar.winfo_width()
        fw = int((current / total) * w)
        self.progress_bar.create_rectangle(0, 0, fw, 3, fill="#7c3aed", outline="")

    def _reset_progress(self):
        self.progress_bar.delete("all")

    # ─── Spinner ───────────────────────────────────────────────────────────

    def start_spinner(self, text: str = "Processing"):
        self.spinner_running = True
        self.spinner_text    = text
        self._tick_spinner()

    def _tick_spinner(self):
        if not self.spinner_running:
            return
        c = self.spinner_chars[self.spinner_idx % len(self.spinner_chars)]
        self.spinner_idx += 1
        self.status_label.config(text=f"{c} {self.spinner_text}")
        self.root.after(100, self._tick_spinner)

    def stop_spinner(self):
        self.spinner_running = False
        self.status_label.config(text="Ready")

    # ─── Log ───────────────────────────────────────────────────────────────

    def log_msg(self, msg: str, tag: str = "white"):
        self.log.configure(state="normal")
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > 600:
            self.log.delete("1.0", f"{lines - 500}.0")
        self.log.insert("end", msg + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.stats_label.config(text="")
        self._reset_progress()

    # ─── Audio ─────────────────────────────────────────────────────────────

    def _beep(self, success: bool = True):
        try:
            winsound.MessageBeep(
                winsound.MB_OK if success else winsound.MB_ICONHAND)
        except Exception:
            pass

    def _notify(self, title: str, msg: str):
        if HAS_TRAY and self.tray_icon and self.tray_running:
            try:
                self.tray_icon.notify(title, msg)
            except Exception:
                pass

    # ─── Backup / Undo ─────────────────────────────────────────────────────

    def _backup(self, filepath: str):
        if not self.backup_enabled.get() or not os.path.exists(filepath):
            return
        bdir = os.path.join(self.temp_dir, "backups")
        os.makedirs(bdir, exist_ok=True)
        ts  = int(time.time() * 1000)
        dst = os.path.join(bdir, f"{ts}_{os.path.basename(filepath)}")
        shutil.copy2(filepath, dst)
        self.undo_stack.append({"original": filepath, "backup": dst})
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def undo_last(self):
        if not self.undo_stack:
            self.log_msg("UNDO: nothing to undo", "warn")
            return
        entry = self.undo_stack.pop()
        try:
            shutil.copy2(entry["backup"], entry["original"])
            self.log_msg(
                f"UNDO: restored {os.path.basename(entry['original'])}", "undo")
        except Exception as e:
            self.log_msg(f"UNDO ERROR: {e}", "err")

    # ─── Botones ───────────────────────────────────────────────────────────

    def select_folder(self):
        path = filedialog.askdirectory(title="Project root folder")
        if not path:
            return
        if not self._validate_path(path):
            messagebox.showerror("Error", "Dangerous path!")
            return
        self.project_path.set(path)
        self._add_recent("recent_dirs", path)
        self.log_msg(f"DIR: {path}", "path")

    def select_md(self):
        path = filedialog.askopenfilename(title=".md file",
            filetypes=[("Markdown", "*.md"), ("All", "*.*")])
        if not path:
            return
        self.md_path.set(path)
        self._add_recent("recent_mds", path)
        self.log_msg(f".MD: {path}", "path")

    def open_cmd(self):
        p = self.project_path.get()
        if not p or not os.path.isdir(p):
            messagebox.showerror("Error", "Select a valid project folder first")
            return
        subprocess.Popen(f'start cmd /k "cd /d {p}"', shell=True)
        self.log_msg(f"CMD: {p}", "ok")

    def open_explorer(self):
        p = self.project_path.get()
        if not p or not os.path.isdir(p):
            messagebox.showerror("Error", "Select a valid project folder first")
            return
        os.startfile(p)
        self.log_msg(f"OPEN: {p}", "ok")

    def copy_prompt(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(PROMPT_TEXT)
        self.root.update()
        self.log_msg("PROMPT copied to clipboard!", "ok")

    def _copy_minip(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(MINIP_TEXT)
        self.root.update()
        self.log_msg("Mini prompt copied!", "ok")

    def skip_instruction(self):
        if not self.is_running:
            return
        self.skip_current = True
        self.log_msg(">> SKIPPING...", "warn")
        self._kill_process()

    def stop_execution(self):
        if not self.is_running:
            return
        self.stop_all     = True
        self.skip_current = True
        self.log_msg(">> STOPPING...", "err")
        self._kill_process()

    def paste_from_clipboard(self):
        try:
            clipboard = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showerror("Error", "Clipboard is empty")
            return
        if not clipboard.strip():
            return
        p = self.project_path.get()
        if not p or not os.path.isdir(p):
            messagebox.showerror("Error", "Select DIR first")
            return
        tmp = os.path.join(self.temp_dir, f"paste_{int(time.time())}.md")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(clipboard)
        self.md_path.set(tmp)
        self.log_msg(f"PASTE: {len(clipboard)} chars", "ok")
        self.parse_md()

    # ─── Editor de instrucciones ────────────────────────────────────────────

    def _edit_instruction(self, index: int):
        if index < 0 or index >= len(self.instructions):
            return

        inst = self.instructions[index]

        win = tk.Toplevel(self.root)
        win.title(f"Edit [{index+1}] {inst['action']} — {inst['filepath']}")
        win.geometry("600x400")
        win.configure(bg="#0d1117")
        win.transient(self.root)
        win.grab_set()

        top = tk.Frame(win, bg="#161b22", padx=8, pady=6)
        top.pack(fill="x")

        tk.Label(top,
            text=f"{inst['action']}  →  {inst['filepath']}",
            font=("Consolas", 9, "bold"),
            fg="#7c3aed", bg="#161b22").pack(side="left")

        def save():
            self.instructions[index]["content"] = editor.get("1.0", "end-1c").strip()
            self.log_msg(f"  EDITED [{index+1}] {inst['filepath']}", "undo")
            win.destroy()
            self._display_instructions()

        def cancel():
            win.destroy()

        def delete():
            self.instructions.pop(index)
            self.log_msg(f"  REMOVED [{index+1}] {inst['filepath']}", "warn")
            win.destroy()
            self._display_instructions()

        ttk.Button(top, text="ELIMINAR", style="R.TButton",
            command=delete).pack(side="right", padx=2)
        ttk.Button(top, text="CANCELAR", style="W.TButton",
            command=cancel).pack(side="right", padx=2)
        ttk.Button(top, text="GUARDAR", style="G.TButton",
            command=save).pack(side="right", padx=2)

        editor = scrolledtext.ScrolledText(win,
            font=("Consolas", 10), bg="#161b22", fg="#e2e8f0",
            insertbackground="#7c3aed", relief="flat", bd=0,
            wrap="none", padx=8, pady=8)
        editor.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        editor.insert("1.0", inst["content"])
        editor.focus_set()

    def _on_log_double_click(self, event):
        if self.is_running or not self.instructions:
            return
        index    = self.log.index(f"@{event.x},{event.y}")
        line_num = int(index.split(".")[0])
        self.log.configure(state="normal")
        line_text = self.log.get(f"{line_num}.0", f"{line_num}.end").strip()
        self.log.configure(state="disabled")
        m = re.match(r'^\s*(\d+)\.', line_text)
        if m:
            inst_idx = int(m.group(1)) - 1
            if 0 <= inst_idx < len(self.instructions):
                self._edit_instruction(inst_idx)

    def _display_instructions(self):
        self.clear_log()
        self.log_msg("=" * 50, "dim")
        self.log_msg("INSTRUCTIONS — double-click to edit", "head")
        self.log_msg("=" * 50, "dim")

        if not self.instructions:
            self.log_msg("No instructions", "warn")
            self.run_btn.state(["disabled"])
            return

        counts: dict[str, int] = {}
        for inst in self.instructions:
            counts[inst["action"]] = counts.get(inst["action"], 0) + 1

        self.log_msg(f"Found: {len(self.instructions)} instructions", "info")
        for a, c in counts.items():
            self.log_msg(f"  {a}: {c}", "info")
        self.log_msg("")

        for i, inst in enumerate(self.instructions):
            a = inst["action"]
            if a == "EJECUTAR":
                preview = inst["content"].replace("\n", " | ")[:60]
                self.log_msg(f"  {i+1:02d}. EXEC  {preview}...", "cmd")
            elif a == "ELIMINAR":
                self.log_msg(f"  {i+1:02d}. DEL   {inst['filepath']}", "warn")
            elif a == "REEMPLAZAR":
                self.log_msg(f"  {i+1:02d}. REPL  {inst['filepath']}", "replace")
            else:
                n   = inst["content"].count("\n") + 1
                act = "NEW" if a == "CREAR" else "MOD"
                self.log_msg(f"  {i+1:02d}. {act}   {inst['filepath']} ({n}L)", "cmd")

        self.log_msg("")
        self.log_msg("Double-click to edit. Press RUN to execute.", "ok")
        self.stats_label.config(
            text=" | ".join(f"{a}:{c}" for a, c in counts.items()))
        self.run_btn.state(["!disabled"])

    # ─── Parse ─────────────────────────────────────────────────────────────

    def parse_md(self):
        md_file = self.md_path.get()
        if not md_file or not os.path.exists(md_file):
            messagebox.showerror("Error", "Select a valid .md file")
            return
        project = self.project_path.get()
        if not project or not os.path.isdir(project):
            messagebox.showerror("Error", "Select a valid folder")
            return
        if not self._validate_path(project):
            messagebox.showerror("Error", "Dangerous path!")
            return

        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self.log_msg(f"Error reading file: {e}", "err")
            return

        self.instructions = self._extract(content)
        self._display_instructions()
        self.log.bind("<Double-Button-1>", self._on_log_double_click)

        if self.auto_run.get() and self.instructions:
            self.run_all()

    # ─── Extractor ─────────────────────────────────────────────────────────

    def _extract(self, content: str) -> list:
        """
        Parser INICIO_BLOQUE / FIN_BLOQUE.
        - Salta fence lines entre ETIQUETA e INICIO_BLOQUE
        - Elimina fence lines del contenido final
        - FIN_BLOQUE solo cierra si está en columna 0
        """
        instructions = []
        lines        = content.split("\n")
        i            = 0

        while i < len(lines):
            stripped = lines[i].strip()

            m = re.match(r'^ETIQUETA\[([^\]]+)\]\s*$', stripped)
            if not m:
                i += 1
                continue

            params_str = m.group(1)
            params     = [p.strip() for p in params_str.split(",")]

            if len(params) != 4:
                self.log_msg(
                    f"  WARN: ETIQUETA inválida ({len(params)} params): [{params_str}]",
                    "warn")
                i += 1
                continue

            # Buscar INICIO_BLOQUE saltando vacías y fence lines
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if s == "" or re.match(r'^`{3,}\w*\s*$', s):
                    j += 1
                    continue
                break

            if j >= len(lines) or lines[j].strip() != "INICIO_BLOQUE":
                self.log_msg(
                    f"  WARN: sin INICIO_BLOQUE → [{params_str}]", "warn")
                i += 1
                continue

            # Acumular hasta FIN_BLOQUE en columna 0
            k          = j + 1
            code_lines = []
            found      = False

            while k < len(lines):
                if lines[k].rstrip() == "FIN_BLOQUE":
                    found = True
                    break
                code_lines.append(lines[k])
                k += 1

            if not found:
                self.log_msg(
                    f"  WARN: FIN_BLOQUE no encontrado → [{params_str}]", "warn")
                i += 1
                continue

            # Eliminar fence lines del contenido
            final = [cl for cl in code_lines
                     if not re.match(r'^\s*`{3,}\w*\s*$', cl)]
            code  = "\n".join(final).strip()

            ubicacion, nombre, extension, accion = params
            accion = accion.upper().strip()

            if accion == "EJECUTAR" or nombre.lower() == "nan":
                filepath = "CMD"
            elif ubicacion == ".":
                filepath = f"{nombre}.{extension}"
            else:
                filepath = f"{ubicacion}/{nombre}.{extension}"

            instructions.append({
                "ubicacion": ubicacion, "nombre":   nombre,
                "extension": extension, "action":   accion,
                "language":  "",        "content":  code,
                "filepath":  filepath,
            })

            i = k + 1

        return instructions

    # ─── Ejecución ─────────────────────────────────────────────────────────

    def run_all(self):
        if self.is_running or not self.instructions:
            return
        mode = "DRY-RUN" if self.dry_run.get() else "EXECUTE"
        if not messagebox.askyesno("Confirm",
                f"{mode}: {len(self.instructions)} instructions\n"
                f"Project: {self.project_path.get()}\n\nContinue?"):
            return

        self.is_running   = True
        self.stop_all     = False
        self.skip_current = False
        self.run_btn.state(["disabled"])
        self.skip_btn.state(["!disabled"])
        self.stop_btn.state(["!disabled"])
        self.start_spinner("Executing")
        threading.Thread(target=self._execute_all, daemon=True).start()

    def _execute_all(self):
        project = self.project_path.get()
        total   = len(self.instructions)
        ok = err = skip = 0

        self.log_msg("")
        self.log_msg("=" * 50, "dim")
        self.log_msg("DRY-RUN" if self.dry_run.get() else "EXECUTING", "head")
        self.log_msg("=" * 50, "dim")

        for i, inst in enumerate(self.instructions, 1):
            if self.stop_all:
                self.log_msg(f"STOPPED at [{i}/{total}]", "err")
                break

            self.skip_current = False
            action            = inst["action"]
            self.spinner_text = f"[{i}/{total}] {action}"
            self.root.after(0, lambda c=i, t=total: self._update_progress(c, t))
            self.log_msg(f"--- [{i}/{total}] {action} ---", "dim")

            try:
                if self.dry_run.get():
                    if action == "EJECUTAR":
                        self.log_msg(
                            f"  [DRY] Would execute: "
                            f"{inst['content'].replace(chr(10), ' | ')[:60]}...", "dry")
                    else:
                        self.log_msg(
                            f"  [DRY] Would {action}: {inst['filepath']}", "dry")
                    ok += 1
                    continue

                if action == "EJECUTAR":
                    self._exec_cmd(project, inst["content"])
                elif action in ("CREAR", "MODIFICAR"):
                    self._backup(os.path.join(
                        project, inst["filepath"].replace("/", os.sep)))
                    self._create_file(project, inst)
                elif action == "ELIMINAR":
                    self._backup(os.path.join(
                        project, inst["filepath"].replace("/", os.sep)))
                    self._delete_file(project, inst)
                elif action == "REEMPLAZAR":
                    self._backup(os.path.join(
                        project, inst["filepath"].replace("/", os.sep)))
                    self._replace_in_file(project, inst)
                else:
                    self.log_msg(f"  Unknown action: {action}", "warn")
                    continue

                if self.skip_current:
                    skip += 1
                else:
                    ok += 1

            except Exception as e:
                err += 1
                self.log_msg(f"  ERROR: {e}", "err")

        self.log_msg("")
        self.log_msg("=" * 50, "dim")
        self.log_msg(f"OK:{ok} ERR:{err} SKIP:{skip} TOTAL:{total}", "head")
        self.log_msg("=" * 50, "dim")

        if err == 0 and not self.stop_all:
            self.log_msg("Done!", "ok")
            self.root.after(0, lambda: self._beep(True))
            self._notify("CONDOR", "Execution completed!")
        elif self.stop_all:
            self.log_msg("Stopped by user", "warn")
        else:
            self.log_msg(f"Done with {err} errors", "warn")
            self.root.after(0, lambda: self._beep(False))
            self._notify("CONDOR", f"Completed with {err} errors")

        self.root.after(0, self._finish)

    def _finish(self):
        self.is_running   = False
        self.stop_all     = False
        self.skip_current = False
        self.stop_spinner()
        self.run_btn.state(["!disabled"])
        self.skip_btn.state(["disabled"])
        self.stop_btn.state(["disabled"])

    # ─── Archivos ──────────────────────────────────────────────────────────

    def _create_file(self, project: str, inst: dict):
        filepath = inst["filepath"]
        content  = inst["content"]
        full     = os.path.join(project, filepath.replace("/", os.sep))
        dir_path = os.path.dirname(full)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content + "\n")
        n   = content.count("\n") + 1
        act = "NEW" if inst["action"] == "CREAR" else "MOD"
        self.log_msg(f"  {act}: {filepath} ({n}L)", "ok")

    def _delete_file(self, project: str, inst: dict):
        filepath = inst["filepath"]
        full     = os.path.join(project, filepath.replace("/", os.sep))
        if os.path.exists(full):
            os.remove(full)
            self.log_msg(f"  DEL: {filepath}", "warn")
        else:
            self.log_msg(f"  NOT FOUND: {filepath}", "warn")

    def _replace_in_file(self, project: str, inst: dict):
        filepath = inst["filepath"]
        content  = inst["content"]
        full     = os.path.join(project, filepath.replace("/", os.sep))

        if not os.path.exists(full):
            self.log_msg(f"  REPL ERR: not found → {filepath}", "err")
            return
        if ">>>" not in content:
            self.log_msg("  REPL ERR: missing >>> separator", "err")
            return

        parts     = content.split(">>>", 1)
        search    = parts[0].rstrip("\n")
        replace   = parts[1].lstrip("\n")

        if not search.strip():
            self.log_msg("  REPL ERR: empty search text", "err")
            return

        with open(full, "r", encoding="utf-8") as f:
            fc = f.read()

        # ── Intento 1: búsqueda exacta tal cual ──
        if search in fc:
            fc = fc.replace(search, replace, 1)
            self._write_and_log(full, fc, filepath, search, replace)
            return

        # ── Intento 2: normalizar tabs → espacios ──
        def norm(t):
            return t.replace("\t", "    ")

        nfc = norm(fc)
        nsr = norm(search)

        if nsr in nfc:
            fc = nfc.replace(nsr, replace, 1)
            self._write_and_log(full, fc, filepath, search, replace)
            return

        # ── Intento 3: búsqueda línea por línea con strip ──
        search_lines = [l.strip() for l in search.split("\n") if l.strip()]
        fc_lines     = fc.split("\n")

        if len(search_lines) == 0:
            self.log_msg("  REPL ERR: empty search text", "err")
            return

        # Buscar la primera línea del search en el archivo
        found = False
        for start_idx in range(len(fc_lines)):
            # Verificar si desde start_idx coinciden todas las líneas del search
            if fc_lines[start_idx].strip() == search_lines[0]:
                # Una sola línea de búsqueda
                if len(search_lines) == 1:
                    replace_lines = replace.split("\n")
                    fc_lines = fc_lines[:start_idx] + replace_lines + fc_lines[start_idx + 1:]
                    found = True
                    break

                # Múltiples líneas: verificar que todas coincidan
                match = True
                matched = 0
                fi = start_idx

                for si in range(len(search_lines)):
                    # Avanzar en fc saltando líneas vacías
                    while fi < len(fc_lines) and fc_lines[fi].strip() == "" and search_lines[si] != "":
                        fi += 1

                    if fi >= len(fc_lines):
                        match = False
                        break

                    if fc_lines[fi].strip() != search_lines[si]:
                        match = False
                        break

                    fi += 1
                    matched += 1

                if match and matched == len(search_lines):
                    # Encontrado: reemplazar desde start_idx hasta fi
                    replace_lines = replace.split("\n")
                    fc_lines = fc_lines[:start_idx] + replace_lines + fc_lines[fi:]
                    found = True
                    break

        if found:
            fc = "\n".join(fc_lines)
            self._write_and_log(full, fc, filepath, search, replace)
            return

        # ── Intento 4: búsqueda parcial de la primera línea ──
        first_search = search_lines[0]
        for idx, line in enumerate(fc_lines):
            if first_search in line.strip() or line.strip() in first_search:
                if len(first_search) >= 5 and len(line.strip()) >= 5:
                    # Match parcial de una línea
                    if len(search_lines) == 1:
                        replace_lines = replace.split("\n")
                        fc_lines = fc_lines[:idx] + replace_lines + fc_lines[idx + 1:]
                        fc = "\n".join(fc_lines)
                        self._write_and_log(full, fc, filepath, search, replace)
                        self.log_msg("    (partial match)", "warn")
                        return

        # ── Nada funcionó ──
        self.log_msg(f"  REPL ERR: text not found in {filepath}", "err")
        self.log_msg(f"    search: {search.split(chr(10))[0][:60]}...", "dim")

    def _write_and_log(self, full: str, content: str, filepath: str,
                       search: str, replace: str):
        """Escribe el archivo y muestra el resultado en el log."""
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        self.log_msg(f"  REPL: {filepath}", "replace")
        self.log_msg(f"    - {search.split(chr(10))[0][:50]}", "dim")
        self.log_msg(f"    + {replace.split(chr(10))[0][:50]}", "ok")

    # ─── CMD ───────────────────────────────────────────────────────────────

    def _is_interactive(self, cmd: str) -> bool:
        c = cmd.lower().strip()
        return (c.startswith("npm ") or c.startswith("npx ") or
                c.startswith("python") or c.startswith("py ") or
                c.startswith("node "))

    def _normalize_create_cmd(self, cmd: str) -> str:
        """Convierte variantes de create vite a la forma silenciosa."""
        c = cmd.lower().strip()
        if any(x in c for x in [
            "npm init vite", "npm create vite",
            "npx create-vite", "npx init vite"
        ]):
            template = "react"
            if "--template" in c:
                idx  = c.index("--template")
                rest = cmd[idx + len("--template"):].strip()
                template = rest.split()[0] if rest.split() else "react"
            return f"npx create-vite@latest . --template {template} --yes"

        if "create-next-app" in c:
            if "--yes" not in c and "-y" not in c:
                return cmd + " --yes"

        return cmd

    def _exec_cmd(self, project: str, commands: str):
        lines = [l.strip() for l in commands.strip().split("\n")
                 if l.strip() and not l.strip().startswith("#")]

        for cmd in lines:
            if self.stop_all:
                self.log_msg(f"  STOP: {cmd}", "err")
                break
            if self.skip_current:
                self.log_msg(f"  SKIP: {cmd}", "warn")
                continue

            cmd = self._normalize_create_cmd(cmd)

            # CMD SEP
            if self.cmd_sep_var.get() and self._is_interactive(cmd):
                self.log_msg(f"  [CMD SEP] {cmd}", "interactive")
                try:
                    proc = subprocess.Popen(
                        f'start /wait cmd /k "'
                        f'title CONDOR: {cmd} && '
                        f'echo ======================================== && '
                        f'echo  CONDOR ejecutando: && '
                        f'echo  {cmd} && '
                        f'echo ======================================== && echo. && '
                        f'cd /d "{project}" && {cmd} && echo. && '
                        f'echo ======================================== && '
                        f'echo  LISTO - puedes cerrar esta ventana && '
                        f'echo ========================================"',
                        shell=True, cwd=project)

                    self._set_process(proc)

                    while proc.poll() is None:
                        if self.stop_all or self.skip_current:
                            self._kill_process()
                            self.log_msg("  Process killed.", "warn")
                            break
                        time.sleep(0.2)

                    self._set_process(None)

                    if not self.skip_current and not self.stop_all:
                        self.log_msg("  Window closed. Continuing...", "ok")

                except Exception as e:
                    self.log_msg(f"  Error: {e}", "err")
                    self._set_process(None)
                continue

            # Inline
            self.log_msg(f"  > {cmd}", "cmd")
            self.spinner_text = cmd[:40]

            try:
                proc = subprocess.Popen(
                    cmd, shell=True, cwd=project,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True, bufsize=1)

                self._set_process(proc)

                out_count = 0
                while True:
                    if self.stop_all or self.skip_current:
                        self._kill_process()
                        self.log_msg("    Process killed.", "warn")
                        break

                    line = proc.stdout.readline()
                    if line:
                        clean = line.rstrip()
                        if clean and out_count < 8:
                            self.log_msg(f"    {clean}", "info")
                            out_count += 1
                    elif proc.poll() is not None:
                        break
                    else:
                        time.sleep(0.05)

                if not self.skip_current and not self.stop_all:
                    try:
                        stderr = proc.stderr.read()
                    except Exception:
                        stderr = ""
                    rc = proc.returncode if proc.returncode is not None else -1

                    if rc != 0 and stderr and stderr.strip():
                        tag = "warn" if ("warn" in stderr.lower()
                                         or "notice" in stderr.lower()) else "err"
                        for ln in stderr.strip().split("\n")[:4]:
                            self.log_msg(f"    {ln[:100]}", tag)

                    self.log_msg(
                        f"    {'OK' if rc == 0 else f'exit:{rc}'}",
                        "ok" if rc == 0 else "warn")

                self._set_process(None)

            except Exception as e:
                self.log_msg(f"    Error: {e}", "err")
                self._set_process(None)

    # ─── Entry point ───────────────────────────────────────────────────────

    def run(self):
        self.log_msg("CONDOR v5.1", "head")
        self.log_msg(f"{self.node_status} | {self.npm_status}", "info")
        self.log_msg(
            "Ctrl+V=paste  Ctrl+R=run  Ctrl+S=scan  "
            "Ctrl+Z=undo  Ctrl+O=open  Esc=stop", "dim")
        self.log_msg(
            "ETIQUETA → INICIO_BLOQUE → ```contenido``` → FIN_BLOQUE", "block")
        if PROMPT_TEXT.startswith("Error:"):
            self.log_msg(PROMPT_TEXT, "err")
        self.log_msg("")
        self.root.mainloop()


if __name__ == "__main__":
    app = AutoBuilder()
    app.run()