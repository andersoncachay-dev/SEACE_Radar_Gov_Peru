# GovRadar en Azure

## Arquitectura recomendada

- **Azure Container Apps / frontend:** React compilado y servido por Nginx.
- **Azure Container Apps / API:** FastAPI, con `ENABLE_SCHEDULER=false` y al menos una replica activa.
- **Azure Container Apps Job / ingestion-worker:** actualiza los perfiles de busqueda activos cada quince minutos.
- **Azure Container Apps Job / alert-worker:** ejecuta `python -m backend.app.alert_worker` cada cinco minutos, con paralelismo 1.
- **Azure Database for PostgreSQL Flexible Server:** base productiva y respaldos administrados.
- **Azure Container Registry:** imagenes privadas de API y frontend.
- **Azure Key Vault:** `DATABASE_URL`, `SECRET_KEY` y la conexion de Azure Communication Services.
- **Azure Communication Services Email:** correo desde un dominio verificado.
- **Azure Communication Services Advanced Messaging:** WhatsApp Business mediante una plantilla aprobada.
- **Log Analytics / Azure Monitor:** logs, ejecuciones del job y alarmas operativas.

El scheduler embebido en la API se desactiva en Azure. Si la API escala a dos replicas, un scheduler interno ejecutaria dos veces el mismo trabajo. El Container Apps Job se configura con una sola replica y reintentos controlados.

## Orden de implementacion

### 1. Recursos base

Crear un grupo de recursos y, dentro de el:

1. Azure Container Registry.
2. Container Apps Environment enlazado a Log Analytics.
3. PostgreSQL Flexible Server 16.
4. Key Vault con RBAC.
5. Una identidad administrada para leer Key Vault y descargar imagenes de ACR.

Para produccion, conectar PostgreSQL y Container Apps por red privada. No guardar passwords ni connection strings en el repositorio.

### 2. Comunicaciones

En Azure Communication Services:

1. Crear Email Communication Service.
2. Verificar el dominio corporativo o comenzar con el dominio administrado por Azure.
3. Conectar el dominio al recurso de Communication Services.
4. Registrar el WhatsApp Business Account y el numero emisor.
   - Numero de negocio para Chile (20 de julio de 2026): `+56 9 4899 9539`.
5. Crear y conseguir aprobacion para una plantilla `govradar_alert` en español.

WhatsApp no permite iniciar una conversacion comercial con texto libre. Fuera de la ventana de 24 horas se debe enviar una plantilla aprobada. El worker usa esa plantilla para alertas proactivas.

### 3. Secretos de Key Vault

Crear estos secretos:

- `database-url`: `postgresql+psycopg://USUARIO:PASSWORD@HOST:5432/DB?sslmode=require`
- `app-secret-key`: valor aleatorio de al menos 32 bytes.
- `azure-communication-connection`: connection string de Communication Services.
- `admin-password`: password inicial fuerte; rotarlo despues del primer acceso.

La identidad de cada Container App y del Job necesita el rol **Key Vault Secrets User**. Para descargar imagenes necesita **AcrPull** sobre el registro.

### 4. Construir imagenes

```powershell
$tag = (git rev-parse --short HEAD)
az acr build --registry <ACR> --image "govradar-api:$tag" .
az acr build --registry <ACR> --image "govradar-frontend:$tag" `
  --file frontend/Dockerfile.azure `
  --build-arg "VITE_API_URL=https://<API_FQDN>" frontend
```

### 5. Migrar base de datos

Antes de activar una nueva revision:

```powershell
az containerapp job start --name govradar-migrate --resource-group <RESOURCE_GROUP>
```

El job de migracion usa la imagen de API y ejecuta:

```text
alembic upgrade head
```

### 6. API

Variables no secretas:

```text
ENVIRONMENT=azure
ENABLE_SCHEDULER=false
AUTO_SEND_ALERTS=false
AUTO_CREATE_TABLES=false
CORS_ORIGINS=https://<FRONTEND_FQDN>
```

Secretos referenciados desde Key Vault:

```text
DATABASE_URL=database-url
SECRET_KEY=app-secret-key
```

Configurar ingress externo en puerto 8000 y probes contra `/health`.

### 7. Worker de ingesta

Usar [ingestion-peru-job.yaml](ingestion-peru-job.yaml), [ingestion-chile-job.yaml](ingestion-chile-job.yaml) e [ingestion-argentina-job.yaml](ingestion-argentina-job.yaml) con la misma imagen del API y el secreto `database-url`. Los tres sincronizan las palabras personalizadas del Radar con perfiles automáticos. Perú (OECE/OCDS) se ejecuta en los minutos 00/15/30/45, Chile (Mercado Público) en 05/20/35/50 y Argentina (COMPR.AR) en 10/25/40/55, distribuyendo la carga y aislando fallas por país.

### 8. Worker de alertas

Usar [alert-job.yaml](alert-job.yaml), reemplazar los marcadores y establecer los mismos secretos de base de datos y comunicaciones. El cron `*/5 * * * *` se evalua en UTC, aunque en este caso el intervalo no depende de la zona horaria.

### 9. Workers del modulo Seguimiento de Oportunidades

El scheduler embebido esta desactivado en Azure (`ENABLE_SCHEDULER=false`), asi que estas dos automatizaciones del modulo de Seguimiento tambien corren como Container Apps Jobs, con el mismo patron "claim" que ya usa la ingesta (`claim_external_scheduler_run`): el cron dispara con frecuencia, pero el trabajo real solo se ejecuta cuando ya se cumplio el intervalo guardado en `app_settings` (el mismo intervalo editable desde Sistema > Verificacion automatica de fechas).

- [tracking-alerts-job.yaml](tracking-alerts-job.yaml): alertas por correo "Atender"/"Urgente" cuando una etapa sin completar se acerca a su fecha limite. Intervalo por defecto 30 minutos (`TRACKING_ALERT_INTERVAL_MINUTES`), sin panel de administracion propio todavia.
- [tracking-date-refresh-peru-job.yaml](tracking-date-refresh-peru-job.yaml) y [tracking-date-refresh-chile-job.yaml](tracking-date-refresh-chile-job.yaml): revalidan contra SEACE/Mercado Publico las fechas de oportunidades en seguimiento activo cuya propuesta aun no vence. Intervalo por defecto 3 horas, editable por pais desde Sistema > Verificacion automatica de fechas.

Reemplazar los marcadores igual que en los jobs anteriores y establecer los mismos secretos de base de datos y comunicaciones.

### 10. Modulo Historico Peru (datos abiertos CONOSCE)

Fuente: archivos estaticos del Portal de Datos Abiertos del OECE en `https://conosce.osce.gob.pe/buscador/assets/67ae6c4a/reportes/...` (patrones en `backend/app/services/historico/conosce.py`). OECE los regenera todos, incluidos los meses pasados, dentro de los primeros cinco dias de cada mes. El 12/10/2026 se verifico que la descarga funciona desde Azure Container Apps y desde una PC, sin proxy.

Cadena de actualizacion:

1. **Job de Azure** [historico-peru-job.yaml](historico-peru-job.yaml) (`govradar-historico-peru`). El cron es horario (`50 * * * *`) y casi siempre termina sin hacer nada (patron claim).
   - **Importacion completa:** se ejecuta desde el dia de actualizacion (9 por defecto, editable en Sistema › Historico Peru) hasta que una importacion del mes termina bien, o cuando un admin pulsa "Actualizar ahora".
   - **Mantenimiento:** una vez al dia recalcula los dias restantes y las alertas; los lunes despues de las 8:00 (Lima) envia el resumen semanal.
   - Cada archivo se descarga, se procesa y se borra antes de pasar al siguiente, para que el disco nunca pase de unos 70 MB.
   - Recursos: 1 CPU / 2 GiB, timeout de 2 h.
