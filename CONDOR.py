"""
CONDOR v2.3 — Automatizador de proyectos desde .md
"""

import os
import re
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk
import sys
import time

try:
    import pystray
    from PIL import Image
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

INTERACTIVE_COMMANDS = [
    "npm create", "npx create", "npm init", "npx init",
    "npm run dev", "npm start", "npm test",
    "python", "py ", "node ", "npx prisma studio",
]

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
- **accion**: una de estas → `CREAR` | `MODIFICAR` | `EJECUTAR` | `ELIMINAR`

### Acciones:
- **CREAR** → Crea un archivo nuevo con el contenido del bloque de código
- **MODIFICAR** → Reemplaza TODO el contenido de un archivo existente
- **EJECUTAR** → Ejecuta los comandos en la terminal CMD de Windows 10
- **ELIMINAR** → Elimina el archivo indicado

## Ejemplos de uso

### Ejecutar comandos en terminal:
ETIQUETA[.,nan,cmd,EJECUTAR]
```bash
npm install
npm install express
mkdir src
```

### Crear un archivo:
ETIQUETA[src,App,jsx,CREAR]
```jsx
export default function App() {
  return <h1>Hola</h1>
}
```

### Modificar un archivo existente:
ETIQUETA[src,index,css,MODIFICAR]
```css
body { margin: 0; }
```

### Eliminar un archivo:
ETIQUETA[src,viejo,js,ELIMINAR]
```bash
eliminado
```

## Reglas importantes

1. La línea `ETIQUETA[...]` debe estar SOLA en su propia línea, justo antes del bloque ``` de código
2. No agregar texto extra en la línea de la etiqueta
3. Para comandos de terminal usar `ETIQUETA[.,nan,cmd,EJECUTAR]` con bloque ```bash
4. Para archivos usar la ruta relativa: `ETIQUETA[src/components,Navbar,jsx,CREAR]`
5. Separar comandos interactivos (npm create, npm run dev) en su propio bloque EJECUTAR
6. Usar `.` como ubicacion para archivos en la raíz del proyecto
7. El contenido del bloque de código es lo que se escribe en el archivo o se ejecuta
8. Cada bloque de código debe tener su propia ETIQUETA
9. Trabajo con Windows 10 y CMD, los comandos deben ser compatibles
10. Cuando se crea la estructura de carpetas, usar un solo bloque EJECUTAR con mkdir

## Ejemplo de flujo completo para un proyecto:

ETIQUETA[.,nan,cmd,EJECUTAR]
```bash
npm create vite@latest . -- --template react
```

ETIQUETA[.,nan,cmd,EJECUTAR]
```bash
npm install
npm install alguna-dependencia
```

ETIQUETA[.,nan,cmd,EJECUTAR]
```bash
rd /s /q src
mkdir src
mkdir src\\components
```

ETIQUETA[.,vite.config,js,CREAR]
```js
import { defineConfig } from 'vite'
export default defineConfig({ plugins: [] })
```

ETIQUETA[src,main,jsx,CREAR]
```jsx
import React from 'react'
// ... contenido
```

