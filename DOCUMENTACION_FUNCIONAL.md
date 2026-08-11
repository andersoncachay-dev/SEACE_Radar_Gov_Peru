# Documentación funcional — SEACE Radar / GovRadar

Este documento explica, en español y a nivel de negocio + técnico, qué hace cada función principal del sistema para **Perú, Chile y Argentina**, de dónde trae la información y en qué tablas la guarda. Complementa a `CLAUDE.md` (guía técnica para agentes de código, en inglés) y a `PRODUCT.md` (visión de producto/marca).

---

## 1. Búsqueda Manual

**Qué es:** una búsqueda puntual que dispara el propio usuario desde la pantalla de Oportunidades, llenando un formulario (palabra clave, año, módulo/país) y pulsando el botón de ejecutar. A diferencia del Update Automático, no depende de una lista de palabras clave del Radar ni de una programación — es "quiero buscar esto ahora mismo".

**Cómo se dispara:**
1. El frontend (`frontend/src/pages/OpportunitiesPage.tsx`) arma la búsqueda y llama `POST /runs/start`.
2. El backend (`backend/app/routers/runs.py::start_run`) crea un registro `ScrapeRun` con estado `queued` y delega el trabajo real a una tarea en segundo plano: `services/run_service.py::execute_scrape_run`.
3. Esa función revisa el campo `source` del perfil/payload y decide **de dónde traer los datos** según el módulo elegido:

| Módulo en la UI | `source` interno | De dónde consulta | Cómo consulta |
|---|---|---|---|
| SEACE Público (Perú) | `seace_public_browser` | Portal público de SEACE | Navegador automatizado (Selenium) — `src/seace_browser_scraper.py::search_seace_public_browser`, filtra por palabra clave/año/versión y opcionalmente visita la ficha de cada proceso para enriquecer detalle. |
| Contratos Menores a 8 UIT (Perú) | `menor8_browser` | Portal SEACE (módulo de menor cuantía) | **Deshabilitado por defecto** (`ENABLE_MENOR8_MODULE=false`) — el módulo se considera inestable, no se usa en producción. |
| Oportunidades Chile LMP-GC | `mercado_publico_lmp_gc` | Portal Mercado Público (Chile) | Descarga masiva vía Excel del portal (`search_mercado_publico_bulk_excel`) filtrando por rango de fecha de cierre y palabra clave, y luego visita solo las fichas de detalle de los procesos que lo requieren (nuevos o con cambio de estado/fecha) — mismo motor que usa el Update Automático de Chile. |
| Botón "Buscar Fecha en Mercado Público CL" | (revalidación puntual) | Portal Mercado Público (Chile) | Consulta directa a la ficha de **un solo proceso ya guardado**, por su código de nomenclatura (`search_mercado_publico_details_by_code`) — sirve para refrescar fechas de un proceso puntual sin correr una búsqueda completa. |
| Buscador Argentina — Procesos | `comprar_argentina_procesos` | COMPR.AR — Contrataciones gestionadas electrónicamente | Completa la búsqueda avanzada en `BuscarAvanzado.aspx`, descarga el reporte Excel y normaliza todos los resultados. La búsqueda exacta por código también visita la ficha para recuperar el cronograma y los documentos. |
| Buscador Argentina — Publicaciones | `comprar_argentina_publicaciones` | COMPR.AR — Publicaciones gestionadas fuera del sistema electrónico | Consulta `BuscarAvanzadoPublicacion.aspx`. Como esta fuente no ofrece Excel, recorre las páginas de resultados del formulario ASP.NET hasta agotar la paginación y normaliza cada publicación. La consulta exacta por código visita su ficha de detalle. |

En Argentina, el formulario general permite **una sola palabra clave por ejecución**, uno o varios años, meses específicos o todos los meses, y el alcance comercial `Vigentes` o `Todos`. La opción **Agregar a la búsqueda actual** conserva la lista existente y suma únicamente procesos nuevos o actualizados; **Iniciar nueva búsqueda** reemplaza el conjunto visible por la nueva consulta. El resumen de procesos identificados muestra inicialmente una sola fila y permite desplegar el resto con **Ver más**.

La búsqueda específica por nomenclatura permite consultar un proceso o publicación puntual. En Procesos recupera el cronograma de la ficha; en Publicaciones el botón **Buscar / actualizar fechas en COMPR.AR** vuelve a leer la ficha y actualiza las fechas oficiales.

