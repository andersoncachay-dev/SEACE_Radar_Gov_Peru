# Documentación funcional — SEACE Radar / GovRadar

Este documento explica, en español y a nivel de negocio + técnico, qué hace cada función principal del sistema, de dónde trae la información y en qué tablas la guarda. Complementa a `CLAUDE.md` (guía técnica para agentes de código, en inglés) y a `PRODUCT.md` (visión de producto/marca).

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

**Dónde almacena:**
- Cada ejecución crea/actualiza un registro en **`scrape_runs`** (estado `queued → running → completed/failed/cancelled`, mensajes de progreso, cantidad de filas encontradas). El usuario puede ver el avance en vivo y cancelarlo (`POST /runs/{id}/cancel`).
- Los procesos encontrados se combinan (upsert) en la tabla **`opportunities`** vía `services/ingestion_service.py::upsert_opportunities`: si el proceso ya existía (mismo `source` + `external_id`) se actualiza; si cambió algo relevante (fecha, estado, monto, documento), se guarda una copia del estado anterior en **`opportunity_snapshots`** — esto es lo que permite ver el historial de cambios de un proceso sin depender de un Excel aparte.
- El acceso está controlado por el país habilitado del usuario (`access_profile`: Perú/Chile/ambos) — no se puede lanzar ni ver una búsqueda de un país al que el usuario no tiene acceso.

---

## 2. Update Automático ("Radar Automático")

**Qué es:** el motor que revisa por su cuenta, sin que nadie abra la aplicación, si aparecieron procesos nuevos que coincidan con las palabras clave del negocio (tabla `radar_keywords`, configurable por país desde la UI). Es la función que sostiene la promesa central del producto: detectar oportunidades sin trabajo manual diario.

**De dónde consulta (por país, `backend/app/radar_config.py`):**
- **Perú** → fuente `oece_ocds_api`: la **API oficial abierta del Estado peruano** "Contrataciones Abiertas" (OCDS) en `https://contratacionesabiertas.oece.gob.pe/api/v1` — es una API de datos, no requiere navegador/Selenium (`src/oece_ocds_connector.py::search_oece_ocds`).
- **Chile** → fuente `mercado_publico_lmp_gc`: el mismo scraper de Mercado Público que usa la Búsqueda Manual (bulk Excel + fichas de detalle), pero disparado con la bandera `automatic_incremental=True`, que acota la ventana de búsqueda a "mes actual + mes siguiente" (por fecha de cierre) y evita revisitar procesos que ya se vieron sin cambios — así cada corrida es barata en vez de repetir una búsqueda completa.

**Cómo decide qué palabras buscar:** `services/scheduler_service.py::sync_radar_profiles` genera automáticamente un perfil de búsqueda (`search_profiles`) por cada combinación país × palabra clave activa, con el nombre `"Radar automático · {país} · {keyword}"`, y desactiva los que ya no correspondan a una palabra clave vigente. Estos perfiles automáticos son distintos de los perfiles manuales que un usuario puede crear a mano.

**Cómo se dispara (dos modos, mismo código de fondo):**
- **Modo local / Docker** (`ENABLE_SCHEDULER=true`): un scheduler interno (APScheduler) vive dentro del propio proceso de la API y llama a `enqueue_active_profiles(country)` cada cierto intervalo (`SCHEDULER_INTERVAL_MINUTES`, 15 min por defecto).
- **Modo producción / Azure** (`EXTERNAL_SCHEDULER_ENABLED=true`, el que corre hoy en Azure): no hay un proceso vivo escuchando. En su lugar, un **Container Apps Job** de Azure dispara por cron (cada 15 minutos, en horarios distintos para Perú y Chile para repartir la carga) al script `backend/app/ingestion_worker.py`. Este script primero consulta la tabla **`app_settings`** para ver si ya pasó el intervalo real configurado para ese país (15 min por defecto, editable desde `Sistema > Verificación automática` sin necesidad de tocar el cron de Azure); si todavía no toca, no hace nada; si ya toca, ejecuta la ingesta real y anota en `app_settings` cuándo debe volver a tocar.
- **Botón "Actualizar ahora" (por país)** en la UI de Sistema: llama a `POST /runs/scheduler/trigger?country=...`, que fuerza una ejecución inmediata sin esperar el intervalo y reprograma el próximo vencimiento automático a partir de ese momento.

**Dónde almacena:** exactamente igual que la Búsqueda Manual — un `ScrapeRun` por corrida, los procesos nuevos/actualizados quedan en `opportunities`, los cambios quedan en `opportunity_snapshots`. Además, el propio mecanismo de programación guarda su estado (próximo vencimiento, intervalo vigente por país) en `app_settings`, para que el cron de Azure sepa si "ya le tocaba" ejecutar o no.

---

## 3. Seguimiento de Oportunidades

**Qué es:** el flujo interno de trabajo una vez que un proceso ya fue detectado — asignarlo a un área/responsable, hacerlo avanzar por etapas (fases) hasta la decisión de cotizar o no, y avisar cuando una etapa está por vencer.