Por favor, sigue este formato en todas tus respuestas cuando me des código para crear o modificar archivos del proyecto. Gracias!"""


class AutoBuilder:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("CONDOR v2.3")
        self.root.geometry("800x550")
        self.root.configure(bg="#0d1117")
        self.root.resizable(True, True)

        # Estado bandeja
        self.tray_icon    = None
        self.tray_running = False

        # Estado general
        self.project_path = tk.StringVar(value="")
        self.md_path      = tk.StringVar(value="")
        self.is_running   = False
        self.skip_current = False
        self.stop_all     = False
        self.instructions = []

        # Spinner
        self.spinner_chars        = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.spinner_idx          = 0
        self.spinner_running      = False
        self.spinner_text         = ""
        self.current_spinner_line = None

        # Icono
        self.icon_path = self._find_icon()
        if self.icon_path:
            try:
                self.root.iconbitmap(self.icon_path)
            except Exception as e:
                print(f"[CONDOR] iconbitmap error: {e}")

        # Estilos
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self._def_btn("P", "#7c3aed", "#6d28d9")
        self._def_btn("G", "#10b981", "#059669")
        self._def_btn("R", "#ef4444", "#dc2626")
        self._def_btn("Y", "#f59e0b", "#d97706", fg="black")
        self._def_btn("C", "#3b82f6", "#2563eb")
        self._def_btn("W", "#64748b", "#475569")

        self.build_ui()

        # Interceptar X
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────

    def _def_btn(self, prefix, bg, active_bg, fg="white"):
        self.style.configure(f"{prefix}.TButton",
            background=bg, foreground=fg,
            font=("Consolas", 9), padding=(8, 3))
        self.style.map(f"{prefix}.TButton",
            background=[("active", active_bg), ("disabled", "#333")])

    def _find_icon(self):
        candidates = []
        if getattr(sys, "frozen", False):
            candidates.append(os.path.join(sys._MEIPASS, "condor.ico"))
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(script_dir, "condor.ico"))
        candidates.append(os.path.join(os.getcwd(), "condor.ico"))
        for p in candidates:
            if os.path.isfile(p):
                print(f"[CONDOR] Icono: {p}")
                return p
        print("[CONDOR] condor.ico no encontrado")
        return None

    def _load_pil_image(self):
        """Carga condor.ico como imagen PIL para pystray."""
        if self.icon_path and HAS_TRAY:
            try:
                img = Image.open(self.icon_path).convert("RGBA").resize((64, 64))
                return img
            except Exception as e:
                print(f"[CONDOR] PIL error abriendo icono: {e}")
        # Fallback morado
        return Image.new("RGBA", (64, 64), (124, 58, 237, 255))

    # ─────────────────────────────────────────────
    # Bandeja del sistema
    # ─────────────────────────────────────────────

    def _on_close(self):
        """Intercepta la X de la ventana."""
        if HAS_TRAY:
            self._hide_to_tray()
        else:
            self._quit_app()

    def _hide_to_tray(self):
        """Oculta la ventana y lanza el icono en la bandeja."""
        self.root.withdraw()

        # Si ya hay un icono corriendo no crear otro
        if self.tray_running:
            return

        image = self._load_pil_image()

        menu = pystray.Menu(
            pystray.MenuItem("Mostrar CONDOR", self._cb_mostrar, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir",          self._cb_salir),
        )

        self.tray_icon    = pystray.Icon("condor", image, "CONDOR v2.3", menu)
        self.tray_running = True

        # pystray.run() bloquea → hilo daemon
        threading.Thread(target=self._tray_loop, daemon=True, name="TrayThread").start()

    def _tray_loop(self):
        """Corre en el hilo daemon; bloquea hasta que icon.stop() se llame."""
        try:
            self.tray_icon.run()
        finally:
            self.tray_running = False

    def _cb_mostrar(self, icon, item):
        """Callback del menú bandeja → restaurar ventana (debe ir al hilo Tk)."""
        self.root.after(0, self._restaurar_ventana)

    def _restaurar_ventana(self):
        """Ejecutado en el hilo principal de Tk."""
        self._parar_tray()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _cb_salir(self, icon, item):
        """Callback del menú bandeja → cerrar app."""
        self.root.after(0, self._quit_app)

    def _parar_tray(self):
        """Para el icono de bandeja de forma segura."""
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception as e:
                print(f"[CONDOR] Error parando bandeja: {e}")
            self.tray_icon    = None
            self.tray_running = False

    def _quit_app(self):
        """Cierra completamente la aplicación."""
        self.stop_all = True
        self._parar_tray()
        self.root.destroy()

    # ─────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────

    def build_ui(self):
        top = tk.Frame(self.root, bg="#161b22", padx=8, pady=6)
        top.pack(fill="x")

        # Fila DIR
        row1 = tk.Frame(top, bg="#161b22")
        row1.pack(fill="x", pady=1)
        tk.Label(row1, text="DIR:", font=("Consolas", 9, "bold"),
            fg="#7c3aed", bg="#161b22", width=4).pack(side="left")
        self.folder_entry = tk.Entry(row1, textvariable=self.project_path,
            font=("Consolas", 9), bg="#0d1117", fg="#e2e8f0",
            insertbackground="#7c3aed", relief="flat", bd=0)
        self.folder_entry.pack(side="left", fill="x", expand=True, ipady=3, ipadx=4)
        ttk.Button(row1, text="...", style="P.TButton", width=3,
            command=self.select_folder).pack(side="right", padx=2)

        # Fila .MD
        row2 = tk.Frame(top, bg="#161b22")
        row2.pack(fill="x", pady=1)
        tk.Label(row2, text=".MD:", font=("Consolas", 9, "bold"),
            fg="#3b82f6", bg="#161b22", width=4).pack(side="left")
        self.md_entry = tk.Entry(row2, textvariable=self.md_path,
            font=("Consolas", 9), bg="#0d1117", fg="#e2e8f0",
            insertbackground="#7c3aed", relief="flat", bd=0)
        self.md_entry.pack(side="left", fill="x", expand=True, ipady=3, ipadx=4)
        ttk.Button(row2, text="...", style="P.TButton", width=3,
            command=self.select_md).pack(side="right", padx=2)

        # Fila botones
        row3 = tk.Frame(top, bg="#161b22")
        row3.pack(fill="x", pady=4)

        self.parse_btn = ttk.Button(row3, text="ANALIZAR", style="P.TButton",
            command=self.parse_md)
        self.parse_btn.pack(side="left", padx=2)

        self.run_btn = ttk.Button(row3, text="EJECUTAR", style="G.TButton",
            command=self.run_all)
        self.run_btn.pack(side="left", padx=2)
        self.run_btn.state(["disabled"])

        self.skip_btn = ttk.Button(row3, text="SALTAR", style="Y.TButton",
            command=self.skip_instruction)
        self.skip_btn.pack(side="left", padx=2)
        self.skip_btn.state(["disabled"])

        self.stop_btn = ttk.Button(row3, text="PARAR", style="R.TButton",
            command=self.stop_execution)
        self.stop_btn.pack(side="left", padx=2)
        self.stop_btn.state(["disabled"])

        self.prompt_btn = ttk.Button(row3, text="PROMPT", style="W.TButton",
            command=self.copy_prompt)
        self.prompt_btn.pack(side="right", padx=2)

        self.cmd_btn = ttk.Button(row3, text="CMD", style="C.TButton",
            command=self.open_cmd)
        self.cmd_btn.pack(side="right", padx=2)

        self.clear_btn = ttk.Button(row3, text="LIMPIAR", style="P.TButton",
            command=self.clear_log)
        self.clear_btn.pack(side="right", padx=2)

        self.stats_label = tk.Label(row3, text="", font=("Consolas", 8),
            fg="#64748b", bg="#161b22")
        self.stats_label.pack(side="right", padx=8)

        # Log
        log_frame = tk.Frame(self.root, bg="#0d1117")
        log_frame.pack(fill="both", expand=True)

        self.log = scrolledtext.ScrolledText(log_frame,
            font=("Consolas", 9), bg="#0d1117", fg="#e2e8f0",
            insertbackground="#7c3aed", relief="flat", bd=0,
            wrap="word", state="disabled", padx=8, pady=4)
        self.log.pack(fill="both", expand=True)

        # Barra de estado
        self.status_frame = tk.Frame(self.root, bg="#161b22", height=20)
        self.status_frame.pack(fill="x", side="bottom")

        self.status_label = tk.Label(self.status_frame, text="",
            font=("Consolas", 8), fg="#10b981", bg="#161b22")
        self.status_label.pack(side="left", padx=5)

        hint = "  [X] minimiza a bandeja" if HAS_TRAY else "  pip install pystray pillow"
        tk.Label(self.status_frame, text=hint,
            font=("Consolas", 8), fg="#30363d", bg="#161b22").pack(side="right", padx=5)

        # Tags de color
        tags = [
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
            ("spinner",     "#f59e0b", False),
        ]
        for tag, color, bold in tags:
            font = ("Consolas", 9, "bold") if bold else ("Consolas", 9)
            self.log.tag_configure(tag, foreground=color, font=font)

    # ─────────────────────────────────────────────
    # Spinner
    # ─────────────────────────────────────────────

    def start_spinner(self, text="Procesando"):
        self.spinner_running = True
        self.spinner_text    = text
        self._tick_spinner()

    def _tick_spinner(self):
        if not self.spinner_running:
            return
        char = self.spinner_chars[self.spinner_idx]
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)
        self.status_label.config(text=f"{char} {self.spinner_text}...")
        self.root.after(100, self._tick_spinner)

    def stop_spinner(self):
        self.spinner_running = False
        self.status_label.config(text="Listo")

    # ─────────────────────────────────────────────
    # Log
    # ─────────────────────────────────────────────

    def log_msg(self, msg, tag="white"):
        self.log.configure(state="normal")
        max_lines = 500
        current   = int(self.log.index("end-1c").split(".")[0])
        if current > max_lines:
            self.log.delete("1.0", f"{current - max_lines + 1}.0")
        self.log.insert("end", msg + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")
        if not self.is_running:
            self.root.update_idletasks()

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.stats_label.config(text="")
        self.current_spinner_line = None

    # ─────────────────────────────────────────────
    # Botones
    # ─────────────────────────────────────────────

    def copy_prompt(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(PROMPT_TEXT)
        self.root.update()
        self.log_msg("PROMPT copiado al portapapeles!", "ok")
        self.log_msg("Pegalo al inicio de tu chat con el asistente de IA.", "info")
        self.log_msg("Asi sus respuestas tendran el formato ETIQUETA[...]", "info")
        self.log_msg("")

    def open_cmd(self):
        project = self.project_path.get()
        if not project or not os.path.isdir(project):
            messagebox.showerror("Error", "Selecciona una carpeta valida primero")
            return
        try:
            subprocess.Popen(f'start cmd /k "cd /d {project}"', shell=True)
            self.log_msg(f"CMD abierto en: {project}", "ok")
        except Exception as e:
            self.log_msg(f"Error: {e}", "err")

    def select_folder(self):
        path = filedialog.askdirectory(title="Carpeta raiz del proyecto")
        if path:
            self.project_path.set(path)
            self.log_msg(f"DIR: {path}", "path")

    def select_md(self):
        path = filedialog.askopenfilename(title="Archivo .md",
            filetypes=[("Markdown", "*.md"), ("Todos", "*.*")])
        if path:
            self.md_path.set(path)
            self.log_msg(f".MD: {path}", "path")

    def skip_instruction(self):
        self.skip_current = True
        self.log_msg(">> SALTANDO...", "warn")

    def stop_execution(self):
        self.stop_all     = True
        self.skip_current = True
        self.log_msg(">> DETENIENDO...", "err")

    # ─────────────────────────────────────────────
    # Parseo .md
    # ─────────────────────────────────────────────

    def parse_md(self):
        md_file = self.md_path.get()
        if not md_file or not os.path.exists(md_file):
            messagebox.showerror("Error", "Selecciona un archivo .md valido")
            return
        project = self.project_path.get()
        if not project or not os.path.isdir(project):
            messagebox.showerror("Error", "Selecciona una carpeta valida")
            return

        self.clear_log()
        self.log_msg("=" * 50, "dim")
        self.log_msg("ANALIZANDO .md", "head")
        self.log_msg("=" * 50, "dim")

        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self.log_msg(f"Error: {e}", "err")
            return

        self.instructions = self.extract_instructions(content)

        if not self.instructions:
            self.log_msg("No se encontraron ETIQUETAS", "warn")
            self.run_btn.state(["disabled"])
            return

        counts = {}
        for inst in self.instructions:
            a = inst["action"]
            counts[a] = counts.get(a, 0) + 1

        self.log_msg(f"Total: {len(self.instructions)} instrucciones", "info")
        for a, c in counts.items():
            self.log_msg(f"  {a}: {c}", "info")
        self.log_msg("")

        for i, inst in enumerate(self.instructions, 1):
            if inst["action"] == "EJECUTAR":
                cmds   = inst["content"].replace("\n", " | ")[:70]
                is_int = any(ic in inst["content"].lower()
                             for ic in ["npm create", "npx create", "npm init"])
                tag    = "interactive" if is_int else "cmd"
                marker = " [INTERACTIVO]" if is_int else ""
                self.log_msg(f"  {i:02d}. EXEC{marker} -> {cmds}...", tag)
            elif inst["action"] == "ELIMINAR":
                self.log_msg(f"  {i:02d}. DEL  -> {inst['filepath']}", "warn")
            else:
                lines = inst["content"].count("\n") + 1
                act   = "NEW " if inst["action"] == "CREAR" else "MOD "
                self.log_msg(f"  {i:02d}. {act} -> {inst['filepath']} ({lines}L)", "cmd")

        self.log_msg("")
        self.log_msg("Listo. Presiona EJECUTAR para aplicar.", "ok")
        self.stats_label.config(text=" | ".join(f"{a}:{c}" for a, c in counts.items()))
        self.run_btn.state(["!disabled"])

    def extract_instructions(self, content):
        instructions = []
        pattern = re.compile(r'ETIQUETA\[([^\]]+)\]\s*\n```(\w*)\n(.*?)```', re.DOTALL)

        for match in pattern.finditer(content):
            params_str = match.group(1)
            lang       = match.group(2)
            code       = match.group(3)
            params     = [p.strip() for p in params_str.split(",")]

            if len(params) != 4:
                self.log_msg(
                    f"ETIQUETA invalida ({len(params)} params): [{params_str}]", "warn")
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

    # ─────────────────────────────────────────────
    # Ejecución
    # ─────────────────────────────────────────────

    def run_all(self):
        if self.is_running or not self.instructions:
            return

        confirm = messagebox.askyesno("Confirmar",
            f"{len(self.instructions)} instrucciones.\n"
            f"Proyecto: {self.project_path.get()}\n\nContinuar?")
        if not confirm:
            return

        self.is_running = True
        self.stop_all   = False
        self.run_btn.state(["disabled"])
        self.parse_btn.state(["disabled"])
        self.skip_btn.state(["!disabled"])
        self.stop_btn.state(["!disabled"])
        self.start_spinner("Ejecutando instrucciones")

        threading.Thread(target=self.execute_instructions, daemon=True).start()

    def execute_instructions(self):
        project = self.project_path.get()
        total   = len(self.instructions)
        success = errors = skipped = 0

        self.log_msg("")
        self.log_msg("=" * 50, "dim")
        self.log_msg("EJECUTANDO", "head")
        self.log_msg("=" * 50, "dim")

        for i, inst in enumerate(self.instructions, 1):
            if self.stop_all:
                self.log_msg(f"DETENIDO en [{i}/{total}]", "err")
                break

            self.skip_current = False
            action            = inst["action"]
            self.spinner_text = f"[{i}/{total}] {action}"

            self.log_msg(f"--- [{i}/{total}] {action} ---", "dim")

            try:
                if action == "EJECUTAR":
                    self.execute_cmd(project, inst["content"])
                elif action in ("CREAR", "MODIFICAR"):
                    self.create_file(project, inst)
                elif action == "ELIMINAR":
                    self.delete_file(project, inst)
                else:
                    self.log_msg(f"Accion desconocida: {action}", "warn")
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
            self.log_msg("Completado!", "ok")
        elif self.stop_all:
            self.log_msg("Detenido por el usuario", "warn")
        else:
            self.log_msg(f"Completado con {errors} errores", "warn")

        self.root.after(0, self.finish_execution)

    def finish_execution(self):
        self.is_running = False
        self.stop_spinner()
        self.run_btn.state(["!disabled"])
        self.parse_btn.state(["!disabled"])
        self.skip_btn.state(["disabled"])
        self.stop_btn.state(["disabled"])

    def create_file(self, project, inst):
        filepath  = inst["filepath"]
        content   = inst["content"]
        full_path = os.path.join(project, filepath.replace("/", os.sep))

        dir_path = os.path.dirname(full_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            self.log_msg(f"  mkdir: {dir_path}", "info")

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content + "\n")

        lines = content.count("\n") + 1
        act   = "NEW" if inst["action"] == "CREAR" else "MOD"
        self.log_msg(f"  {act}: {filepath} ({lines}L)", "ok")

    def delete_file(self, project, inst):
        filepath  = inst["filepath"]
        full_path = os.path.join(project, filepath.replace("/", os.sep))
        if os.path.exists(full_path):
            os.remove(full_path)
            self.log_msg(f"  DEL: {filepath}", "warn")
        else:
            self.log_msg(f"  NOT FOUND: {filepath}", "warn")

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
                self.log_msg(f"  [INTERACTIVO] {cmd}", "interactive")
                self.log_msg(f"  Abriendo CMD separada...", "warn")
                try:
                    p = subprocess.Popen(
                        f'start /wait cmd /k "cd /d {project} && {cmd} && '
                        f'echo. && echo LISTO. Cierra esta ventana. && pause"',
                        shell=True, cwd=project)
                    p.wait()
                    self.log_msg("  CMD cerrada. Continuando...", "ok")
                except Exception as e:
                    self.log_msg(f"  Error: {e}", "err")
                continue

            self.log_msg(f"  > {cmd}", "cmd")
            self.spinner_text = f"Ejecutando: {cmd[:30]}..."

            try:
                result = subprocess.run(cmd, shell=True, cwd=project,
                    capture_output=True, text=True, timeout=180)

                if result.stdout.strip():
                    for line in result.stdout.strip().split("\n")[:8]:
                        self.log_msg(f"    {line}", "info")

                if result.returncode != 0 and result.stderr.strip():
                    stderr = result.stderr.strip()
                    tag    = "warn" if ("warn" in stderr.lower()
                                        or "notice" in stderr.lower()) else "err"
                    for line in stderr.split("\n")[:5]:
                        self.log_msg(f"    {line[:120]}", tag)

                tag = "ok" if result.returncode == 0 else "warn"
                msg = "OK" if result.returncode == 0 else f"exit:{result.returncode}"
                self.log_msg(f"    {msg}", tag)

            except subprocess.TimeoutExpired:
                self.log_msg("    TIMEOUT (>180s)", "err")
            except Exception as e:
                self.log_msg(f"    Error: {e}", "err")

    # ─────────────────────────────────────────────
    # Entry point
    # ─────────────────────────────────────────────

    def run(self):
        self.log_msg("CONDOR v2.3", "head")
        self.log_msg("DIR: carpeta raiz del proyecto", "info")
        self.log_msg(".MD: archivo con instrucciones", "info")
        self.log_msg("ANALIZAR → EJECUTAR | SALTAR | PARAR", "info")
        self.log_msg("CMD: abrir terminal | PROMPT: copiar instrucciones IA", "info")
        if HAS_TRAY:
            self.log_msg("Cerrar ventana [X] → minimiza a bandeja del sistema", "ok")
        else:
            self.log_msg("AVISO: pip install pystray pillow (para bandeja)", "warn")
        self.log_msg("")
        self.root.mainloop()


if __name__ == "__main__":
    app = AutoBuilder()
    app.run()