2. **Script de la PC** `backend/scripts/historico_pc_sync.py`. Solo actua si la importacion del mes no termino o si el job fallo (`GET /historico/status`). Sube los archivos a la API uno por uno y la API procesa cada uno al recibirlo, para no llenar el disco efimero (4 GiB). Programarlo en el Programador de tareas de Windows, a diario desde el dia 10 a las 08:00:

   ```powershell
   $action = New-ScheduledTaskAction -Execute "py" -Argument "backend\scripts\historico_pc_sync.py" -WorkingDirectory "<ruta del repo>"
   $trigger = New-ScheduledTaskTrigger -Daily -At 8:00am
   Register-ScheduledTask -TaskName "GovRadar Historico Peru" -Action $action -Trigger $trigger
   [Environment]::SetEnvironmentVariable("GOVRADAR_API_URL", "https://api.crmprocesosgobierno.rodarlab.com", "User")
   [Environment]::SetEnvironmentVariable("GOVRADAR_EMAIL", "<admin>", "User")
   [Environment]::SetEnvironmentVariable("GOVRADAR_PASSWORD", "<clave>", "User")
   ```

3. **Carga manual.** Si el script tambien falla, o no aparece dentro de 24 h despues de una falla del job, los admins reciben el correo "Historico Peru · Carga manual requerida" (como maximo uno cada 3 dias). La carga se hace en Sistema › Historico Peru › Cargar archivos, con los nombres originales de CONOSCE (`SETIEMBRE` y `SEPTIEMBRE` se aceptan por igual).

Alta del job (una sola vez, despues de desplegar la imagen y aplicar la migracion `20261012_0035`):

```powershell
(Get-Content azure/historico-peru-job.yaml) -replace 'IMAGE_TAG', '<tag>' | Set-Content $env:TEMP\historico-job.yaml
az containerapp job create -g govradar-rg -n govradar-historico-peru --yaml $env:TEMP\historico-job.yaml
# primera carga sin esperar al dia 9:
# Ojo: `job start --env-vars` REEMPLAZA todas las variables del contenedor (se pierde DATABASE_URL).
# Para forzar una importacion usa "Actualizar ahora" en Configuracion, o un start simple si ya toca (dia >= dia de actualizacion).
az containerapp job start -g govradar-rg -n govradar-historico-peru
```

Una importacion completa (unos 60 archivos, cerca de 3 GB) toma alrededor de 40 minutos; la mayor parte es la lectura de las ordenes mensuales con `python-calamine`.


### 11. Modulo Historico Chile (datos abiertos ChileCompra)

Mismo modulo que Historico Peru (mismas tablas `hist_*` con columna `country`, mismas pantallas y alertas), con otra fuente: los zip mensuales de `datos-abiertos.chilecompra.cl/descargas`, en `https://transparenciachc.blob.core.windows.net/lic-da/AAAA-M.zip` (licitaciones) y `.../oc-da/AAAA-M.zip` (ordenes de compra). Ver `backend/app/services/historico/chilecompra.py` y `chile_import.py`. ChileCompra los actualiza a diario; una actualizacion relee los ultimos 18 meses de licitaciones y 3 de ordenes, y los meses anteriores solo si faltan.

- **Job de Azure** [historico-chile-job.yaml](historico-chile-job.yaml) (`govradar-historico-chile`), cron horario `20 * * * *`, `HISTORICO_COUNTRY=chile`, timeout 3 h. La primera carga (2023 a hoy, unos 92 archivos) toma unos 40 minutos; despues, el dia de actualizacion por defecto es el 3 de cada mes (editable en Configuracion › Historico Chile).
- **Sin script de PC:** la fuente es Azure Blob y se descarga directo desde el job. Si el job falla, los admins reciben "Historico Chile · Carga manual requerida" y suben los zip en Configuracion › Historico Chile › Cargar archivos, nombrados `lic-AAAA-M.zip` / `oc-AAAA-M.zip` (si se suben con el nombre original `AAAA-M.zip`, se reconocen por la cabecera del CSV).
- **Permiso:** modulo `historico_chile` en Usuarios, independiente de `historico_peru`.

