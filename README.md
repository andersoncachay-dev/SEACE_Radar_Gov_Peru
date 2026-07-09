
# SEACE Radar Gov Peru v5 - Browser Auto

Esta versión agrega un conector automático con navegador real usando Selenium. Es el enfoque correcto para SEACE Público cuando el formulario usa JSF/PrimeFaces/reCAPTCHA/JS del navegador y `requests` devuelve la página base sin resultados.

## Ejecutar

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Uso recomendado

1. Selecciona **SEACE Público - navegador automático**.
2. Keyword: `satelital`.
3. Año: `2026`.
4. Deja **Navegador visible** activado.
5. Pulsa **Buscar con navegador**.

La app abrirá Chrome, llenará el formulario, hará clic en Buscar y leerá la tabla HTML resultante.
