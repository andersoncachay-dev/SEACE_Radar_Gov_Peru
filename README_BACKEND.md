# SEACE Radar Gov Peru - Backend Productivo Inicial

Este backend separa la capa productiva del MVP Streamlit. Incluye API, base de datos, migraciones, usuarios, perfiles de busqueda, ejecuciones, oportunidades y reglas de alerta.

## Estado

- `SEACE Publico` queda integrado como primera fuente ejecutable desde `/runs/start`.
- `Menores a 8 UIT` queda deshabilitado por defecto con `ENABLE_MENOR8_MODULE=false` porque el modulo actual no es estable.
- Streamlit sigue disponible como MVP/manual.

## Arranque local

1. Copiar `.env.example` a `.env` y cambiar `SECRET_KEY` y `ADMIN_PASSWORD`.
2. Instalar dependencias: `py -m pip install -r requirements.txt`.
3. Ejecutar migracion: `py -m alembic upgrade head`.
4. Crear admin: `py backend/scripts/seed_admin.py`.
5. Levantar API: `py -m uvicorn backend.app.main:app --reload`.

En esta terminal `py` no esta disponible, pero los scripts quedan preparados para el entorno Windows normal donde se venia ejecutando el proyecto.

Tambien se puede usar:

```powershell
.\run_backend.ps1
```

## Arranque con Docker

```powershell
docker compose up --build
```

La API queda en:

- `http://127.0.0.1:8000`
- Docs: `http://127.0.0.1:8000/docs`

El compose usa PostgreSQL en el puerto local `5433`.

## Streamlit conectado al backend

El MVP Streamlit ahora tiene una fuente nueva: `Backend API`.

Uso:

1. Levantar el backend.
2. Ejecutar Streamlit como antes.
3. Seleccionar `Backend API` en la barra lateral.
4. Iniciar sesion con el admin.
5. Consultar oportunidades persistidas, iniciar runs, crear reglas y procesar alertas.

La URL se controla con:

```powershell
$env:BACKEND_API_URL="http://127.0.0.1:8000"
```

## Endpoints principales

- `POST /auth/login`
- `GET /users`
- `POST /users`
- `GET /search-profiles`
- `POST /search-profiles`
- `POST /runs/start`
- `GET /runs`
- `GET /opportunities`
- `POST /alerts/rules`
- `POST /alerts/evaluate`
- `POST /alerts/send-pending`

## Prueba rapida via API

Login con el admin inicial:

```powershell
curl -X POST http://127.0.0.1:8000/auth/login `
  -H "Content-Type: application/x-www-form-urlencoded" `
  -d "username=admin@seace-radar.local&password=Admin12345"
```

Crear un perfil de busqueda:

```powershell
curl -X POST http://127.0.0.1:8000/search-profiles `
  -H "Authorization: Bearer TOKEN" `
  -H "Content-Type: application/json" `
  -d "{\"name\":\"Satelital 2026\",\"keyword\":\"satelital\",\"source\":\"seace_public_browser\",\"year\":\"2026\",\"max_results\":25}"
```

Ejecutar un radar manual:

```powershell
curl -X POST http://127.0.0.1:8000/runs/start `
  -H "Authorization: Bearer TOKEN" `
  -H "Content-Type: application/json" `
  -d "{\"source\":\"seace_public_browser\",\"keyword\":\"satelital\",\"year\":\"2026\",\"max_results\":25,\"enrich_details\":false}"
```

Consultar oportunidades:

```powershell
curl http://127.0.0.1:8000/opportunities -H "Authorization: Bearer TOKEN"
```

## Alertas

Crear regla email:

```json
{
  "name": "Prioridad A comercial",
  "channel": "email",
  "destination": "equipo@empresa.com",
  "min_priority": "A",
  "hours_before_deadline": 48,
  "is_active": true
}
```

Flujo:

1. `POST /alerts/evaluate` genera alertas pendientes.
2. `POST /alerts/send-pending` intenta enviarlas.
3. Si SMTP o WhatsApp no estan configurados, la alerta queda en `error` con el motivo.

## Historial

Cada upsert de oportunidad crea un registro en `opportunity_snapshots` cuando cambia el hash del contenido. Esto permite auditar cambios de fechas, estado, PDF o descripcion sin depender del Excel.

## Siguiente paso recomendado

1. Estabilizar la ejecucion real en servidor: instalar Python en PATH o usar Docker.
2. Probar `/runs/start` con `source=seace_public_browser`.
3. Probar la fuente `Backend API` dentro de Streamlit contra el backend levantado.
4. Revisar aparte `Menores a 8 UIT`, actualmente apagado con `ENABLE_MENOR8_MODULE=false`.