**Dónde almacena:**
- Cada ejecución crea/actualiza un registro en **`scrape_runs`** (estado `queued → running → completed/failed/cancelled`, mensajes de progreso, cantidad de filas encontradas). El usuario puede ver el avance en vivo y cancelarlo (`POST /runs/{id}/cancel`).
- Los procesos encontrados se combinan (upsert) en la tabla **`opportunities`** vía `services/ingestion_service.py::upsert_opportunities`: si el proceso ya existía (mismo `source` + `external_id`) se actualiza; si cambió algo relevante (fecha, estado, monto, documento), se guarda una copia del estado anterior en **`opportunity_snapshots`** — esto es lo que permite ver el historial de cambios de un proceso sin depender de un Excel aparte.
- El acceso está controlado por el país habilitado del usuario (`access_profile`: Perú/Chile/Argentina/ambos) — no se puede lanzar ni ver una búsqueda de un país al que el usuario no tiene acceso.

---

## 2. Update Automático ("Radar Automático")

**Qué es:** el motor que revisa por su cuenta, sin que nadie abra la aplicación, si aparecieron procesos nuevos que coincidan con las palabras clave del negocio (tabla `radar_keywords`, configurable por país desde la UI). Es la función que sostiene la promesa central del producto: detectar oportunidades sin trabajo manual diario.

**De dónde consulta (por país, `backend/app/radar_config.py`):**
- **Perú** → fuente `oece_ocds_api`: la **API oficial abierta del Estado peruano** "Contrataciones Abiertas" (OCDS) en `https://contratacionesabiertas.oece.gob.pe/api/v1` — es una API de datos, no requiere navegador/Selenium (`src/oece_ocds_connector.py::search_oece_ocds`).
- **Chile** → fuente `mercado_publico_lmp_gc`: el mismo scraper de Mercado Público que usa la Búsqueda Manual (bulk Excel + fichas de detalle), pero disparado con la bandera `automatic_incremental=True`, que acota la ventana de búsqueda a "mes actual + mes siguiente" (por fecha de cierre) y evita revisitar procesos que ya se vieron sin cambios — así cada corrida es barata en vez de repetir una búsqueda completa.
- **Argentina** → fuentes `comprar_argentina_procesos` y `comprar_argentina_publicaciones`: por cada palabra clave activa se consulta **ambos buscadores de COMPR.AR**. Procesos usa el reporte Excel; Publicaciones recorre todas las hojas HTML porque el portal no ofrece descarga masiva. La ventana incremental se calcula por fecha de apertura desde **7 días antes hasta 33 días después** del día de ejecución. Los resultados nuevos o modificados de ambas fuentes se agregan a la misma base acumulada, aunque su plazo comercial ya haya vencido.

**Cómo decide qué palabras buscar:** `services/scheduler_service.py::sync_radar_profiles` genera automáticamente un perfil de búsqueda (`search_profiles`) por cada combinación país × palabra clave activa y, para Argentina, además por cada fuente (Procesos y Publicaciones), con el nombre `"Radar automático · {país} · {keyword}"`. También desactiva los perfiles que ya no correspondan a una palabra clave vigente. Estos perfiles automáticos son distintos de los perfiles manuales que un usuario puede crear a mano.

**Cómo se dispara (dos modos, mismo código de fondo):**
- **Modo local / Docker** (`ENABLE_SCHEDULER=true`): un scheduler interno (APScheduler) vive dentro del propio proceso de la API y llama a `enqueue_active_profiles(country)` cada cierto intervalo (`SCHEDULER_INTERVAL_MINUTES`, 15 min por defecto).
- **Modo producción / Azure** (`EXTERNAL_SCHEDULER_ENABLED=true`, el que corre hoy en Azure): no hay un proceso vivo escuchando. En su lugar, un **Container Apps Job** de Azure dispara por cron (cada 15 minutos, en horarios distintos para Perú, Chile y Argentina para repartir la carga) al script `backend/app/ingestion_worker.py`. Este script primero consulta la tabla **`app_settings`** para ver si ya pasó el intervalo real configurado para ese país (15 min por defecto, editable desde `Sistema > Verificación automática` sin necesidad de tocar el cron de Azure); si todavía no toca, no hace nada; si ya toca, ejecuta la ingesta real y anota en `app_settings` cuándo debe volver a tocar.
- **Botón "Actualizar ahora" (por país)** en la UI de Sistema: llama a `POST /runs/scheduler/trigger?country=...`, que fuerza una ejecución inmediata sin esperar el intervalo y reprograma el próximo vencimiento automático a partir de ese momento.

