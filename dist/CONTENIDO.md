0. **Para crear el exe**:
   - Necesitarás instalar: `pyinstaller`, `pystray`, `Pillow`
   - Comando sugerido: 
     ```
     pyinstaller --onefile --windowed --icon=condor.ico --add-data "condor.ico;." CONDOR.py
     ```
   - Nota: `pystray` y `Pillow` deben estar instalados en tu entorno
