$ErrorActionPreference = "Stop"
Write-Host "Instalando dependencias..."
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
Write-Host "Iniciando SEACE Radar Gov Peru..."
py -m streamlit run app.py