**Dónde almacena:** exactamente igual que la Búsqueda Manual — un `ScrapeRun` por corrida, los procesos nuevos/actualizados quedan en `opportunities`, los cambios quedan en `opportunity_snapshots`. Además, el propio mecanismo de programación guarda su estado (próximo vencimiento, intervalo vigente por país) en `app_settings`, para que el cron de Azure sepa si "ya le tocaba" ejecutar o no.

La tabla de Oportunidades no representa solamente el resultado de la última corrida: muestra la **unión persistida** de oportunidades encontradas por updates automáticos y búsquedas manuales. El filtro usado para consultar la fuente (`Vigentes` o `Todos`) define qué se intenta encontrar en esa ejecución, pero no elimina de la tabla los registros anteriores ni los procesos vencidos.

---

## 3. Módulo Argentina — COMPR.AR

El módulo Argentina integra en una sola experiencia las contrataciones electrónicas y las publicaciones informativas de COMPR.AR, manteniendo separado el origen de cada registro para aplicar la navegación, las fechas y la descarga de documentos correctas.

### 3.1 Páginas del módulo

- **Inicio Argentina:** resumen comercial por año con KPIs de procesos radar, prioridad A, vigentes, cerrados y monto detectado; mapa SVG por provincia; distribución regional; buscador, ordenamiento, exportación y listado de oportunidades. Cada tarjeta identifica al lado del semáforo si el registro es **Proceso** o **Publicación**.
- **Buscador Argentina:** único acceso de navegación para las dos fuentes. Dentro de la página se elige entre Procesos y Publicaciones y se conservan los períodos y palabras clave activos de cada búsqueda.
- **Histórico Procesos Eliminados AR:** conserva los registros retirados de la sección y permite restaurarlos; retirarlos de la vista no borra la información recolectada.
- **Seguimiento de Oportunidades Argentina:** usa el flujo común de fases, etapas, áreas, responsables, comentarios y alertas del CRM.

### 3.2 Origen y tratamiento de los datos

| Tipo | Fuente | Identificador | Obtención de resultados | Detalle |
|---|---|---|---|---|
| Proceso | `comprar_argentina_procesos` | Número de proceso | Reporte Excel de COMPR.AR | Ficha del proceso, cronograma y documentos mediante navegación/postbacks ASP.NET. |
| Publicación | `comprar_argentina_publicaciones` | Número de publicación | Paginación completa de resultados HTML | Ficha de la convocatoria, cronograma y anexos descargables. |

Los procesos y publicaciones se deduplican por `source + external_id`, por lo que una actualización modifica el registro correcto sin confundir elementos con códigos similares de fuentes distintas. Cuando no se puede asignar una provincia a partir de la entidad o el detalle, el registro queda en la región nacional **Argentina** para no perderlo del mapa ni de los totales.

### 3.3 Fechas y semáforo comercial

Para **Procesos**, la ficha aporta fecha de publicación, inicio y fin de consultas y fecha del acto de apertura; esta última se usa como fin de propuesta. Para **Publicaciones**, el mapeo funcional es:

| Campo del CRM | Campo de la ficha de Publicaciones COMPR.AR |
|---|---|
| Fecha de convocatoria | Fecha de publicación |
| Fin Consultas | Fin de consultas |
| Fin Propuesta | Fin de recepción de documentación |

Si la ficha oficial muestra **Sin datos cargados**, el CRM conserva y presenta ese texto en rojo después de la validación, en vez de inventar una fecha o dejar ambiguo el resultado.

El semáforo se recalcula con las fechas vigentes:

- **Verde — Vigente para Consultas y Propuestas:** todavía admite consultas y propuestas.
- **Amarillo — Vigente para Propuesta:** el plazo de consultas terminó, pero aún se puede presentar propuesta o documentación.
- **Rojo — Proceso Culminado:** venció el plazo de propuesta o el estado oficial es terminal.

También se respetan los estados oficiales de COMPR.AR. `Adjudicado`, `Dejado Sin Efecto`, `Fracasado` y `Desierto` se consideran terminales; los estados de apertura, evaluación, análisis o adjudicación pendiente permanecen en curso según sus fechas. El semáforo **clasifica** los registros, pero no los elimina: todos los procesos provenientes de updates automáticos y búsquedas manuales continúan visibles en la tabla.

