# SEACE Radar Gov Peru v10.7 - Scraper por click en Ver detalle

Reemplaza este archivo:
- `src/seace_menor8_scraper.py`

Cambio principal:
- Ya no depende de `detalle_url`. Para cada proceso `CM-*`, vuelve al listado, localiza la tarjeta y hace click en `Ver detalle`.
- Luego extrae Consulta, Cotización y PDF/TDR desde la pantalla real de detalle.

Si el click falla, se generan archivos `debug_*` HTML en la raíz del proyecto para revisar el DOM exacto.
