# CONDOR — Instrucciones para el asistente

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
mkdir src\components
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

Por favor, sigue este formato en todas tus respuestas cuando me des código para crear o modificar archivos del proyecto. Gracias!