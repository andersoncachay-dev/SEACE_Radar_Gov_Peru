
# SEACE Radar Gov Peru v7 - Estado y Fechas de Procesos

Versión v7 con:

- Columna **Estado Comercial**: Vigente / En evaluación / Cerrado / Revisar.
- Columnas **Fecha Presentación** y **Fecha Buena Pro**.
- Columna **RUC** antes de Entidad.
- Opción de abrir detalle del proceso para enriquecer RUC y cronograma.
- Exportación Excel con hojas: Oportunidades, Resumen y CRM_Entidades.

## Ejecutar

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Uso recomendado

1. Seleccionar **SEACE Público - navegador automático**.
2. Keyword: `satelital`.
3. Año: `2026`.
4. Activar **Navegador visible**.
5. Opcional: activar **Enriquecer con detalle** para capturar RUC y cronograma de los primeros procesos.

## Nota técnica

La grilla principal de SEACE muestra la relación de procesos, pero no siempre incluye RUC ni todas las fechas del cronograma. Para completarlas, v7 intenta abrir el detalle de cada proceso cuando puede identificar el enlace de ficha.
