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

# ─────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────

INTERACTIVE_COMMANDS = [
    "npm create", "npx create", "npm init", "npx init",
    "npm run dev", "npm start", "npm test",
    "python", "py ", "node ", "npx prisma studio",
]

DANGEROUS_PATHS = [
    "c:\\", "c:\\windows", "c:\\program files", "c:\\users",
    "c:\\program files (x86)", "c:\\system32",
]

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".condor_config.json")

PROMPT_TEXT = """# Sistema CONDOR — Instrucciones para el asistente

Estoy usando **CONDOR**, un automatizador que lee archivos `.md` y ejecuta las instrucciones que contienen. Necesito que tus respuestas sigan este formato para que CONDOR pueda procesarlas automáticamente.

## Formato de ETIQUETAS

Antes de cada bloque de código debes agregar una línea con este formato exacto:

```
ETIQUETA[ubicacion,nombre,extension,accion]
```

### Parámetros:
- **ubicacion**: ruta relativa desde la raíz del proyecto (usar `.` para la raíz)
- **nombre**: nombre del archivo sin extensión (usar `nan` si no aplica, como en comandos)
- **extension**: extensión del archivo (js, jsx, css, html, py, cmd, etc.)
- **accion**: una de estas → `CREAR` | `MODIFICAR` | `EJECUTAR` | `ELIMINAR` | `REEMPLAZAR`

### Acciones:
- **CREAR** → Crea un archivo nuevo con el contenido del bloque de código
- **MODIFICAR** → Reemplaza TODO el contenido de un archivo existente
- **EJECUTAR** → Ejecuta los comandos en la terminal CMD de Windows 10
- **ELIMINAR** → Elimina el archivo indicado
- **REEMPLAZAR** → Busca texto exacto en el archivo y lo sustituye por otro

### Reglas del REEMPLAZAR:
- Usar `>>>` en una línea sola como separador entre ORIGINAL y NUEVO
- La parte ANTES de `>>>` es el texto exacto a buscar en el archivo
- La parte DESPUÉS de `>>>` es el texto que lo reemplaza

## Reglas importantes
1. La línea ETIQUETA[...] debe estar SOLA en su propia línea, justo antes del bloque de código
2. Para comandos usar ETIQUETA[.,nan,cmd,EJECUTAR] con bloque bash
3. Separar comandos interactivos en su propio bloque EJECUTAR
4. Para cambios pequeños preferir REEMPLAZAR sobre MODIFICAR
5. Trabajo con Windows 10 y CMD

Por favor, sigue este formato en todas tus respuestas. Gracias!"""


# ─────────────────────────────────────────────
# Clase principal
# ─────────────────────────────────────────────

