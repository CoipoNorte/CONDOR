# CONDOR v5.0

Automatizador de proyectos desde archivos .md — Un puente entre tu IA y tu proyecto real.

## Que es CONDOR?

Le pides algo a una IA, copias su respuesta y CONDOR construye todo el proyecto automaticamente.
Sin abrir VSCode. Sin copiar/pegar archivo por archivo. Sin ejecutar comandos uno por uno.

    Tu le pides algo a la IA
            |
    La IA responde con formato ETIQUETA[...]
            |
    Copias la respuesta (Ctrl+C)
            |
    En CONDOR presionas PASTE (Ctrl+V)
            |
    CONDOR construye todo el proyecto solo

## Requisitos

    - Python 3.10+
    - Windows 10/11
    - Node.js (opcional, para proyectos web)

## Instalacion

    pip install pystray pillow

Opcional para drag and drop:

    pip install tkinterdnd2

## Ejecutar

    python condor.py

## Compilar a .exe

    rd /s /q build dist
    pyinstaller CONDOR.spec

El ejecutable queda en dist/CONDOR.exe

## Interfaz

    DIR  [carpeta del proyecto...............] [..]
    MD   [archivo de instrucciones...........] [..]

    SCAN  RUN  SKIP  STOP  |  PASTE  UNDO
                              PROMPT  CMD  OPEN  CLR

    [ ] Auto-run  [ ] Dry-run  [x] Backup  [x] CMD SEP

    [=============================] barra de progreso

    LOG de ejecucion...

    Ready                    node v20.x | npm 10.x

## Botones

    SCAN    Ctrl+S    Analiza el .md y muestra instrucciones detectadas
    RUN     Ctrl+R    Ejecuta todas las instrucciones
    SKIP              Salta la instruccion actual y mata el proceso
    STOP    Esc       Detiene toda la ejecucion y mata procesos activos
    PASTE   Ctrl+V    Pega respuesta de la IA y analiza automaticamente
    UNDO    Ctrl+Z    Restaura el ultimo archivo modificado
    PROMPT            Copia las instrucciones del formato al portapapeles
    CMD               Abre terminal CMD en la carpeta del proyecto
    OPEN    Ctrl+O    Abre el explorador de archivos en el proyecto
    CLR               Limpia el log

## Checkboxes

    Auto-run    Ejecuta automaticamente despues de analizar
    Dry-run     Simula la ejecucion sin hacer cambios reales
    Backup      Guarda copia de archivos antes de modificarlos
    CMD SEP     npm/npx/python/node se abren en ventana CMD separada

## Formato de instrucciones

Cada instruccion tiene esta estructura:

    ETIQUETA[ubicacion,nombre,extension,accion]
    INICIO_BLOQUE
    ...contenido...
    FIN_BLOQUE

### Parametros

    ubicacion   Ruta relativa desde la raiz (usar . para la raiz)
    nombre      Nombre del archivo sin extension (nan para comandos)
    extension   Extension del archivo (js, jsx, css, py, cmd, etc.)
    accion      CREAR | MODIFICAR | EJECUTAR | ELIMINAR | REEMPLAZAR

### Acciones

    CREAR       Crea un archivo nuevo con el contenido del bloque
    MODIFICAR   Reemplaza TODO el contenido de un archivo existente
    EJECUTAR    Ejecuta comandos en la terminal CMD de Windows
    ELIMINAR    Elimina el archivo indicado
    REEMPLAZAR  Busca texto exacto en el archivo y lo sustituye

### Reglas de INICIO_BLOQUE y FIN_BLOQUE

    1. SIEMPRE usar INICIO_BLOQUE y FIN_BLOQUE para todo
    2. INICIO_BLOQUE va solo en su linea despues de la ETIQUETA
    3. FIN_BLOQUE va solo en su linea al final del contenido
    4. FIN_BLOQUE debe estar en columna 0 (sin espacios antes)
    5. El contenido puede tener cualquier cosa adentro:
       triple comillas, backticks, otros ETIQUETA[], etc.

