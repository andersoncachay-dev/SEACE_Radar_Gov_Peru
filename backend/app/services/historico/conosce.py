"""CONOSCE (OECE open data) file catalogue, download and streaming readers.

URL patterns come from the portal's own renderer
(bi.seace.gob.pe .../portal/js/renderhtmlv2.js): every dataset is a static
file under /buscador/assets/67ae6c4a/reportes. Verified 2026-10-12 to be
reachable both from Azure Container Apps and from a workstation without a
proxy. OECE regenerates every file (past months included) each month, so a
refresh always re-reads the whole range.
"""
from __future__ import annotations

import csv
import io
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

import requests

BASE_URL = "https://conosce.osce.gob.pe/buscador/assets/67ae6c4a/reportes"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
FIRST_YEAR = 2023

# The portal labels the month "SETIEMBRE" but the file is named SEPTIEMBRE.
_ORDER_MONTH_FILE_NAMES = (
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO",
    "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
)
_ORDER_MONTH_ALIASES = {"SETIEMBRE": 9, "SEPTIEMBRE": 9}

DATASETS = ("ordenes", "adjudicaciones", "directa", "contratos", "pac", "entidades")


@dataclass(frozen=True)
class SourceFile:
    dataset: str
    year: int | None
    month: int | None
    url: str

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def order_file(year: int, month: int) -> SourceFile:
    name = _ORDER_MONTH_FILE_NAMES[month - 1]
    return SourceFile("ordenes", year, month, f"{BASE_URL}/ordenes/{year}/CONOSCE_ORDENESCOMPRA{name}{year}_0.xlsx")


def yearly_file(dataset: str, year: int) -> SourceFile:
    folder, prefix = {
        "adjudicaciones": ("adjudicaciones", "ADJUDICACIONES"),
        "directa": ("adjudicaciones", "ADJUDICACIONES_CD"),
        "contratos": ("contratos", "CONTRATOS"),
        "pac": ("pac", "PAC"),
    }[dataset]
    return SourceFile(dataset, year, None, f"{BASE_URL}/{folder}/{year}/CONOSCE_{prefix}{year}_0.xlsx")


def entities_file() -> SourceFile:
    return SourceFile("entidades", None, None, f"{BASE_URL}/entidadescontratantes/entidades_contratantes.csv")


def catalogue(today: date, first_year: int = FIRST_YEAR) -> list[SourceFile]:
    """Every file a full refresh needs, smallest datasets first so a failure
    on the heavy monthly orders still leaves contracts/PAC up to date."""
    files: list[SourceFile] = [entities_file()]
    for year in range(first_year, today.year + 1):
        files += [yearly_file("contratos", year), yearly_file("directa", year), yearly_file("adjudicaciones", year)]
    files.append(yearly_file("pac", today.year))
    for year in range(first_year, today.year + 1):
        last_month = today.month if year == today.year else 12
        files += [order_file(year, month) for month in range(1, last_month + 1)]
    return files


def identify_file(filename: str) -> SourceFile | None:
    """Recognise a manually uploaded CONOSCE file by its name, tolerating the
    SETIEMBRE/SEPTIEMBRE spelling and browser suffixes like " (1)"."""
    name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode().upper()
    name = re.sub(r"\s*\(\d+\)", "", name)
    if "ENTIDADES_CONTRATANTES" in name:
        return entities_file()
    match = re.search(r"ORDENESCOMPRA([A-Z]+?)(20\d\d)", name)
    if match:
        month_name = match.group(1)
        month = _ORDER_MONTH_ALIASES.get(month_name) or (
            _ORDER_MONTH_FILE_NAMES.index(month_name) + 1 if month_name in _ORDER_MONTH_FILE_NAMES else None
        )
        if month:
            return order_file(int(match.group(2)), month)
        return None
    for dataset, token in (("directa", "ADJUDICACIONES_CD"), ("adjudicaciones", "ADJUDICACIONES"), ("contratos", "CONTRATOS"), ("pac", "PAC")):
        match = re.search(rf"CONOSCE_{token}(20\d\d)", name)
        if match:
            if dataset == "adjudicaciones" and "_SIE" in name:
                return None  # subset of the full adjudicaciones file
            return yearly_file(dataset, int(match.group(1)))
    return None


def download(source: SourceFile, target_dir: Path, *, retries: int = 3, timeout: int = 300, proxies: dict | None = None) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.filename
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with requests.get(source.url, stream=True, timeout=timeout, headers={"User-Agent": USER_AGENT}, proxies=proxies) as response:
                if response.status_code == 404:
                    raise FileNotFoundError(f"CONOSCE no publica {source.filename} (404)")
                response.raise_for_status()
                partial = target.with_suffix(target.suffix + ".part")
                with partial.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 20):
                        handle.write(chunk)
                partial.replace(target)
                return target
        except FileNotFoundError:
            raise
        except Exception as exc:  # network hiccups: retry with backoff
            last_error = exc
            time.sleep(min(30, 5 * attempt))
    raise RuntimeError(f"No se pudo descargar {source.filename}: {last_error}")


# --- readers -------------------------------------------------------------------


def header_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


_SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_COLUMN = re.compile(r"[A-Z]+")


def _column_index(ref: str) -> int:
    letters = _COLUMN.match(ref).group(0)
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index - 1