class AutoBuilder:
    def __init__(self):
        self.root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
        self.root.title("CONDOR v3.0")
        self.root.configure(bg="#0d1117")
        self.root.resizable(True, True)

        # Cargar config (tamaño ventana, recientes)
        self.config = self.load_config()
        geo = self.config.get("geometry", "900x600")
        self.root.geometry(geo)

        # Estado
        self.project_path = tk.StringVar(value=self.config.get("last_dir", ""))
        self.md_path = tk.StringVar(value="")
        self.is_running = False
        self.skip_current = False
        self.stop_all = False
        self.instructions = []
        self.dry_run = tk.BooleanVar(value=False)
        self.auto_run = tk.BooleanVar(value=False)
        self.backup_enabled = tk.BooleanVar(value=True)
        self.undo_stack = []

        # Bandeja
        self.tray_icon = None
        self.tray_running = False

        # Spinner
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.spinner_idx = 0
        self.spinner_running = False
        self.spinner_text = ""

        # Temp
        self.temp_dir = tempfile.mkdtemp(prefix="condor_")

        # Icono
        self.icon_path = self._find_icon()
        if self.icon_path:
            try:
                self.root.iconbitmap(self.icon_path)
            except:
                pass

        # Estilos
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self._def_btn("P", "#7c3aed", "#6d28d9")
        self._def_btn("G", "#10b981", "#059669")
        self._def_btn("R", "#ef4444", "#dc2626")
        self._def_btn("Y", "#f59e0b", "#d97706", fg="black")
        self._def_btn("C", "#3b82f6", "#2563eb")
        self._def_btn("W", "#64748b", "#475569")
        self._def_btn("T", "#06b6d4", "#0891b2")
        self._def_btn("O", "#f97316", "#ea580c")

        # Checkbutton style
        self.style.configure("Dark.TCheckbutton",
            background="#161b22", foreground="#8b949e",
            font=("Consolas", 8))

        self.check_node()
        self.build_ui()
        self.setup_keybindings()
        self.setup_drag_drop()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", self._on_resize)

    # ─── Helpers ───

    def _def_btn(self, prefix, bg, active_bg, fg="white"):
        self.style.configure(f"{prefix}.TButton",
            background=bg, foreground=fg,
            font=("Consolas", 8), padding=(6, 2))
        self.style.map(f"{prefix}.TButton",
            background=[("active", active_bg), ("disabled", "#333")])

    def _find_icon(self):
        candidates = []
        if getattr(sys, "frozen", False):
            candidates.append(os.path.join(sys._MEIPASS, "condor.ico"))
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(script_dir, "condor.ico"))
        for p in candidates:
            if os.path.isfile(p):
                return p
        return None

    def _load_pil_image(self):
        if self.icon_path and HAS_TRAY:
            try:
                return Image.open(self.icon_path).convert("RGBA").resize((64, 64))
            except:
                pass
        if HAS_TRAY:
            return Image.new("RGBA", (64, 64), (124, 58, 237, 255))
        return None

    # ─── Config persistente ───

    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    return json.load(f)
        except:
            pass
        return {"recent_dirs": [], "recent_mds": [], "geometry": "900x600", "last_dir": ""}

    def save_config(self):
        try:
            self.config["geometry"] = self.root.geometry()
            self.config["last_dir"] = self.project_path.get()
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=2)
        except:
            pass

    def add_recent(self, key, path):
        if key not in self.config:
            self.config[key] = []
        if path in self.config[key]:
            self.config[key].remove(path)
        self.config[key].insert(0, path)
        self.config[key] = self.config[key][:10]
        self.save_config()

    def _on_resize(self, event):
        pass  # se guarda al cerrar

    # ─── Bandeja ───

    def _on_close(self):
        self.save_config()
        if HAS_TRAY:
            self._hide_to_tray()
        else:
            self._quit_app()

    def _hide_to_tray(self):
        self.root.withdraw()
        if self.tray_running:
            return
        image = self._load_pil_image()
        menu = pystray.Menu(
            pystray.MenuItem("Show", self._cb_show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._cb_exit),
        )
        self.tray_icon = pystray.Icon("condor", image, "CONDOR v3.0", menu)
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
            except:
                pass
            self.tray_icon = None
            self.tray_running = False

    def _quit_app(self):
        self.save_config()
        self.stop_all = True
        self._stop_tray()
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except:
            pass
        self.root.destroy()

    # ─── Atajos de teclado ───

    def setup_keybindings(self):
        self.root.bind("<Control-v>", lambda e: self.paste_from_clipboard())
        self.root.bind("<Control-r>", lambda e: self.run_all())
        self.root.bind("<Control-s>", lambda e: self.parse_md())
        self.root.bind("<Control-z>", lambda e: self.undo_last())
        self.root.bind("<Control-o>", lambda e: self.open_explorer())
        self.root.bind("<Escape>", lambda e: self.stop_execution())

    # ─── Drag and drop (simulado con botón) ───

    def setup_drag_drop(self):
        if not HAS_DND:
            return
        try:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self._on_drop)
            self.log_msg("Drag & Drop enabled", "ok")
        except Exception as e:
            self.log_msg(f"DnD not available: {e}", "dim")

    def _on_drop(self, event):
        path = event.data.strip('{}').strip('"')
        if os.path.isdir(path):
            if not self.validate_path(path):
                messagebox.showerror("Error", "Dangerous path!")
                return
            self.project_path.set(path)
            self.add_recent("recent_dirs", path)
            self.log_msg(f"DROP DIR: {path}", "path")
        elif path.endswith('.md'):
            self.md_path.set(path)
            self.add_recent("recent_mds", path)
            self.log_msg(f"DROP .MD: {path}", "path")
            self.parse_md()
        else:
            self.log_msg(f"DROP: unsupported file type: {path}", "warn")

    # ─── Check Node.js ───

    def check_node(self):
        try:
            r = subprocess.run("node --version", shell=True, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                ver = r.stdout.strip()
                self.node_status = f"node {ver}"
            else:
                self.node_status = "node: NOT FOUND"
        except:
            self.node_status = "node: NOT FOUND"

        try:
            r = subprocess.run("npm --version", shell=True, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                self.npm_status = f"npm {r.stdout.strip()}"
            else:
                self.npm_status = "npm: NOT FOUND"
        except:
            self.npm_status = "npm: NOT FOUND"

    # ─── Validar carpeta peligrosa ───

    def validate_path(self, path):
        normalized = os.path.normpath(path).lower()
        for danger in DANGEROUS_PATHS:
            if normalized == os.path.normpath(danger).lower():
                return False
        return True

    # ─── UI ───

    def build_ui(self):
        # ═══ BARRA SUPERIOR ═══
        top = tk.Frame(self.root, bg="#161b22", padx=6, pady=4)
        top.pack(fill="x")

        # Fila 1: DIR + .MD
        paths = tk.Frame(top, bg="#161b22")
        paths.pack(fill="x", pady=1)

        tk.Label(paths, text="DIR", font=("Consolas", 8, "bold"),
            fg="#7c3aed", bg="#161b22", width=3).pack(side="left")
        self.folder_entry = tk.Entry(paths, textvariable=self.project_path,
            font=("Consolas", 8), bg="#0d1117", fg="#e2e8f0",
            insertbackground="#7c3aed", relief="flat", bd=0)
        self.folder_entry.pack(side="left", fill="x", expand=True, ipady=2, ipadx=3)
        self._tooltip(self.folder_entry, "Carpeta raíz del proyecto")
        ttk.Button(paths, text="..", style="P.TButton", width=2,
            command=self.select_folder).pack(side="left", padx=1)

        tk.Label(paths, text="MD", font=("Consolas", 8, "bold"),
            fg="#3b82f6", bg="#161b22", width=2).pack(side="left", padx=(4,0))
        self.md_entry = tk.Entry(paths, textvariable=self.md_path,
            font=("Consolas", 8), bg="#0d1117", fg="#e2e8f0",
            insertbackground="#3b82f6", relief="flat", bd=0)
        self.md_entry.pack(side="left", fill="x", expand=True, ipady=2, ipadx=3)
        self._tooltip(self.md_entry, "Archivo .md con instrucciones")
        ttk.Button(paths, text="..", style="C.TButton", width=2,
            command=self.select_md).pack(side="left", padx=1)

        # Fila 2: Botones principales
        btns = tk.Frame(top, bg="#161b22")
        btns.pack(fill="x", pady=2)

        # Grupo izquierdo: acciones principales
        left = tk.Frame(btns, bg="#161b22")
        left.pack(side="left")

        b1 = ttk.Button(left, text="SCAN", style="P.TButton", command=self.parse_md)
        b1.pack(side="left", padx=1)
        self._tooltip(b1, "Analizar .md (Ctrl+S)")

        self.run_btn = ttk.Button(left, text="RUN", style="G.TButton", command=self.run_all)
        self.run_btn.pack(side="left", padx=1)
        self.run_btn.state(["disabled"])
        self._tooltip(self.run_btn, "Ejecutar todo (Ctrl+R)")

        self.skip_btn = ttk.Button(left, text="SKIP", style="Y.TButton", command=self.skip_instruction)
        self.skip_btn.pack(side="left", padx=1)
        self.skip_btn.state(["disabled"])
        self._tooltip(self.skip_btn, "Saltar instrucción actual")

        self.stop_btn = ttk.Button(left, text="STOP", style="R.TButton", command=self.stop_execution)
        self.stop_btn.pack(side="left", padx=1)
        self.stop_btn.state(["disabled"])
        self._tooltip(self.stop_btn, "Detener ejecución (Esc)")

        # Separador
        tk.Frame(left, bg="#30363d", width=1, height=16).pack(side="left", padx=4)

        b5 = ttk.Button(left, text="PASTE", style="T.TButton", command=self.paste_from_clipboard)
        b5.pack(side="left", padx=1)
        self._tooltip(b5, "Pegar .md desde portapapeles (Ctrl+V)")

        b6 = ttk.Button(left, text="UNDO", style="O.TButton", command=self.undo_last)
        b6.pack(side="left", padx=1)
        self._tooltip(b6, "Deshacer última modificación (Ctrl+Z)")

        # Grupo derecho: utilidades
        right = tk.Frame(btns, bg="#161b22")
        right.pack(side="right")

        b7 = ttk.Button(right, text="PROMPT", style="W.TButton", command=self.copy_prompt)
        b7.pack(side="right", padx=1)
        self._tooltip(b7, "Copiar instrucciones para IA")

        b8 = ttk.Button(right, text="CMD", style="C.TButton", command=self.open_cmd)
        b8.pack(side="right", padx=1)
        self._tooltip(b8, "Abrir terminal CMD")

        b9 = ttk.Button(right, text="OPEN", style="C.TButton", command=self.open_explorer)
        b9.pack(side="right", padx=1)
        self._tooltip(b9, "Abrir en Explorer (Ctrl+O)")

        b10 = ttk.Button(right, text="CLR", style="P.TButton", command=self.clear_log)
        b10.pack(side="right", padx=1)
        self._tooltip(b10, "Limpiar log")

        # Fila 3: Checkboxes + stats
        opts = tk.Frame(top, bg="#161b22")
        opts.pack(fill="x", pady=1)

        ttk.Checkbutton(opts, text="Auto-run", variable=self.auto_run,
            style="Dark.TCheckbutton").pack(side="left", padx=4)
        ttk.Checkbutton(opts, text="Dry-run", variable=self.dry_run,
            style="Dark.TCheckbutton").pack(side="left", padx=4)
        ttk.Checkbutton(opts, text="Backup", variable=self.backup_enabled,
            style="Dark.TCheckbutton").pack(side="left", padx=4)

        self.stats_label = tk.Label(opts, text="", font=("Consolas", 7),
            fg="#64748b", bg="#161b22")
        self.stats_label.pack(side="right", padx=4)

        # ═══ BARRA DE PROGRESO ═══
        self.progress_frame = tk.Frame(self.root, bg="#0d1117", height=3)
        self.progress_frame.pack(fill="x")
        self.progress_bar = tk.Canvas(self.progress_frame, height=3,
            bg="#161b22", highlightthickness=0)
        self.progress_bar.pack(fill="x")

        # ═══ LOG ═══
        self.log = scrolledtext.ScrolledText(self.root,
            font=("Consolas", 9), bg="#0d1117", fg="#e2e8f0",
            insertbackground="#7c3aed", relief="flat", bd=0,
            wrap="word", state="disabled", padx=8, pady=4)
        self.log.pack(fill="both", expand=True)

        # ═══ BARRA DE ESTADO ═══
        status = tk.Frame(self.root, bg="#161b22", height=18)
        status.pack(fill="x", side="bottom")

        self.status_label = tk.Label(status, text="Ready",
            font=("Consolas", 7), fg="#10b981", bg="#161b22")
        self.status_label.pack(side="left", padx=4)

        tk.Label(status, text=f"{self.node_status} | {self.npm_status}",
            font=("Consolas", 7), fg="#30363d", bg="#161b22").pack(side="right", padx=4)

        tray_hint = "[X]=tray" if HAS_TRAY else ""
        tk.Label(status, text=f"Ctrl+V=paste Ctrl+R=run Esc=stop {tray_hint}",
            font=("Consolas", 7), fg="#21262d", bg="#161b22").pack(side="right", padx=8)

        # Tags
        for tag, color, bold in [
            ("ok", "#10b981", False), ("err", "#ef4444", False),
            ("warn", "#f59e0b", False), ("info", "#3b82f6", False),
            ("cmd", "#7c3aed", False), ("path", "#06b6d4", False),
            ("head", "#7c3aed", True), ("dim", "#30363d", False),
            ("white", "#e2e8f0", False), ("interactive", "#f59e0b", True),
            ("replace", "#06b6d4", True), ("dry", "#f59e0b", True),
            ("undo", "#f97316", True), ("backup", "#64748b", False),
        ]:
            f = ("Consolas", 9, "bold") if bold else ("Consolas", 9)
            self.log.tag_configure(tag, foreground=color, font=f)

    def _tooltip(self, widget, text):
        tip = None
        def enter(e):
            nonlocal tip
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + widget.winfo_height() + 2
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tk.Label(tip, text=text, font=("Consolas", 8),
                bg="#1f2937", fg="#e2e8f0", padx=6, pady=2, relief="flat").pack()
        def leave(e):
            nonlocal tip
            if tip:
                tip.destroy()
                tip = None
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    # ─── Progreso visual ───

    def update_progress(self, current, total):
        self.progress_bar.delete("all")
        if total == 0:
            return
        w = self.progress_bar.winfo_width()
        fill_w = int((current / total) * w)
        self.progress_bar.create_rectangle(0, 0, fill_w, 3, fill="#7c3aed", outline="")

    def reset_progress(self):
        self.progress_bar.delete("all")

    # ─── Spinner ───

    def start_spinner(self, text="Processing"):
        self.spinner_running = True
        self.spinner_text = text
        self._tick_spinner()

    def _tick_spinner(self):
        if not self.spinner_running:
            return
        c = self.spinner_chars[self.spinner_idx]
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)
        self.status_label.config(text=f"{c} {self.spinner_text}")
        self.root.after(100, self._tick_spinner)

    def stop_spinner(self):
        self.spinner_running = False
        self.status_label.config(text="Ready")

    # ─── Log ───

    def log_msg(self, msg, tag="white"):
        self.log.configure(state="normal")
        current = int(self.log.index("end-1c").split(".")[0])
        if current > 600:
            self.log.delete("1.0", f"{current - 500}.0")
        self.log.insert("end", msg + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.stats_label.config(text="")
        self.reset_progress()

    # ─── Sonido ───

    def play_sound(self, success=True):
        try:
            if success:
                winsound.MessageBeep(winsound.MB_OK)
            else:
                winsound.MessageBeep(winsound.MB_ICONHAND)
        except:
            pass

    # ─── Notificación Windows ───

    def notify(self, title, msg):
        if HAS_TRAY and self.tray_icon and self.tray_running:
            try:
                self.tray_icon.notify(title, msg)
            except:
                pass

    # ─── Backup ───

    def backup_file(self, filepath):
        if not self.backup_enabled.get():
            return None
        if not os.path.exists(filepath):
            return None
        backup_dir = os.path.join(self.temp_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        ts = int(time.time() * 1000)
        name = os.path.basename(filepath)
        backup_path = os.path.join(backup_dir, f"{ts}_{name}")
        shutil.copy2(filepath, backup_path)
        self.undo_stack.append({"original": filepath, "backup": backup_path})
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
        return backup_path

    def undo_last(self):
        if not self.undo_stack:
            self.log_msg("UNDO: nothing to undo", "warn")
            return
        entry = self.undo_stack.pop()
        try:
            shutil.copy2(entry["backup"], entry["original"])
            self.log_msg(f"UNDO: restored {os.path.basename(entry['original'])}", "undo")
        except Exception as e:
            self.log_msg(f"UNDO ERROR: {e}", "err")

    # ─── Botones ───

    def select_folder(self):
        path = filedialog.askdirectory(title="Project root folder")
        if path:
            if not self.validate_path(path):
                messagebox.showerror("Error", "Dangerous path! Cannot use system directories.")
                return
            self.project_path.set(path)
            self.add_recent("recent_dirs", path)
            self.log_msg(f"DIR: {path}", "path")

    def select_md(self):
        path = filedialog.askopenfilename(title=".md file",
            filetypes=[("Markdown", "*.md"), ("All", "*.*")])
        if path:
            self.md_path.set(path)
            self.add_recent("recent_mds", path)
            self.log_msg(f".MD: {path}", "path")

    def open_cmd(self):
        project = self.project_path.get()
        if not project or not os.path.isdir(project):
            messagebox.showerror("Error", "Select a valid project folder first")
            return
        subprocess.Popen(f'start cmd /k "cd /d {project}"', shell=True)
        self.log_msg(f"CMD: {project}", "ok")

    def open_explorer(self):
        project = self.project_path.get()
        if not project or not os.path.isdir(project):
            messagebox.showerror("Error", "Select a valid project folder first")
            return
        os.startfile(project)
        self.log_msg(f"OPEN: {project}", "ok")

    def copy_prompt(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(PROMPT_TEXT)
        self.root.update()
        self.log_msg("PROMPT copied to clipboard!", "ok")

    def skip_instruction(self):
        self.skip_current = True
        self.log_msg(">> SKIPPING...", "warn")

    def stop_execution(self):
        self.stop_all = True
        self.skip_current = True
        self.log_msg(">> STOPPING...", "err")

    def paste_from_clipboard(self):
        try:
            clipboard = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showerror("Error", "Clipboard is empty")
            return
        if not clipboard.strip():
            return

        project = self.project_path.get()
        if not project or not os.path.isdir(project):
            messagebox.showerror("Error", "Select DIR first")
            return

        ts = int(time.time())
        temp_file = os.path.join(self.temp_dir, f"paste_{ts}.md")
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(clipboard)

        self.md_path.set(temp_file)
        self.log_msg(f"PASTE: {len(clipboard)} chars", "ok")
        self.parse_md()

    # ─── Parse ───

    def parse_md(self):
        md_file = self.md_path.get()
        if not md_file or not os.path.exists(md_file):
            messagebox.showerror("Error", "Select a valid .md file")
            return
        project = self.project_path.get()
        if not project or not os.path.isdir(project):
            messagebox.showerror("Error", "Select a valid folder")
            return
        if not self.validate_path(project):
            messagebox.showerror("Error", "Dangerous path!")
            return

        self.clear_log()
        self.log_msg("=" * 50, "dim")
        self.log_msg("SCANNING .md", "head")
        self.log_msg("=" * 50, "dim")

        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self.log_msg(f"Error: {e}", "err")
            return

        self.instructions = self.extract_instructions(content)

        if not self.instructions:
            self.log_msg("No ETIQUETA found", "warn")
            self.run_btn.state(["disabled"])
            return

        counts = {}
        for inst in self.instructions:
            a = inst["action"]
            counts[a] = counts.get(a, 0) + 1

        self.log_msg(f"Found: {len(self.instructions)} instructions", "info")
        for a, c in counts.items():
            self.log_msg(f"  {a}: {c}", "info")
        self.log_msg("")

        for i, inst in enumerate(self.instructions, 1):
            a = inst["action"]
            if a == "EJECUTAR":
                cmds = inst["content"].replace("\n", " | ")[:60]
                is_int = any(ic in inst["content"].lower() for ic in ["npm create", "npx create", "npm init"])
                tag = "interactive" if is_int else "cmd"
                marker = " [I]" if is_int else ""
                self.log_msg(f"  {i:02d}. EXEC{marker} {cmds}...", tag)
            elif a == "ELIMINAR":
                self.log_msg(f"  {i:02d}. DEL  {inst['filepath']}", "warn")
            elif a == "REEMPLAZAR":
                self.log_msg(f"  {i:02d}. REPL {inst['filepath']}", "replace")
            else:
                lines = inst["content"].count("\n") + 1
                act = "NEW" if a == "CREAR" else "MOD"
                self.log_msg(f"  {i:02d}. {act}  {inst['filepath']} ({lines}L)", "cmd")

        self.log_msg("")

        if self.dry_run.get():
            self.log_msg("DRY-RUN mode: no changes will be made", "dry")

        self.log_msg("Ready. Press RUN to execute.", "ok")
        self.stats_label.config(text=" | ".join(f"{a}:{c}" for a, c in counts.items()))
        self.run_btn.state(["!disabled"])

        if self.auto_run.get():
            self.run_all()

    def extract_instructions(self, content):
        instructions = []
        pattern = re.compile(r'ETIQUETA\[([^\]]+)\]\s*\n```(\w*)\n(.*?)```', re.DOTALL)

        for match in pattern.finditer(content):
            params_str = match.group(1)
            lang = match.group(2)
            code = match.group(3)
            params = [p.strip() for p in params_str.split(",")]

            if len(params) != 4:
                self.log_msg(f"Invalid ETIQUETA ({len(params)} params): [{params_str}]", "warn")
                continue

            ubicacion, nombre, extension, accion = params
            accion = accion.upper().strip()

            if accion == "EJECUTAR" or nombre.lower() == "nan":
                filepath = "CMD"
            elif ubicacion == ".":
                filepath = f"{nombre}.{extension}"
            else:
                filepath = f"{ubicacion}/{nombre}.{extension}"

            instructions.append({
                "ubicacion": ubicacion, "nombre": nombre,
                "extension": extension, "action": accion,
                "language": lang, "content": code.strip(),
                "filepath": filepath,
            })

        return instructions

    # ─── Ejecución ───

    def run_all(self):
        if self.is_running or not self.instructions:
            return

        mode = "DRY-RUN" if self.dry_run.get() else "EXECUTE"
        confirm = messagebox.askyesno("Confirm",
            f"{mode}: {len(self.instructions)} instructions\n"
            f"Project: {self.project_path.get()}\n\nContinue?")
        if not confirm:
            return

        self.is_running = True
        self.stop_all = False
        self.run_btn.state(["disabled"])
        self.skip_btn.state(["!disabled"])
        self.stop_btn.state(["!disabled"])
        self.start_spinner("Executing")

        threading.Thread(target=self._execute_all, daemon=True).start()

    def _execute_all(self):
        project = self.project_path.get()
        total = len(self.instructions)
        success = errors = skipped = 0

        self.log_msg("")
        self.log_msg("=" * 50, "dim")
        mode_label = "DRY-RUN" if self.dry_run.get() else "EXECUTING"
        self.log_msg(mode_label, "head")
        self.log_msg("=" * 50, "dim")

        for i, inst in enumerate(self.instructions, 1):
            if self.stop_all:
                self.log_msg(f"STOPPED at [{i}/{total}]", "err")
                break

            self.skip_current = False
            action = inst["action"]
            self.spinner_text = f"[{i}/{total}] {action}"
            self.root.after(0, lambda c=i, t=total: self.update_progress(c, t))

            self.log_msg(f"--- [{i}/{total}] {action} ---", "dim")

            try:
                if self.dry_run.get() and action != "EJECUTAR":
                    self.log_msg(f"  [DRY] Would {action}: {inst['filepath']}", "dry")
                    success += 1
                    continue

                if action == "EJECUTAR":
                    if self.dry_run.get():
                        cmds = inst["content"].replace("\n", " | ")[:60]
                        self.log_msg(f"  [DRY] Would execute: {cmds}...", "dry")
                        success += 1
                        continue
                    self.execute_cmd(project, inst["content"])
                elif action in ("CREAR", "MODIFICAR"):
                    full = os.path.join(project, inst["filepath"].replace("/", os.sep))
                    self.backup_file(full)
                    self.create_file(project, inst)
                elif action == "ELIMINAR":
                    full = os.path.join(project, inst["filepath"].replace("/", os.sep))
                    if not messagebox.askyesno("Confirm DELETE",
                        f"Delete {inst['filepath']}?"):
                        skipped += 1
                        continue
                    self.backup_file(full)
                    self.delete_file(project, inst)
                elif action == "REEMPLAZAR":
                    full = os.path.join(project, inst["filepath"].replace("/", os.sep))
                    self.backup_file(full)
                    self.replace_in_file(project, inst)
                else:
                    self.log_msg(f"Unknown action: {action}", "warn")
                    continue

                if self.skip_current:
                    skipped += 1
                else:
                    success += 1

            except Exception as e:
                errors += 1
                self.log_msg(f"ERROR: {e}", "err")

        self.log_msg("")
        self.log_msg("=" * 50, "dim")
        self.log_msg(f"OK:{success} ERR:{errors} SKIP:{skipped} TOTAL:{total}", "head")
        self.log_msg("=" * 50, "dim")

        if errors == 0 and not self.stop_all:
            self.log_msg("Done!", "ok")
            self.root.after(0, lambda: self.play_sound(True))
            self.notify("CONDOR", "Execution completed successfully!")
        elif self.stop_all:
            self.log_msg("Stopped by user", "warn")
        else:
            self.log_msg(f"Done with {errors} errors", "warn")
            self.root.after(0, lambda: self.play_sound(False))
            self.notify("CONDOR", f"Completed with {errors} errors")

        self.root.after(0, self._finish)

    def _finish(self):
        self.is_running = False
        self.stop_spinner()
        self.run_btn.state(["!disabled"])
        self.skip_btn.state(["disabled"])
        self.stop_btn.state(["disabled"])

    # ─── Acciones de archivo ───

    def create_file(self, project, inst):
        filepath = inst["filepath"]
        content = inst["content"]
        full_path = os.path.join(project, filepath.replace("/", os.sep))

        dir_path = os.path.dirname(full_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content + "\n")

        lines = content.count("\n") + 1
        act = "NEW" if inst["action"] == "CREAR" else "MOD"
        self.log_msg(f"  {act}: {filepath} ({lines}L)", "ok")

    def delete_file(self, project, inst):
        filepath = inst["filepath"]
        full_path = os.path.join(project, filepath.replace("/", os.sep))
        if os.path.exists(full_path):
            os.remove(full_path)
            self.log_msg(f"  DEL: {filepath}", "warn")
        else:
            self.log_msg(f"  NOT FOUND: {filepath}", "warn")

    def replace_in_file(self, project, inst):
        filepath = inst["filepath"]
        content = inst["content"]
        full_path = os.path.join(project, filepath.replace("/", os.sep))

        if not os.path.exists(full_path):
            self.log_msg(f"  REPL ERR: file not found -> {filepath}", "err")
            return

        if ">>>" not in content:
            self.log_msg(f"  REPL ERR: missing >>> separator", "err")
            return

        parts = content.split(">>>", 1)
        original_text = parts[0].rstrip("\n")
        replace_text = parts[1].lstrip("\n")

        if not original_text.strip():
            self.log_msg(f"  REPL ERR: empty search text", "err")
            return

        with open(full_path, "r", encoding="utf-8") as f:
            file_content = f.read()

        # Normalizar: tabs a espacios para comparación
        def normalize(text):
            return text.replace("\t", "    ")

        normalized_file = normalize(file_content)
        normalized_search = normalize(original_text)

        if normalized_search in normalized_file:
            # Match con normalización
            file_content = normalized_file.replace(normalized_search, replace_text, 1)
        elif original_text in file_content:
            # Match exacto
            file_content = file_content.replace(original_text, replace_text, 1)
        else:
            # Intento por líneas con strip
            orig_lines = [l.rstrip() for l in original_text.split("\n")]
            file_lines = file_content.split("\n")
            file_stripped = [l.rstrip() for l in file_lines]

            found = False
            for idx in range(len(file_stripped) - len(orig_lines) + 1):
                # Comparar normalizando tabs
                chunk = [normalize(l) for l in file_stripped[idx:idx + len(orig_lines)]]
                search = [normalize(l) for l in orig_lines]
                if chunk == search:
                    new_lines = file_lines[:idx] + replace_text.split("\n") + file_lines[idx + len(orig_lines):]
                    file_content = "\n".join(new_lines)
                    found = True
                    break

            if not found:
                self.log_msg(f"  REPL ERR: text not found in {filepath}", "err")
                self.log_msg(f"    search: {original_text[:60]}...", "dim")
                return

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(file_content)

        orig_preview = original_text.split("\n")[0][:50]
        repl_preview = replace_text.split("\n")[0][:50]
        self.log_msg(f"  REPL: {filepath}", "replace")
        self.log_msg(f"    - {orig_preview}", "dim")
        self.log_msg(f"    + {repl_preview}", "ok")

    # ─── CMD ───

    def is_interactive(self, cmd):
        cmd_lower = cmd.lower().strip()
        return any(cmd_lower.startswith(ic.lower()) for ic in INTERACTIVE_COMMANDS)

    def execute_cmd(self, project, commands):
        lines = [l.strip() for l in commands.strip().split("\n")
                 if l.strip() and not l.strip().startswith("#")]

        for cmd in lines:
            if self.skip_current or self.stop_all:
                self.log_msg(f"  SKIP: {cmd}", "warn")
                continue

            if self.is_interactive(cmd):
                self.log_msg(f"  [I] {cmd}", "interactive")
                try:
                    p = subprocess.Popen(
                        f'start /wait cmd /k "cd /d {project} && {cmd} && echo. && echo Done. Close this window. && pause"',
                        shell=True, cwd=project)
                    p.wait()
                    self.log_msg("  Window closed. Continuing...", "ok")
                except Exception as e:
                    self.log_msg(f"  Error: {e}", "err")
                continue

            self.log_msg(f"  > {cmd}", "cmd")
            self.spinner_text = cmd[:40]

            try:
                result = subprocess.run(cmd, shell=True, cwd=project,
                    capture_output=True, text=True, timeout=180)

                if result.stdout.strip():
                    for line in result.stdout.strip().split("\n")[:6]:
                        self.log_msg(f"    {line}", "info")

                if result.returncode != 0 and result.stderr.strip():
                    stderr = result.stderr.strip()
                    tag = "warn" if "warn" in stderr.lower() or "notice" in stderr.lower() else "err"
                    for line in stderr.split("\n")[:4]:
                        self.log_msg(f"    {line[:100]}", tag)

                status = "OK" if result.returncode == 0 else f"exit:{result.returncode}"
                self.log_msg(f"    {status}", "ok" if result.returncode == 0 else "warn")

            except subprocess.TimeoutExpired:
                self.log_msg("    TIMEOUT", "err")
            except Exception as e:
                self.log_msg(f"    Error: {e}", "err")

    # ─── Run ───

    def run(self):
        self.log_msg("CONDOR v3.0", "head")
        self.log_msg(f"{self.node_status} | {self.npm_status}", "info")
        self.log_msg("Ctrl+V=paste Ctrl+R=run Ctrl+S=scan Ctrl+Z=undo Ctrl+O=open Esc=stop", "dim")
        self.log_msg("")
        self.root.mainloop()


if __name__ == "__main__":
    app = AutoBuilder()
    app.run()