### 3.4 Fichas y documentos

El modal de detalle permite buscar documentos en la fuente oficial y guardarlos en el repositorio local del proceso:

- En Procesos, el servicio reproduce las acciones ASP.NET de COMPR.AR para descargar pliegos generales, cláusulas, actos y anexos.
- En Publicaciones, usa la ruta específica de anexos de convocatoria (`/Publicacion/Convocatoria/DescargarArchivo?idAnexo=...`).
- Los archivos se registran en **`documents`** y se almacenan bajo `exports/documents/{opportunity_id}`.
- Una sección independiente ofrece el enlace **Ver detalle del proceso completo en COMPR.AR**; el enlace no se repite en cada documento.

La implementación principal se encuentra en `src/comprar_argentina_scraper.py`, `backend/app/radar_config.py`, `backend/app/services/run_service.py` y `backend/app/services/document_service.py`.

---

## 4. Seguimiento de Oportunidades

**Qué es:** el flujo interno de trabajo una vez que un proceso ya fue detectado — asignarlo a un área/responsable, hacerlo avanzar por etapas (fases) hasta la decisión de cotizar o no, y avisar cuando una etapa está por vencer.

**Cómo funciona:**
- `services/tracking_service.py::start_tracking` crea un registro en **`opportunity_tracking`** (1 a 1 con la oportunidad) y genera sus etapas (**`opportunity_tracking_stages`**) a partir de las plantillas reutilizables configuradas por país (**`tracking_phases`** → **`tracking_stage_templates`**), con fechas límite calculadas automáticamente (ej. `compute_cotizacion_due_dates`).
- Cada etapa puede asignarse a una o varias áreas (**`tracking_areas`**) y responsables (**`tracking_responsibles`**) — tablas de catálogo administrables desde `Sistema`.
- `advance_phase` / `toggle_stage` mueven el proceso de fase o marcan una etapa como completa.
- `evaluate_time_status_alerts` revisa periódicamente cada etapa activa contra su fecha límite y calcula un estado ("Atender" / "Urgente"); dispara el aviso una sola vez por nivel (se guarda un flag en la propia etapa para no repetir el correo).
- `services/tracking_date_refresh_service.py` (`_refresh_peru` / `_refresh_chile`) vuelve a consultar la fuente original — **el portal de SEACE por navegador para Perú** (`search_seace_public_browser_targets`, mismo motor que la Búsqueda Manual, no la API OCDS) y **la ficha de Mercado Público por código para Chile** (`search_mercado_publico_details_by_code`) — para los procesos que siguen en seguimiento activo, y si detecta un cambio de fecha avisa al responsable.
- Argentina puede usar todo el flujo común de seguimiento. La revalidación de sus fechas se realiza actualmente desde la búsqueda exacta o el botón **Buscar / actualizar fechas en COMPR.AR** de la oportunidad; todavía no forma parte del refresco masivo periódico de fechas de `tracking_date_refresh_service.py`.
- Se dispara igual que el Update Automático: modo embebido local, o Azure con el mismo patrón de "cron + verificación de intervalo guardado en `app_settings`" (cada 30 min para alertas de vencimiento, cada 3 horas para el refresco de fechas, ambos editables desde `Sistema > Verificación automática`).

**Dónde consulta:** SEACE (navegador) para Perú y Mercado Público (ficha por código) para Chile. En Argentina, la actualización puntual consulta la ficha de Procesos o Publicaciones en COMPR.AR. La actualización masiva periódica de seguimiento continúa limitada a Perú y Chile.

**Dónde almacena:** `opportunity_tracking`, `opportunity_tracking_stages` (y sus tablas puente de áreas/responsables asignados), más un flujo aparte de revisión/standby en `opportunity_reviews` / `opportunity_review_comments`.

---

## 5. Alertas y Notificaciones

**Qué es:** dos mecanismos separados de aviso automático:

1. **Alertas de nuevas oportunidades** (`services/notification_service.py`): compara los procesos en `opportunities` contra reglas configuradas por el usuario (**`alert_rules`**: palabra clave, prioridad mínima, país, horas antes del vencimiento) y genera una **`alert`** pendiente por cada coincidencia (sin duplicar, gracias a una restricción única por proceso+regla+tipo de alerta).
2. **Alertas de Seguimiento** (vencimiento de etapas, cambio de fechas) — descritas en la sección 4, van por una tabla/flujo distinto (`opportunity_tracking_stage_assignees`, notificaciones directas al responsable).