def _first_sheet_member(archive) -> str:
    from lxml import etree

    workbook = etree.fromstring(archive.read("xl/workbook.xml"))
    first = workbook.find(f"{_SHEET_NS}sheets/{_SHEET_NS}sheet")
    rel_id = first.get(f"{_REL_NS}id") if first is not None else None
    if rel_id and "xl/_rels/workbook.xml.rels" in archive.namelist():
        rels = etree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        for rel in rels:
            if rel.get("Id") == rel_id:
                target = rel.get("Target").lstrip("/")
                return target if target.startswith("xl/") else f"xl/{target}"
    return "xl/worksheets/sheet1.xml"


def iter_xlsx_rows(path: Path) -> Iterator[dict[str, object]]:
    """Stream the first sheet as dicts keyed by normalised header.

    The ~70 MB monthly order files (46+ per refresh) dominate import time.
    python-calamine (Rust) reads them at ~33k rows/s vs ~3k for openpyxl
    read-only (measured 2026-10-12); the lxml parser is the pure-Python
    fallback and openpyxl the last resort for unusual layouts."""
    try:
        from python_calamine import CalamineWorkbook
    except ImportError:
        CalamineWorkbook = None
    if CalamineWorkbook is not None:
        yield from _iter_xlsx_rows_calamine(CalamineWorkbook, path)
        return
    try:
        yield from _iter_xlsx_rows_fast(path)
    except _UnsupportedWorkbook:
        yield from _iter_xlsx_rows_openpyxl(path)


def _iter_xlsx_rows_calamine(workbook_cls, path: Path) -> Iterator[dict[str, object]]:
    sheet = workbook_cls.from_path(str(path)).get_sheet_by_index(0)
    rows = iter(sheet.iter_rows()) if hasattr(sheet, "iter_rows") else iter(sheet.to_python())
    headers = [header_key(cell) for cell in next(rows, [])]
    for row in rows:
        if not any(cell not in (None, "") for cell in row):
            continue
        yield {headers[i]: row[i] for i in range(min(len(headers), len(row))) if headers[i] and row[i] != ""}


class _UnsupportedWorkbook(Exception):
    pass


def _iter_xlsx_rows_fast(path: Path) -> Iterator[dict[str, object]]:
    import zipfile

    from lxml import etree

    with zipfile.ZipFile(path) as archive:
        try:
            member = _first_sheet_member(archive)
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                with archive.open("xl/sharedStrings.xml") as handle:
                    for _, element in etree.iterparse(handle, tag=f"{_SHEET_NS}si"):
                        shared.append("".join(element.itertext()))
                        element.clear()
            handle = archive.open(member)
        except (KeyError, etree.XMLSyntaxError) as exc:
            raise _UnsupportedWorkbook(str(exc)) from exc
        with handle:
            headers: list[str] | None = None
            for _, row in etree.iterparse(handle, tag=f"{_SHEET_NS}row"):
                values: dict[int, object] = {}
                position = -1
                for cell in row:
                    ref = cell.get("r")
                    position = _column_index(ref) if ref else position + 1
                    kind = cell.get("t")
                    if kind == "inlineStr":
                        value: object = "".join(cell.itertext())
                    else:
                        raw = cell.findtext(f"{_SHEET_NS}v")
                        if raw is None:
                            continue
                        if kind == "s":
                            value = shared[int(raw)]
                        elif kind in ("str", "e", "b"):
                            value = raw
                        else:
                            try:
                                value = float(raw)
                            except ValueError:
                                value = raw
                    values[position] = value
                row.clear()
                while row.getprevious() is not None:
                    del row.getparent()[0]
                if headers is None:
                    width = max(values) + 1 if values else 0
                    headers = [header_key(values.get(i, "")) for i in range(width)]
                    continue
                if not values:
                    continue
                yield {headers[i]: value for i, value in values.items() if i < len(headers) and headers[i]}


def _iter_xlsx_rows_openpyxl(path: Path) -> Iterator[dict[str, object]]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        rows = sheet.iter_rows(values_only=True)
        headers = [header_key(cell) for cell in next(rows, ())]
        for row in rows:
            if row is None or all(cell in (None, "") for cell in row):
                continue
            yield {headers[i]: row[i] for i in range(min(len(headers), len(row))) if headers[i]}
    finally:
        workbook.close()


def iter_csv_rows(path: Path) -> Iterator[dict[str, object]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    delimiter = "|" if text[:2000].count("|") > text[:2000].count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    headers = [header_key(cell) for cell in next(reader, [])]
    for row in reader:
        if row:
            yield {headers[i]: row[i] for i in range(min(len(headers), len(row))) if headers[i]}


def iter_rows(path: Path) -> Iterator[dict[str, object]]:
    return iter_csv_rows(path) if path.suffix.lower() == ".csv" else iter_xlsx_rows(path)


# --- value coercion ------------------------------------------------------------

_EXCEL_EPOCH = date(1899, 12, 30)


def to_date(value: object) -> date | None:
    """CONOSCE mixes dd/mm/yyyy text, ISO timestamps and Excel serials."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        if 20000 < float(value) < 80000:
            return _EXCEL_EPOCH + timedelta(days=int(float(value)))
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{5}(\.\d+)?", text):
        return to_date(float(text))
    for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10] if pattern == "%Y-%m-%d" else text.split(" ")[0], pattern).date()
        except ValueError:
            continue
    return None


def to_float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return re.sub(r"\s+", " ", str(value)).strip()
