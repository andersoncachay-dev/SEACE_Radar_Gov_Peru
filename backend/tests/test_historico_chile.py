from __future__ import annotations

import csv
import io
import shutil
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.hist_scope import current_country, use_country
from backend.app.models import AppSetting, HistAlert, HistContract, HistContracting, HistExpiring, HistKeyword, HistRecurring
from backend.app.services.historico import chile_import, chilecompra, import_service, orchestration, query_service
from backend.tests.test_historico_import import TODAY, HistoricoFixture

LIC_HEADER = chile_import.LIC_COLUMNS + ["Descripcion"]
OC_HEADER = chile_import.OC_COLUMNS


def _lic(code, line, supplier, amount, award, months="12", unit="4", selected="Seleccionada", name="Servicio de enlace de datos e internet", region="Región de Coquimbo", state="Adjudicada", tipo="LE", currency="CLP", item_name="Proveedores de servicio de Internet (ISP)", item_desc="enlace dedicado 100 Mbps"):
    row = dict.fromkeys(LIC_HEADER, "")
    row.update({
        "CodigoExterno": code, "Link": f"http://www.mercadopublico.cl/fichaLicitacion.html?idLicitacion={code}", "Nombre": name,
        "Tipo de Adquisicion": "Licitación Pública Entre 100 y 1000 UTM (LE)", "Estado": state, "CodigoOrganismo": "7248",
        "NombreOrganismo": "ILUSTRE MUNICIPALIDAD DE LA SERENA", "sector": "Municipalidades", "RutUnidad": "69.040.100-4",
        "RegionUnidad": region, "Tipo": tipo, "CodigoMoneda": currency, "FechaAdjudicacion": award, "FechaPublicacion": "2026-09-02",
        "TiempoDuracionContrato": months, "UnidadTiempoDuracionContrato": unit, "Correlativo": line, "Rubro1": "Servicios",
        "Nombre linea Adquisicion": item_name, "Descripcion linea Adquisicion": item_desc,
        "RutProveedor": supplier, "NombreProveedor": f"Proveedor {supplier}", "MontoLineaAdjudica": amount, "Oferta seleccionada": selected,
    })
    return row


def _oc(code, issued, amount, tipo="Compra Ágil", procedencia="NA", licitacion="NA", name="Servicio de internet mes de septiembre", supplier="76.111.111-1", product="Servicio de internet"):
    row = dict.fromkeys(OC_HEADER, "")
    row.update({
        "Codigo": code, "Nombre": name, "Descripcion/Obervaciones": "", "DescripcionTipoOC": tipo, "ProcedenciaOC": procedencia,
        "Estado": "Aceptada", "FechaCreacion": issued, "FechaEnvio": issued, "MontoTotalOC_PesosChilenos": amount,
        "RutUnidadCompra": "61.602.000-0", "OrganismoPublico": "SERVICIO DE SALUD COQUIMBO", "CodigoOrganismoPublico": "1234",
        "sector": "Salud", "RegionUnidadCompra": "Región de Coquimbo", "RutSucursal": supplier, "NombreProveedor": "ISP Norte",
        "CodigoLicitacion": licitacion, "NombreroductoGenerico": product, "EspecificacionComprador": "",
    })
    return row


