Copia la carpeta `govradar-design-handoff/` dentro del repo como `docs/design/` y pega esto en Claude Code, desde la raíz del repositorio:

---

Vamos a rediseñar el frontend de GovRadar (frontend/) siguiendo el handoff aprobado en docs/design/.

1. Lee primero docs/design/HANDOFF.md completo, luego docs/design/tokens.css, docs/design/brand.ts y los mockups en docs/design/mockups/ (son HTML de referencia: toma estructura, medidas y estilos; ignora support.js y los bloques <script type="text/x-dc">).
2. Revisa frontend/src/main.tsx, frontend/src/shared.tsx, frontend/src/styles.css y frontend/src/pages/ para entender lo que existe.
3. Antes de escribir código, propónme un plan corto para la Fase 0 y la Fase 1 (archivos a crear/modificar) y espera mi OK.
4. Trabaja una fase por vez, en una rama `redesign/fase-N`, y al terminar cada fase: corre `npm run build` en frontend/, resume qué cambió y qué queda pendiente.

Reglas: no toques backend, endpoints ni lógica de negocio (salvo leer/guardar la clave `tenant_brand` en app_settings en la fase de marca); no agregues librerías de UI ni Tailwind; todo valor visual sale de tokens.css.

Empieza por el paso 1.