**Cómo funciona:**
- `services/tracking_service.py::start_tracking` crea un registro en **`opportunity_tracking`** (1 a 1 con la oportunidad) y genera sus etapas (**`opportunity_tracking_stages`**) a partir de las plantillas reutilizables configuradas por país (**`tracking_phases`** → **`tracking_stage_templates`**), con fechas límite calculadas automáticamente (ej. `compute_cotizacion_due_dates`).
- Cada etapa puede asignarse a una o varias áreas (**`tracking_areas`**) y responsables (**`tracking_responsibles`**) — tablas de catálogo administrables desde `Sistema`.
- `advance_phase` / `toggle_stage` mueven el proceso de fase o marcan una etapa como completa.
- `evaluate_time_status_alerts` revisa periódicamente cada etapa activa contra su fecha límite y calcula un estado ("Atender" / "Urgente"); dispara el aviso una sola vez por nivel (se guarda un flag en la propia etapa para no repetir el correo).
- `services/tracking_date_refresh_service.py` (`_refresh_peru` / `_refresh_chile`) vuelve a consultar la fuente original — **el portal de SEACE por navegador para Perú** (`search_seace_public_browser_targets`, mismo motor que la Búsqueda Manual, no la API OCDS) y **la ficha de Mercado Público por código para Chile** (`search_mercado_publico_details_by_code`) — para los procesos que siguen en seguimiento activo, y si detecta un cambio de fecha avisa al responsable.
- Se dispara igual que el Update Automático: modo embebido local, o Azure con el mismo patrón de "cron + verificación de intervalo guardado en `app_settings`" (cada 30 min para alertas de vencimiento, cada 3 horas para el refresco de fechas, ambos editables desde `Sistema > Verificación automática`).

**Dónde consulta:** SEACE (navegador) para Perú y Mercado Público (ficha por código) para Chile — igual que la Búsqueda Manual, no la API OCDS.

**Dónde almacena:** `opportunity_tracking`, `opportunity_tracking_stages` (y sus tablas puente de áreas/responsables asignados), más un flujo aparte de revisión/standby en `opportunity_reviews` / `opportunity_review_comments`.

---

## 4. Alertas y Notificaciones

**Qué es:** dos mecanismos separados de aviso automático:

1. **Alertas de nuevas oportunidades** (`services/notification_service.py`): compara los procesos en `opportunities` contra reglas configuradas por el usuario (**`alert_rules`**: palabra clave, prioridad mínima, país, horas antes del vencimiento) y genera una **`alert`** pendiente por cada coincidencia (sin duplicar, gracias a una restricción única por proceso+regla+tipo de alerta).
2. **Alertas de Seguimiento** (vencimiento de etapas, cambio de fechas) — descritas en la sección 3, van por una tabla/flujo distinto (`opportunity_tracking_stage_assignees`, notificaciones directas al responsable).

**Cómo se envían:** `send_pending_alerts` revisa el canal de cada alerta pendiente:
- **Email**: por Azure Communication Services (si `EMAIL_PROVIDER=azure`) o por SMTP genérico (por defecto, hoy usando Brevo/`smtp-relay.brevo.com` en producción).
- **WhatsApp**: por Azure Communication Services con plantillas aprobadas, o por un webhook HTTP genérico — **actualmente deshabilitado** (`WHATSAPP_ENABLED=false`) hasta contar con el canal/número aprobado.
- Si el envío falla, la alerta queda en reintento con backoff (`attempt_count` / `next_attempt_at`) hasta un máximo de intentos (`ALERT_MAX_ATTEMPTS`, 5 por defecto), y después queda marcada como `failed`.

**Dónde almacena:** `alert_rules` (configuración) y `alerts` (cada aviso individual, con su estado: pendiente/enviado/reintentando/fallido).

---

## 5. Autenticación y Permisos

**Qué es:** control de acceso por usuario y por país.

- El login (`POST /auth/login`) devuelve un token propio firmado (HMAC-SHA256, no un JWT de librería estándar) con expiración configurable (`ACCESS_TOKEN_MINUTES`, 12 horas por defecto). Las contraseñas se guardan con hash PBKDF2, nunca en texto plano.
- Cada usuario (**`users`**) tiene un `access_profile` (`peru`, `chile` o `both`) que determina qué país puede ver y operar — se valida tanto en el backend (filtra qué `source` puede consultar) como en la UI (oculta pantallas de países no habilitados).
- El rol `admin` habilita pantallas adicionales: gestión de usuarios (`Usuarios`) y configuración del sistema (`Sistema`: intervalos de actualización automática, catálogos de áreas/responsables/plantillas, configuración de scoring, documentos legales).
- Recuperación de contraseña: flujo de "olvidé mi contraseña" con enlace temporal (`services/password_reset_service.py`, expira en `PASSWORD_RESET_MINUTES`, 30 min por defecto).

---

## Resumen de dónde vive cada dato

| Dato | Tabla principal |
|---|---|
| Procesos/oportunidades detectados (manual o automático) | `opportunities` |
| Historial de cambios de un proceso | `opportunity_snapshots` |
| Cada ejecución de búsqueda (manual o automática) | `scrape_runs` |
| Palabras clave del Radar Automático | `radar_keywords` |
| Perfiles de búsqueda (manuales y automáticos) | `search_profiles` |
| Próximo vencimiento/intervalo de cada automatización (Azure) | `app_settings` |
| Reglas y envíos de alertas de nuevas oportunidades | `alert_rules`, `alerts` |
| Seguimiento de una oportunidad y sus etapas | `opportunity_tracking`, `opportunity_tracking_stages` |
| Catálogo de áreas/responsables/plantillas de seguimiento | `tracking_areas`, `tracking_responsibles`, `tracking_phases`, `tracking_stage_templates` |
| Usuarios y permisos | `users` |
