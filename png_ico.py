import os
from PIL import Image

# Esto obtiene la ruta de la carpeta donde está este archivo .py
directorio_actual = os.path.dirname(__file__)
ruta_png = os.path.join(directorio_actual, "condor.png")
ruta_ico = os.path.join(directorio_actual, "condor.ico")

try:
    img = Image.open(ruta_png)
    img.save(ruta_ico, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Éxito: Icono generado en {ruta_ico}")
except FileNotFoundError:
    print(f"Error: No encontré el archivo 'condor.png' en {directorio_actual}")