**Cómo se envían:** `send_pending_alerts` revisa el canal de cada alerta pendiente:
- **Email**: por Azure Communication Services (si `EMAIL_PROVIDER=azure`) o por SMTP genérico (por defecto, hoy usando Brevo/`smtp-relay.brevo.com` en producción).
- **WhatsApp**: por Azure Communication Services con plantillas aprobadas, o por un webhook HTTP genérico — **actualmente deshabilitado** (`WHATSAPP_ENABLED=false`) hasta contar con el canal/número aprobado.
- Si el envío falla, la alerta queda en reintento con backoff (`attempt_count` / `next_attempt_at`) hasta un máximo de intentos (`ALERT_MAX_ATTEMPTS`, 5 por defecto), y después queda marcada como `failed`.

**Dónde almacena:** `alert_rules` (configuración) y `alerts` (cada aviso individual, con su estado: pendiente/enviado/reintentando/fallido).

---

## 6. Autenticación y Permisos

**Qué es:** control de acceso por usuario y por país.

- El login (`POST /auth/login`) devuelve un token propio firmado (HMAC-SHA256, no un JWT de librería estándar) con expiración configurable (`ACCESS_TOKEN_MINUTES`, 12 horas por defecto). Las contraseñas se guardan con hash PBKDF2, nunca en texto plano.
- Cada usuario (**`users`**) tiene un `access_profile` (`peru`, `chile`, `argentina` o `both`) que determina qué país puede ver y operar — se valida tanto en el backend (incluidos los dos prefijos `comprar_argentina%`) como en la UI (oculta pantallas de países no habilitados). Para perfiles Argentina o multipaís, el alta admite el teléfono argentino con prefijo **+54**.
- El rol `admin` habilita pantallas adicionales: gestión de usuarios (`Usuarios`) y configuración del sistema (`Sistema`: intervalos de actualización automática, catálogos de áreas/responsables/plantillas, configuración de scoring, documentos legales).
- Recuperación de contraseña: flujo de "olvidé mi contraseña" con enlace temporal (`services/password_reset_service.py`, expira en `PASSWORD_RESET_MINUTES`, 30 min por defecto).

---

## Resumen de dónde vive cada dato

| Dato | Tabla principal |
|---|---|
| Procesos/oportunidades detectados (manual o automático) | `opportunities` |
| Historial de cambios de un proceso | `opportunity_snapshots` |
| Documentos y anexos recuperados de las fichas | `documents` + `exports/documents/{opportunity_id}` |
| Cada ejecución de búsqueda (manual o automática) | `scrape_runs` |
| Palabras clave del Radar Automático | `radar_keywords` |
| Perfiles de búsqueda (manuales y automáticos) | `search_profiles` |
| Próximo vencimiento/intervalo de cada automatización (Azure) | `app_settings` |
| Reglas y envíos de alertas de nuevas oportunidades | `alert_rules`, `alerts` |
| Seguimiento de una oportunidad y sus etapas | `opportunity_tracking`, `opportunity_tracking_stages` |
| Catálogo de áreas/responsables/plantillas de seguimiento | `tracking_areas`, `tracking_responsibles`, `tracking_phases`, `tracking_stage_templates` |
| Usuarios y permisos | `users` |

---

## Matriz funcional por país

| Capacidad | Perú | Chile | Argentina |
|---|---|---|---|
| Inicio, KPIs y mapa regional | Sí | Sí | Sí, por provincia + región nacional de respaldo |
| Búsqueda manual | SEACE | Mercado Público | COMPR.AR Procesos y Publicaciones |
| Update automático | API OCDS | Excel + fichas | Procesos Excel + Publicaciones paginadas |
| Acumulación manual + automática | Sí | Sí | Sí |
| Consulta exacta por código | Sí | Sí | Sí, con rutas distintas por tipo |
| Documentos/anexos | Sí | Sí | Sí |
| Histórico de retirados | Sí | Sí | Sí |
| Seguimiento comercial | Sí | Sí | Sí |
| Refresco masivo periódico de fechas en seguimiento | Sí | Sí | Pendiente; actualización puntual disponible |
