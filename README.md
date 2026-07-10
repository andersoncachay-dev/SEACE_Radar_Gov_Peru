
# SEACE Radar Gov Peru v6 - RUC + CRM

Versión v6 con columna **RUC** antes de **Entidad** en pantalla y Excel.

## Ejecutar

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Nota

SEACE Público no muestra el RUC en la grilla principal de procedimientos. Por eso esta versión crea la columna `ruc` vacía y la deja lista para la siguiente fase: extraer RUC desde el detalle del proceso o desde una tabla maestra de entidades.