class HistoricoChileTests(HistoricoFixture):
    def setUp(self) -> None:
        super().setUp()
        self.chile = use_country(sessionmaker(bind=self.db.get_bind(), future=True)(), "chile")

    def tearDown(self) -> None:
        self.chile.close()
        super().tearDown()

    def _zip(self, name: str, header: list[str], rows: list[dict]) -> Path:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=header, delimiter=";", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)
        path = self.folder / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(name.replace(".zip", ".csv"), buffer.getvalue().encode("latin-1"))
        return path

    def _chile_files(self):
        lic = self._zip("lic-2026-9.zip", LIC_HEADER, [
            _lic("4295-67-LP26", "1", "96.722.400-6", "12000000", "2026-09-30", months="6"),
            _lic("4295-67-LP26", "1", "77.000.000-1", "11000000", "2026-09-30", selected="No Seleccionada"),
            _lic("4295-67-LP26", "2", "96.722.400-6", "243697,5", "2026-09-30", months="12"),
            _lic("5000-1-LE26", "1", "76.000.000-2", "100", "2025-11-20", months="36", currency="USD"),
            _lic("5000-2-LE26", "1", "76.000.000-3", "9000000", "2026-09-10", name="Servicio de aseo", tipo="LE", item_name="Servicios de limpieza", item_desc="aseo de oficinas"),
            _lic("5000-3-LE26", "1", "76.000.000-4", "9000000", "2026-09-10", state="Revocada"),
        ])
        oc = self._zip("oc-2026-9.zip", OC_HEADER, [
            _oc("1001-1-AG26", "2026-04-05", "600000"),
            _oc("1001-2-AG26", "2026-05-05", "600000"),
            _oc("1001-3-AG26", "2026-06-05", "600000"),
            _oc("1001-4-AG26", "2026-07-05", "300000"),
            _oc("1001-5-AG26", "2026-08-05", "300000"),
            _oc("1001-6-SE26", "2026-09-05", "500000", tipo="Proveniente de Ficha de Trato Directo", procedencia="Emergencia, urgencia o imprevisto"),
            _oc("1001-7-SE26", "2026-09-06", "900000", tipo="Sin emisión automática", licitacion="4295-67-LP26"),
            _oc("1001-9-SE26", "2026-09-08", "900000", tipo="Sin emisión automática", procedencia="Proveniente de licitación pública"),
            _oc("1001-8-AG26", "2026-09-07", "50000", name="Compra de resmas de papel", product="Papel"),
        ])
        return [(chilecompra.identify_file(lic.name, lic), lic), (chilecompra.identify_file(oc.name, oc), oc)]

    def _import_chile(self):
        run = import_service.create_run(self.chile, "manual_upload")
        return import_service.import_files(self.chile, run, self._chile_files(), today=TODAY)

    def test_identify_files(self) -> None:
        (lic_source, _), (oc_source, _) = self._chile_files()
        self.assertEqual((lic_source.dataset, lic_source.year, lic_source.month, lic_source.filename), ("licitaciones", 2026, 9, "lic-2026-9.zip"))
        self.assertEqual(oc_source.dataset, "ordenes")
        bare = self.folder / "2026-9.zip"
        shutil.copy(self.folder / "lic-2026-9.zip", bare)
        self.assertEqual(chilecompra.identify_file("2026-9.zip", bare).dataset, "licitaciones")  # by CSV header
        self.assertIsNone(chilecompra.identify_file("informe.xlsx"))

    def test_pipeline_and_isolation_from_peru(self) -> None:
        self._import(self._fixture_files())  # Perú, on the unpinned session
        run = self._import_chile()
        self.assertEqual(run.status, "completed", run.error)

        awards = self.chile.scalars(select(HistContracting).where(HistContracting.dataset == "adjudicacion")).all()
        self.assertEqual(sorted(award.source_key for award in awards), ["4295-67-LP26|1|96.722.400-6", "4295-67-LP26|2|96.722.400-6", "5000-1-LE26|1|76.000.000-2"])
        first = next(award for award in awards if award.item_number == "2")
        self.assertAlmostEqual(first.amount, 243697.5)
        self.assertEqual(first.department, "COQUIMBO")
        self.assertEqual(first.government_level, "Municipalidades")
        self.assertEqual(first.process_group, "Licitación pública 100–1.000 UTM (LE)")
        usd = next(award for award in awards if award.convocatoria_code == "5000-1-LE26")
        self.assertEqual(usd.amount, 100 * chile_import.CURRENCY_TO_CLP["USD"])

        contract = self.chile.scalar(select(HistContract).where(HistContract.contract_code == "4295-67-LP26"))
        self.assertEqual((contract.start_date, contract.end_date), (date(2026, 10, 15), date(2027, 4, 15)))
        expiring = self.chile.execute(select(HistExpiring, HistContracting).join(HistContracting, HistContracting.id == HistExpiring.contracting_id)).all()
        by_code = {award.convocatoria_code: item for item, award in expiring}
        self.assertTrue(by_code["4295-67-LP26"].is_real_date)
        self.assertEqual(by_code["4295-67-LP26"].date_source, "Plazo declarado en la licitación")
        self.assertEqual(by_code["5000-1-LE26"].end_date, date(2028, 12, 5))  # 2025-11-20 + 15 d + 36 months

        orders = self.chile.scalars(select(HistContracting).where(HistContracting.dataset == "orden")).all()
        self.assertEqual(len(orders), 6)  # licitación-derived order and the paper purchase are out
        self.assertEqual({order.process_group for order in orders}, {"Compra Ágil", "Trato directo"})
        recurring = self.chile.scalar(select(HistRecurring))
        self.assertEqual(recurring.orders_12m, 6)
        self.assertEqual(recurring.pattern, "Mensual / recurrente")

        alerts = self.chile.scalars(select(HistAlert)).all()
        self.assertTrue(alerts)
        self.assertTrue(all(alert.country == "chile" for alert in alerts))
        recurring_alert = next((a for a in alerts if a.kind == "recurrente"), None)
        if recurring_alert:
            self.assertEqual(recurring_alert.process_group, "Compra Ágil y trato directo")

        # Perú is untouched and does not see Chile rows (and vice versa).
        peru_awards = self.db.scalar(select(func.count()).select_from(HistContracting).where(HistContracting.dataset == "adjudicacion"))
        self.assertEqual(peru_awards, 3)
        self.assertEqual(query_service.list_contractings(self.db, query_service.Filters())["total"], 3)  # 9004 is "revisar"
        self.assertEqual(query_service.list_contractings(self.chile, query_service.Filters())["total"], 9)
        self.assertNotIn("COQUIMBO", query_service.filter_options(self.db)["departments"])
        self.assertEqual(query_service.filter_options(self.chile)["departments"], ["COQUIMBO"])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(HistKeyword)), self.chile.scalar(select(func.count()).select_from(HistKeyword)))

    def test_reimport_replaces_the_month_only_in_chile(self) -> None:
        self._import(self._fixture_files())
        self._import_chile()
        self._import_chile()
        self.assertEqual(self.chile.scalar(select(func.count()).select_from(HistContracting).where(HistContracting.dataset == "adjudicacion")), 3)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(HistContracting).where(HistContracting.dataset == "adjudicacion")), 3)

    def test_settings_are_per_country(self) -> None:
        orchestration.request_refresh(self.chile, None)
        self.assertTrue(orchestration.status(self.chile)["refresh_requested"])
        self.assertFalse(orchestration.status(self.db)["refresh_requested"])
        keys = set(self.db.scalars(select(AppSetting.key)).all())
        self.assertIn("historico.chile.refresh_requested", keys)
        self.assertEqual(orchestration.refresh_day(self.chile), 3)
        self.assertEqual(orchestration.refresh_day(self.db), 9)
        self.assertEqual(current_country(self.db), "peru")

    def test_catalogue_skips_old_months_already_loaded(self) -> None:
        today = date(2026, 10, 14)
        full = chilecompra.catalogue(today)
        self.assertEqual(len(full), 2 * 46)
        loaded = {("licitacion", f"2023-{m:02d}") for m in range(1, 13)} | {("orden", f"2023-{m:02d}") for m in range(1, 13)}
        partial = chilecompra.catalogue(today, loaded=loaded)
        self.assertEqual(len(partial), len(full) - 24)
        self.assertEqual(partial[0].dataset, "licitaciones")
        self.assertEqual(partial[-1].dataset, "ordenes")

    def test_unspsc_gate(self) -> None:
        classifier = import_service.load_classifier(self.chile)
        isp = chile_import.classify_line(classifier, "Orden de Compra generada por invitación a compra ágil", "81112101", is_order=True)
        self.assertEqual((isp.relevance, isp.category), ("ok", "Internet (sin especificar)"))
        mouse = chile_import.classify_line(classifier, "Mouse inalámbrico óptico", "43211708", is_order=True)
        self.assertEqual(mouse.relevance, "drop")
        laptops = chile_import.classify_line(classifier, "Notebook con wifi para liceo", "43211503", is_order=False)
        self.assertEqual(laptops.relevance, "revisar")
        router = chile_import.classify_line(classifier, "Router para enlace de internet", "43222609", is_order=True)
        self.assertEqual(router.relevance, "ok")
        starlink = chile_import.classify_line(classifier, "Antena Starlink con plan de internet satelital", "43222610", is_order=True)
        self.assertEqual(starlink.category, "Satelital - Starlink")
        unknown = chile_import.classify_line(classifier, "Servicio de internet dedicado", "0", is_order=True)
        self.assertEqual(unknown.relevance, "ok")

    def test_excel_labels(self) -> None:
        labels = dict(query_service.export_columns(self.chile, "vencimientos"))
        self.assertEqual(labels["amount"], "Monto adjudicado $ CLP")
        self.assertEqual(labels["department"], "Región")
        self.assertEqual(dict(query_service.export_columns(self.db, "vencimientos"))["department"], "Departamento")


if __name__ == "__main__":
    unittest.main()
