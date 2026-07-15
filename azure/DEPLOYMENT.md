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

Usar [ingestion-peru-job.yaml](ingestion-peru-job.yaml) y [ingestion-chile-job.yaml](ingestion-chile-job.yaml) con la misma imagen del API y el secreto `database-url`. Ambos sincronizan las palabras base y personalizadas del Radar con perfiles automaticos. Peru (OECE/OCDS) se ejecuta en los minutos 00/15/30/45 y Chile (Mercado Publico) en 05/20/35/50, distribuyendo la carga y aislando fallas por pais.

### 8. Worker de alertas

Usar [alert-job.yaml](alert-job.yaml), reemplazar los marcadores y establecer los mismos secretos de base de datos y comunicaciones. El cron `*/5 * * * *` se evalua en UTC, aunque en este caso el intervalo no depende de la zona horaria.

### 9. Prueba de aceptacion

1. Crear una regla interna y verificar estado `sent`.
2. Crear una regla email a una cuenta controlada y confirmar el correo.
3. Crear reglas WhatsApp para un numero Peru `+51` y Chile `+56`.
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
