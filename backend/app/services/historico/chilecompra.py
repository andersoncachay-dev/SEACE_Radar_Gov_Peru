"""ChileCompra (Mercado Público) open data: file catalogue, download and
streaming CSV reader for Histórico Chile.

datos-abiertos.chilecompra.cl/descargas links to monthly zips on Azure Blob:

* licitaciones ``lic-da/{YYYY}-{M}.zip`` (~13 MB, one CSV of ~200 MB): one
  row per offer per line item of every licitación *published* that month,
  with its award (Oferta seleccionada), declared contract term and region;
* órdenes de compra ``oc-da/{YYYY}-{M}.zip`` (~100 MB, one CSV of ~700 MB):
  one row per item of every purchase order *issued* that month (Compra Ágil,
  trato directo, convenio marco, licitación).

Both are ``;``-separated, latin-1, with decimal commas. Verified 2026-10-14:
both are refreshed daily and past months keep changing as licitaciones get
awarded, so recent months are re-read on every refresh (see catalogue()).
"""
from __future__ import annotations

import csv
import io
import re
import time
import unicodedata
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

import requests

from .conosce import SourceFile

BASE_URL = "https://transparenciachc.blob.core.windows.net"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
FIRST_YEAR = 2023
DATASETS = ("licitaciones", "ordenes")
# Licitaciones published this many months ago can still be awarded or
# corrected; older ones are only re-read on a full refresh.
LIC_REFRESH_MONTHS = 18
# Orders only feed the 12-month recurring view and the history; older months
# are loaded once.
OC_REFRESH_MONTHS = 3
_FOLDER = {"licitaciones": "lic-da", "ordenes": "oc-da"}
_PREFIX = {"licitaciones": "lic", "ordenes": "oc"}
csv.field_size_limit(16 * 1024 * 1024)


class ChileSourceFile(SourceFile):
    """Both blobs are called ``YYYY-M.zip``: the lic-/oc- prefix keeps them
    apart on disk, in upload folders and in the run's file list."""

    @property
    def filename(self) -> str:
        return f"{_PREFIX[self.dataset]}-{self.year}-{self.month}.zip"


def monthly_file(dataset: str, year: int, month: int) -> SourceFile:
    return ChileSourceFile(dataset, year, month, f"{BASE_URL}/{_FOLDER[dataset]}/{year}-{month}.zip")


def local_name(source: SourceFile) -> str:
    return source.filename


def _months(first_year: int, today: date) -> list[tuple[int, int]]:
    return [(year, month) for year in range(first_year, today.year + 1) for month in range(1, (today.month if year == today.year else 12) + 1)]


def catalogue(today: date, first_year: int = FIRST_YEAR, loaded: set[tuple[str, str]] | None = None) -> list[SourceFile]:
    """Files a refresh needs, licitaciones first (lighter, they carry the
    contracts) and the heavy order files last. ``loaded`` holds the
    (dataset, "YYYY-MM") periods already stored: older months are skipped
    unless missing, so a regular refresh reads ~20 files, not ~90."""
    loaded = loaded or set()
    months = _months(first_year, today)
    files: list[SourceFile] = []
    for dataset, keep in (("licitaciones", LIC_REFRESH_MONTHS), ("ordenes", OC_REFRESH_MONTHS)):
        recent = set(months[-keep:])
        for year, month in months:
            period = f"{year:04d}-{month:02d}"
            if (year, month) in recent or ("licitacion" if dataset == "licitaciones" else "orden", period) not in loaded:
                files.append(monthly_file(dataset, year, month))
    return files


def identify_file(filename: str, path: Path | None = None) -> SourceFile | None:
    """Recognise an uploaded ChileCompra file. The portal names both kinds
    ``YYYY-M.zip``; a lic-/oc- prefix decides, else the CSV header does."""
    name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode().lower()
    name = re.sub(r"\s*\(\d+\)", "", name)
    match = re.search(r"(20\d\d)-(\d{1,2})\.(zip|csv)$", name)
    if not match:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        return None
    if name.startswith(("lic", "licitacion")):
        return monthly_file("licitaciones", year, month)
    if name.startswith(("oc", "orden")):
        return monthly_file("ordenes", year, month)
    if path is not None and path.exists():
        header = next(_raw_rows(path), [])
        if "CodigoExterno" in header:
            return monthly_file("licitaciones", year, month)
        if "EsCompraAgil" in header or "CodigoLicitacion" in header:
            return monthly_file("ordenes", year, month)
    return None


def download(source: SourceFile, target_dir: Path, *, retries: int = 3, timeout: int = 600, proxies: dict | None = None) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / local_name(source)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with requests.get(source.url, stream=True, timeout=timeout, headers={"User-Agent": USER_AGENT}, proxies=proxies) as response:
                if response.status_code == 404:
                    raise FileNotFoundError(f"ChileCompra no publica {local_name(source)} (404)")
                response.raise_for_status()
                partial = target.with_suffix(".part")
                with partial.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 20):
                        handle.write(chunk)
                partial.replace(target)
                return target
        except FileNotFoundError:
            raise
        except Exception as exc:
            last_error = exc
            time.sleep(min(30, 5 * attempt))
    raise RuntimeError(f"No se pudo descargar {local_name(source)}: {last_error}")


def _open_text(path: Path):
    if zipfile.is_zipfile(path):
        archive = zipfile.ZipFile(path)
        member = next((name for name in archive.namelist() if name.lower().endswith(".csv")), None)
        if member is None:
            archive.close()
            raise ValueError(f"{path.name} no contiene un CSV")
        return archive, io.TextIOWrapper(archive.open(member), encoding="latin-1", newline="")
    return None, path.open(encoding="latin-1", newline="")


def _raw_rows(path: Path) -> Iterator[list[str]]:
    archive, handle = _open_text(path)
    try:
        yield from csv.reader(handle, delimiter=";", quotechar='"')
    finally:
        handle.close()
        if archive is not None:
            archive.close()


def iter_rows(path: Path) -> Iterator[dict[str, str]]:
    """Stream rows as {header: value} straight from the zip (the order CSV
    alone is ~700 MB, never extracted to disk)."""
    rows = _raw_rows(path)
    header = next(rows, None)
    if not header:
        return
    header = [name.strip() for name in header]
    width = len(header)
    for values in rows:
        if len(values) < width:
            values = values + [""] * (width - len(values))
        yield dict(zip(header, values))


def to_float(value: str | None) -> float:
    """ChileCompra writes decimals with a comma and no thousands separator."""
    text = (value or "").strip()
    if not text:
        return 0.0
    try:
        return float(text.replace(".", "").replace(",", ".")) if "," in text else float(text)
    except ValueError:
        return 0.0


def to_date(value: str | None) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    for pattern, size in (("%Y-%m-%d", 10), ("%d-%m-%Y", 10), ("%d/%m/%Y", 10)):
        try:
            return datetime.strptime(text[:size], pattern).date()
        except ValueError:
            continue
    return None


def to_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()