### Reglas del REEMPLAZAR

    Usar >>> en una linea sola como separador
    Antes de >>> = texto exacto a buscar
    Despues de >>> = texto que lo reemplaza

## Ejemplos

### Ejecutar comandos

    ETIQUETA[.,nan,cmd,EJECUTAR]
    INICIO_BLOQUE
    npm install
    npm install express
    INICIO_BLOQUE

### Crear archivo

    ETIQUETA[src,App,jsx,CREAR]
    INICIO_BLOQUE
    export default function App() {
      return <h1>Hola</h1>
    }
    FIN_BLOQUE

### Reemplazar lineas

    ETIQUETA[src,App,jsx,REEMPLAZAR]
    INICIO_BLOQUE
      return <h1>Hola</h1>
    >>>
      return <h1>Hola Mundo</h1>
    FIN_BLOQUE

### Eliminar archivo

    ETIQUETA[src,viejo,js,ELIMINAR]
    INICIO_BLOQUE
    eliminado
    FIN_BLOQUE

## Flujo de trabajo

    1. Abre CONDOR y selecciona la carpeta del proyecto en DIR
    2. Presiona PROMPT para copiar las instrucciones del formato
    3. Pega las instrucciones al inicio de tu chat con la IA
    4. Pidele a la IA lo que necesitas
    5. Copia la respuesta completa de la IA (Ctrl+A, Ctrl+C)
    6. En CONDOR presiona PASTE (Ctrl+V)
    7. Revisa las instrucciones en el log
    8. Presiona RUN
    9. CONDOR hace todo solo

## Caracteristicas

    - Crea, modifica, elimina y reemplaza archivos automaticamente
    - Ejecuta comandos CMD con soporte de SKIP y STOP en tiempo real
    - PASTE directo desde portapapeles sin guardar .md manualmente
    - UNDO para deshacer el ultimo cambio
    - Backup automatico antes de modificar archivos
    - Dry-run para simular sin ejecutar
    - CMD SEP abre npm/npx/python/node en ventana separada
    - SKIP mata el proceso actual y pasa al siguiente
    - STOP mata todo y detiene la ejecucion
    - Drag and Drop de carpetas y archivos .md
    - Barra de progreso visual
    - Minimiza a bandeja del sistema al cerrar con X
    - Guarda configuracion y ultima carpeta usada
    - Detecta version de Node.js y npm
    - Proteccion contra rutas peligrosas del sistema
    - Sonido al completar la ejecucion
    - Parser robusto con INICIO_BLOQUE / FIN_BLOQUE
    - El contenido puede tener backticks, comillas, cualquier cosa
    - Tooltips en todos los botones
    - Atajos de teclado para todo

## Estructura del proyecto

    condor.py        Aplicacion principal
    condor.ico       Icono de la aplicacion
    CONDOR.spec      Configuracion de PyInstaller
    README.md        Este archivo

## CONDOR.spec para compilar

    block_cipher = None

    a = Analysis(
        ['condor.py'],
        datas=[('condor.ico', '.')],
        hiddenimports=['pystray', 'PIL', 'PIL.Image', 'PIL._imagingtk'],
    )

    pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name='CONDOR',
        debug=False,
        strip=False,
        upx=True,
        console=False,
        icon='condor.ico',
    )

## Por que usar CONDOR?

    Sin CONDOR:
        - Copias el codigo de la IA
        - Abres VSCode
        - Creas el archivo manualmente
        - Pegas el contenido
        - Repites para cada archivo (10, 20, 50 veces)
        - Ejecutas los comandos uno por uno
        - Tardas 30 minutos

    Con CONDOR:
        - Copias la respuesta completa de la IA
        - Presionas PASTE
        - Presionas RUN
        - Todo listo en 30 segundos
        - Sin abrir VSCode

## Creditos

    Usuario por defecto para proyectos con login:
        username: admin
        password: admin123

## Licencia

Proyecto libre. Hecho con CONDOR v5.0
