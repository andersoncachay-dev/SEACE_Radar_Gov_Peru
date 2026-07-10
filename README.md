
# SEACE Radar Gov Peru v9 - Cronograma y Nueva Vigencia

Versión v9 enfocada en el cronograma real de SEACE.

## Cambios principales

- Extrae la tabla de cronograma con estructura: **Etapa | Fecha Inicio | Fecha Fin**.
- Agrega columnas por etapa:
  - convocatoria_inicio / convocatoria_fin
  - registro_inicio / registro_fin
  - consulta_inicio / consulta_fin
  - absolucion_inicio / absolucion_fin
  - integracion_inicio / integracion_fin
  - propuesta_inicio / propuesta_fin
  - evaluacion_inicio / evaluacion_fin
  - buena_pro_inicio / buena_pro_fin
- Nueva lógica de vigencia:
  - 🟢 Vigente para Consultas y Propuesta: si aún no vence Formulación de consultas y observaciones.
  - 🟡 Vigente sólo para Propuesta: si ya cerraron consultas, pero aún no vence Presentación de propuestas.
  - 🟠 En Evaluación: si ya venció la propuesta y aún no corresponde marcar Buena Pro cerrada.
  - 🔴 Cerrado: si la fecha de Buena Pro ya pasó.
- Orden por fecha de publicación descendente.
- Exportación Excel con hojas: Oportunidades, Resumen, CRM_Entidades y Cronograma_Detalle.

## Ejecutar

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```
