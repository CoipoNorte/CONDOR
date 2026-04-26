"""
CONDOR v2.2 — Automatizador de proyectos desde .md
+ Botón PROMPT para copiar instrucciones al portapapeles
"""

import os
import re
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk

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
        self.root.title("CONDOR v2.2")
        self.root.geometry("800x550")
        self.root.configure(bg="#0d1117")
        self.root.resizable(True, True)

        self.project_path = tk.StringVar(value="")
        self.md_path = tk.StringVar(value="")
        self.is_running = False
        self.skip_current = False
        self.stop_all = False
        self.instructions = []

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("P.TButton", background="#7c3aed", foreground="white",
            font=("Consolas", 9), padding=(8, 3))
        self.style.map("P.TButton", background=[("active", "#6d28d9"), ("disabled", "#333")])
        self.style.configure("G.TButton", background="#10b981", foreground="white",
            font=("Consolas", 9), padding=(8, 3))
        self.style.map("G.TButton", background=[("active", "#059669"), ("disabled", "#333")])
        self.style.configure("R.TButton", background="#ef4444", foreground="white",
            font=("Consolas", 9), padding=(8, 3))
        self.style.map("R.TButton", background=[("active", "#dc2626"), ("disabled", "#333")])
        self.style.configure("Y.TButton", background="#f59e0b", foreground="black",
            font=("Consolas", 9), padding=(8, 3))
        self.style.map("Y.TButton", background=[("active", "#d97706"), ("disabled", "#333")])
        self.style.configure("C.TButton", background="#3b82f6", foreground="white",
            font=("Consolas", 9), padding=(8, 3))
        self.style.map("C.TButton", background=[("active", "#2563eb"), ("disabled", "#333")])
        self.style.configure("W.TButton", background="#64748b", foreground="white",
            font=("Consolas", 9), padding=(8, 3))
        self.style.map("W.TButton", background=[("active", "#475569"), ("disabled", "#333")])

        self.build_ui()

    def build_ui(self):
        top = tk.Frame(self.root, bg="#161b22", padx=8, pady=6)
        top.pack(fill="x")

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

        row3 = tk.Frame(top, bg="#161b22")
        row3.pack(fill="x", pady=4)

        self.parse_btn = ttk.Button(row3, text="ANALIZAR", style="P.TButton", command=self.parse_md)
        self.parse_btn.pack(side="left", padx=2)

        self.run_btn = ttk.Button(row3, text="EJECUTAR", style="G.TButton", command=self.run_all)
        self.run_btn.pack(side="left", padx=2)
        self.run_btn.state(["disabled"])

        self.skip_btn = ttk.Button(row3, text="SALTAR", style="Y.TButton", command=self.skip_instruction)
        self.skip_btn.pack(side="left", padx=2)
        self.skip_btn.state(["disabled"])

        self.stop_btn = ttk.Button(row3, text="PARAR", style="R.TButton", command=self.stop_execution)
        self.stop_btn.pack(side="left", padx=2)
        self.stop_btn.state(["disabled"])

        # Botón PROMPT - copiar instrucciones al portapapeles
        self.prompt_btn = ttk.Button(row3, text="PROMPT", style="W.TButton", command=self.copy_prompt)
        self.prompt_btn.pack(side="right", padx=2)

        # Botón CMD
        self.cmd_btn = ttk.Button(row3, text="CMD", style="C.TButton", command=self.open_cmd)
        self.cmd_btn.pack(side="right", padx=2)

        self.clear_btn = ttk.Button(row3, text="LIMPIAR", style="P.TButton", command=self.clear_log)
        self.clear_btn.pack(side="right", padx=2)

        self.stats_label = tk.Label(row3, text="", font=("Consolas", 8),
            fg="#64748b", bg="#161b22")
        self.stats_label.pack(side="right", padx=8)

        self.log = scrolledtext.ScrolledText(self.root,
            font=("Consolas", 9), bg="#0d1117", fg="#e2e8f0",
            insertbackground="#7c3aed", relief="flat", bd=0,
            wrap="word", state="disabled", padx=8, pady=4)
        self.log.pack(fill="both", expand=True)

        self.log.tag_configure("ok", foreground="#10b981")
        self.log.tag_configure("err", foreground="#ef4444")
        self.log.tag_configure("warn", foreground="#f59e0b")
        self.log.tag_configure("info", foreground="#3b82f6")
        self.log.tag_configure("cmd", foreground="#7c3aed")
        self.log.tag_configure("path", foreground="#06b6d4")
        self.log.tag_configure("head", foreground="#7c3aed", font=("Consolas", 9, "bold"))
        self.log.tag_configure("dim", foreground="#30363d")
        self.log.tag_configure("white", foreground="#e2e8f0")
        self.log.tag_configure("interactive", foreground="#f59e0b", font=("Consolas", 9, "bold"))

    def copy_prompt(self):
        """Copia el texto de instrucciones CONDOR al portapapeles"""
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

    def log_msg(self, msg, tag="white"):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")
        self.root.update_idletasks()

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.stats_label.config(text="")

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
        self.stop_all = True
        self.skip_current = True
        self.log_msg(">> DETENIENDO...", "err")

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
                cmds = inst["content"].replace("\n", " | ")[:70]
                is_inter = any(ic in inst["content"].lower() for ic in ["npm create", "npx create", "npm init"])
                tag = "interactive" if is_inter else "cmd"
                marker = " [INTERACTIVO]" if is_inter else ""
                self.log_msg(f"  {i:02d}. EXEC{marker} -> {cmds}...", tag)
            elif inst["action"] == "ELIMINAR":
                self.log_msg(f"  {i:02d}. DEL  -> {inst['filepath']}", "warn")
            else:
                lines = inst["content"].count("\n") + 1
                act = "NEW " if inst["action"] == "CREAR" else "MOD "
                self.log_msg(f"  {i:02d}. {act} -> {inst['filepath']} ({lines}L)", "cmd")

        self.log_msg("")
        self.log_msg("Listo. Presiona EJECUTAR para aplicar.", "ok")
        self.stats_label.config(text=" | ".join(f"{a}:{c}" for a, c in counts.items()))
        self.run_btn.state(["!disabled"])

    def extract_instructions(self, content):
        instructions = []
        pattern = r'ETIQUETA\[([^\]]+)\]\s*\n```(\w*)\n(.*?)```'
        matches = re.finditer(pattern, content, re.DOTALL)

        for match in matches:
            params_str = match.group(1)
            lang = match.group(2)
            code = match.group(3)
            params = [p.strip() for p in params_str.split(",")]

            if len(params) != 4:
                self.log_msg(f"ETIQUETA invalida ({len(params)} params): [{params_str}]", "warn")
                continue

            ubicacion, nombre, extension, accion = params
            accion = accion.upper().strip()

            if accion == "EJECUTAR" or nombre.lower() == "nan":
                filepath = "CMD"
            else:
                if ubicacion == ".":
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

    def run_all(self):
        if self.is_running:
            return
        if not self.instructions:
            return

        confirm = messagebox.askyesno("Confirmar",
            f"{len(self.instructions)} instrucciones.\nProyecto: {self.project_path.get()}\n\nContinuar?")
        if not confirm:
            return

        self.is_running = True
        self.stop_all = False
        self.run_btn.state(["disabled"])
        self.parse_btn.state(["disabled"])
        self.skip_btn.state(["!disabled"])
        self.stop_btn.state(["!disabled"])

        thread = threading.Thread(target=self.execute_instructions, daemon=True)
        thread.start()

    def execute_instructions(self):
        project = self.project_path.get()
        total = len(self.instructions)
        success = 0
        errors = 0
        skipped = 0

        self.log_msg("")
        self.log_msg("=" * 50, "dim")
        self.log_msg("EJECUTANDO", "head")
        self.log_msg("=" * 50, "dim")

        for i, inst in enumerate(self.instructions, 1):
            if self.stop_all:
                self.log_msg(f"DETENIDO en [{i}/{total}]", "err")
                break

            self.skip_current = False
            action = inst["action"]

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

        self.is_running = False
        self.root.after(0, lambda: self.run_btn.state(["!disabled"]))
        self.root.after(0, lambda: self.parse_btn.state(["!disabled"]))
        self.root.after(0, lambda: self.skip_btn.state(["disabled"]))
        self.root.after(0, lambda: self.stop_btn.state(["disabled"]))

    def create_file(self, project, inst):
        filepath = inst["filepath"]
        content = inst["content"]
        full_path = os.path.join(project, filepath.replace("/", os.sep))

        dir_path = os.path.dirname(full_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            self.log_msg(f"  mkdir: {dir_path}", "info")

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

    def is_interactive(self, cmd):
        cmd_lower = cmd.lower().strip()
        for ic in INTERACTIVE_COMMANDS:
            if cmd_lower.startswith(ic.lower()):
                return True
        return False

    def execute_cmd(self, project, commands):
        lines = [line.strip() for line in commands.strip().split("\n")
                 if line.strip() and not line.strip().startswith("#")]

        for cmd in lines:
            if self.skip_current or self.stop_all:
                self.log_msg(f"  SKIP: {cmd}", "warn")
                continue

            if self.is_interactive(cmd):
                self.log_msg(f"  [INTERACTIVO] {cmd}", "interactive")
                self.log_msg(f"  Abriendo CMD separada...", "warn")
                try:
                    process = subprocess.Popen(
                        f'start /wait cmd /k "cd /d {project} && {cmd} && echo. && echo LISTO. Cierra esta ventana. && pause"',
                        shell=True, cwd=project)
                    process.wait()
                    self.log_msg(f"  CMD cerrada. Continuando...", "ok")
                except Exception as e:
                    self.log_msg(f"  Error: {e}", "err")
                continue

            self.log_msg(f"  > {cmd}", "cmd")

            try:
                result = subprocess.run(cmd, shell=True, cwd=project,
                    capture_output=True, text=True, timeout=180)

                if result.stdout.strip():
                    for line in result.stdout.strip().split("\n")[:8]:
                        self.log_msg(f"    {line}", "info")

                if result.returncode != 0 and result.stderr.strip():
                    stderr = result.stderr.strip()
                    if "warn" in stderr.lower() or "notice" in stderr.lower():
                        for line in stderr.split("\n")[:3]:
                            self.log_msg(f"    {line[:100]}", "warn")
                    else:
                        for line in stderr.split("\n")[:5]:
                            self.log_msg(f"    {line[:120]}", "err")

                if result.returncode == 0:
                    self.log_msg(f"    OK", "ok")
                else:
                    self.log_msg(f"    exit:{result.returncode}", "warn")

            except subprocess.TimeoutExpired:
                self.log_msg(f"    TIMEOUT (>180s)", "err")
            except Exception as e:
                self.log_msg(f"    Error: {e}", "err")

    def run(self):
        self.log_msg("CONDOR v2.2", "head")
        self.log_msg("DIR: carpeta | .MD: instrucciones", "info")
        self.log_msg("ANALIZAR -> EJECUTAR | SALTAR | PARAR", "info")
        self.log_msg("CMD: terminal | PROMPT: copiar instrucciones IA", "info")
        self.log_msg("")
        self.root.mainloop()


if __name__ == "__main__":
    app = AutoBuilder()
    app.run()