```powershell
(Get-Content azure/historico-chile-job.yaml) -replace 'IMAGE_TAG', '<tag>' | Set-Content $env:TEMP\historico-chile-job.yaml
az containerapp job create -g govradar-rg -n govradar-historico-chile --yaml $env:TEMP\historico-chile-job.yaml
# primera carga inmediata (sin --env-vars: reemplazaria DATABASE_URL; la primera carga ya "toca")
az containerapp job start -g govradar-rg -n govradar-historico-chile
```

### 11. Prueba de aceptacion

1. Crear una regla interna y verificar estado `sent`.
2. Crear una regla email a una cuenta controlada y confirmar el correo.
3. Crear reglas WhatsApp para números de Perú `+51`, Chile `+56` y Argentina `+54`.
4. Verificar `provider_message_id` y `sent_at` en la API.
5. Mantener `WHATSAPP_ENABLED=false` hasta disponer del numero/canal aprobado; las entregas quedan en `waiting_channel` sin consumir reintentos.
6. Simular una credencial incorrecta: debe quedar `retrying`, conservar el mensaje y programar `next_attempt_at`.
7. Corregir la credencial y comprobar el reintento automatico.
8. Crear una alerta que falle cinco veces: debe terminar en `failed`.

## Operacion

- Alerta de Azure Monitor si el job falla dos ejecuciones consecutivas.
- Alerta si existen registros `failed` en la tabla `alerts`.
- Revisar cuotas y reputacion del dominio de correo.
- Rotar secretos desde Key Vault; Container Apps puede consumir referencias sin exponer los valores.
- Mantener el Job con `parallelism: 1` hasta introducir una cola transaccional o Azure Service Bus.

## Despliegue activo (15 de julio de 2026)

GovRadar esta desplegado en el grupo `govradar-rg` y reutiliza, por limite de cuota de la suscripcion, el Container Apps Environment existente de PGI. Las aplicaciones y datos permanecen separados: `govradar-api`, `govradar-frontend`, `govradar-db-rodar`, `govradarkv923fd1` y los jobs `govradar-*`. No se modifican las revisiones de `pgi-backend` ni `pgi-frontend`.

Endpoints temporales de Azure:

- Frontend: `govradar-frontend.lemonwave-7154c3ee.centralus.azurecontainerapps.io`
- API: `govradar-api.lemonwave-7154c3ee.centralus.azurecontainerapps.io`

Registros activos en la zona `rodarlab.com` de Cloudflare, configurados en modo **Solo DNS**:

| Tipo | Nombre | Destino / valor |
| --- | --- | --- |
| CNAME | `crmprocesosgobierno` | `govradar-frontend.lemonwave-7154c3ee.centralus.azurecontainerapps.io` |
| TXT | `asuid.crmprocesosgobierno` | `C85B11412D36D5CD2B55724CE196C968E2EF1256E3E3914E4AA3346023BB8F9B` |
| CNAME | `www.crmprocesosgobierno` | `govradar-frontend.lemonwave-7154c3ee.centralus.azurecontainerapps.io` |
| TXT | `asuid.www.crmprocesosgobierno` | `C85B11412D36D5CD2B55724CE196C968E2EF1256E3E3914E4AA3346023BB8F9B` |
| CNAME | `api.crmprocesosgobierno` | `govradar-api.lemonwave-7154c3ee.centralus.azurecontainerapps.io` |
| TXT | `asuid.api.crmprocesosgobierno` | `C85B11412D36D5CD2B55724CE196C968E2EF1256E3E3914E4AA3346023BB8F9B` |

Los tres hostnames estan vinculados a sus Container Apps con certificados administrados de Azure y HTTPS validado extremo a extremo. Mantener los CNAME en **Solo DNS** para que Azure pueda renovar los certificados; cualquier proxy de Cloudflare se evalua posteriormente y con una prueba completa de TLS y cabeceras.

ACR Tasks esta bloqueado en esta suscripcion. Las imagenes se construyen localmente con Docker y se publican mediante `docker push` al registro `pgihughesnetacr.azurecr.io`.
