$ErrorActionPreference = "Stop"
Write-Host "Instalando dependencias backend..."
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
Write-Host "Ejecutando migraciones..."
py -m alembic upgrade head
Write-Host "Creando/actualizando usuario administrador..."
py backend/scripts/seed_admin.py
Write-Host "Iniciando API en http://127.0.0.1:8000"
py -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
