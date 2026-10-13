"""Histórico Perú fallback: refresh CONOSCE data from a workstation.

Second link of the update chain (Azure job -> this script -> manual upload).
Meant for the Windows Task Scheduler (see azure/DEPLOYMENT.md), daily from
day 10 at 08:00. It exits quietly when this month's import already
completed; otherwise downloads every CONOSCE file, uploads them to the API
and waits for the import. If anything fails it tells the API, which emails
the admins asking for a manual upload.

Environment:
  GOVRADAR_API_URL   e.g. https://api.crmprocesosgobierno.rodarlab.com
  GOVRADAR_EMAIL     an admin account
  GOVRADAR_PASSWORD
  HISTORICO_FORCE    "true" to run even if this month already completed

Run from the repo root:  py backend/scripts/historico_pc_sync.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.services.historico import conosce  # noqa: E402  (stdlib + requests only)

POLL_SECONDS = 20
POLL_LIMIT_SECONDS = 3 * 3600


def log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


class Api:
    def __init__(self, base_url: str, email: str, password: str):
        self.base = base_url.rstrip("/")
        response = requests.post(f"{self.base}/auth/login", data={"username": email, "password": password}, timeout=60)
        response.raise_for_status()
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {response.json()['access_token']}"

    def get(self, path: str):
        response = self.session.get(f"{self.base}{path}", timeout=120)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, **kwargs):
        response = self.session.post(f"{self.base}{path}", timeout=kwargs.pop("timeout", 120), **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"{path}: {response.status_code} {response.text[:300]}")
        return response.json()


def main() -> int:
    base_url = os.environ.get("GOVRADAR_API_URL", "")
    email, password = os.environ.get("GOVRADAR_EMAIL", ""), os.environ.get("GOVRADAR_PASSWORD", "")
    if not (base_url and email and password):
        log("Faltan GOVRADAR_API_URL, GOVRADAR_EMAIL o GOVRADAR_PASSWORD")
        return 2
    api = Api(base_url, email, password)
    force = os.environ.get("HISTORICO_FORCE", "").lower() in {"1", "true", "yes"}
    status = api.get("/historico/status")
    if status["completed_this_month"] and not status["needs_fallback"] and not force:
        log(f"Nada que hacer: la importación de este mes ya terminó ({status['latest_completed_at']}).")
        return 0
    if status["latest_status"] in ("queued", "running") and not force:
        log("Hay una importación en curso; se reintentará en la próxima ejecución.")
        return 0
    try:
        run = api.post("/historico/admin/imports", params={"origin": "pc_script"})
        log(f"Carga #{run['id']} creada")
        with tempfile.TemporaryDirectory(prefix="historico-pc-") as folder:
            for index, source in enumerate(conosce.catalogue(date.today()), start=1):
                try:
                    path = conosce.download(source, Path(folder))
                except FileNotFoundError:
                    log(f"  {source.filename}: aún no publicado, se omite")
                    continue
                with path.open("rb") as handle:
                    api.post(f"/historico/admin/imports/{run['id']}/files", files={"file": (source.filename, handle)}, timeout=900)
                log(f"  {index}. {source.filename} subido ({path.stat().st_size / 1e6:.1f} MB)")
                path.unlink()
        api.post(f"/historico/admin/imports/{run['id']}/process")
        started = time.time()
        while time.time() - started < POLL_LIMIT_SECONDS:
            time.sleep(POLL_SECONDS)
            current = api.get(f"/historico/admin/imports/{run['id']}")
            log(f"  {current['progress']}% {current['message']}")
            if current["status"] == "completed":
                log("Importación completada")
                return 0
            if current["status"] == "failed":
                raise RuntimeError(current["error"] or "la importación falló en el servidor")
        raise RuntimeError("la importación no terminó en 3 horas")
    except Exception as exc:
        log(f"Error: {exc}")
        try:
            api.post("/historico/admin/fallback-failed", json={"reason": f"el script de la PC falló: {exc}"[:500]})
        except Exception as notify_error:
            log(f"Tampoco se pudo avisar a la API: {notify_error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
