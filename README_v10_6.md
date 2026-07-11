# SEACE Radar Gov Peru v10.6 - Corrección cronograma Consulta + PDF click robusto

Archivos incluidos:
- app.py
- src/seace_menor8_scraper.py
- src/exporter.py

Cambios principales:
1. Cronograma Menores a 8 UIT:
   - Fallback de texto más robusto para detectar `Consulta` aunque el HTML no use tabla clásica.
   - Recorta el bloque `Cronograma` y asigna las primeras 4 fechas como Consulta/Cotización cuando corresponde.
   - Si no logra extraer Consulta, guarda `cronograma_debug` para diagnóstico en Excel.

2. Descarga PDF/TDR:
   - Mejora el click de descarga buscando elementos por texto/href: `Descargar requerimiento`, `requerimiento`, `TDR`, `.pdf`, `descargar`.
   - Vigila `exports/requerimientos_menores8uit/` y la carpeta `Descargas` del usuario; si detecta el archivo, lo copia al proyecto.

3. Exporter:
   - Incluye `cronograma_debug` para validar el texto exacto cuando falte Consulta.

Instalación:
- Reemplaza `app.py`, `src/seace_menor8_scraper.py` y `src/exporter.py`.
- Ejecuta: `python -m streamlit run app.py`.
