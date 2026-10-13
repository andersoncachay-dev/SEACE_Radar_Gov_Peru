from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import HistAlert, HistContracting, HistExpiring, HistImportRun, HistPacItem, HistRecurring, User
from backend.app.services.historico import conosce, import_service, orchestration, query_service
from backend.app.services.historico.alerts_service import evaluate_alerts

TODAY = date(2026, 10, 12)

# Headers copied from the real CONOSCE files (2026-10 downloads).
AWARD_HEADERS = [
    "CODIGOENTIDAD", "ENTIDAD_RUC", "ENTIDAD", "TIPOENTIDAD", "ENTIDAD_DEPARTAMENTO", "CODIGOCONVOCATORIA", "OBJETOCONTRACTUAL",
    "TIPOPROCESOSELECCION", "PROCESO", "DESCRIPCION_PROCESO", "N_ITEM", "DESCRIPCION_ITEM", "ESTADO_ITEM", "CANTIDAD_ADJUDICADO_ITEM",
    "MONTO_REFERENCIAL_ITEM_SOLES", "MONTO_ADJUDICADO_ITEM_SOLES", "DEPARTAMENTO_ITEM", "MONEDA", "UNIDAD_MEDIDA", "RUC PROVEEDOR",
    "PROVEEDOR", "TIPO_PROVEEDOR", "FECHA_CONVOCATORIA", "FECHA_BUENAPRO", "FECHA_CONSENTIMIENTO_BP",
]
CONTRACT_HEADERS = [
    "CODIGOENTIDAD", "CODIGOCONVOCATORIA", "DESCRIPCION_PROCESO", "N_COD_CONTRATO", "CODIGO_CONTRATO", "NUM_CONTRATO", "NUM_ITEM",
    "MONTO_CONTRATADO_TOTAL", "MONTO_CONTRATADO_ITEM", "MONTO_ADICIONAL", "MONTO_REDUCCION", "MONTO_PRORROGA", "MONTO_COMPLEMENTARIO",
    "MONEDA", "RUC_CONTRATISTA", "RUC_DESTINATARIO_PAGO", "TIENERESOLUCION", "URLCONTRATO", "ESPUBLICADO", "FECHA_PUBLICACION_CONTRATO",
    "FECHA_SUSCRIPCION_CONTRATO", "FECHA_VIGENCIA_INICIAL", "FECHA_VIGENCIA_FINAL", "FECHA_VIGENCIA_FIN_ACTUALIZADA",
]
ORDER_HEADERS = [
    "entidad", "ruc_entidad", "departamento_entidad", "tipoorden", "nro_de_orden", "orden", "descripcion_orden", "objetocontractual",
    "estadocontratacion", "tipodecontratacion", "monto_total_orden_original", "moneda", "ruc_contratista", "nombre_razon_contratista",
    "fecha_registro", "fecha_de_emision", "fecha_compromiso_presupuestal", "fecha_de_notificacion",
]
PAC_HEADERS = [
    "AÑO", "CODIGOENTIDAD", "RUC_ENTIDAD", "ENTIDAD", "VERSION", "N_REFERENCIA", "DESCRIPCION_PROCESO", "TIPOPROCESOSELECCION",
    "OBJETOCONTRACTUAL", "N_ITEM", "DESCRIPCION_ITEM", "CANTIDAD", "UNIDAD_MEDIDA", "DEPARTAMENTO", "PROVINCIA", "DISTRITO",
    "CODIGOUBIGEO_ITEM", "DEPARTAMENTO_ENT", "PROVINCIA_ENT", "DISTRITO_ENT", "CODIGOUBIGEO_ENT", "MES_PREVISTO", "FECHA_PUBLICACION",
]
EIGHT_UIT = "Contrataciones hasta 8 UIT (No incluye las derivadas de procedimientos de selección)"


def _award(conv, item, desc, amount, buena_pro, entity="UNIVERSIDAD NACIONAL X", ruc="20100000001", code="000100", kind="Concurso Público Abreviado"):
    return ["%s" % code, ruc, entity, "GOBIERNO NACIONAL", "LIMA", conv, "Servicio", kind, f"CP-ABR-{conv}", desc, item, desc,
            "Contratado", 1, amount, amount, "LIMA", "Soles", "Servicio", "20500000009", "TELCO SAC", "Persona Juridica", "01/01/2026", buena_pro, buena_pro]


def _order(number, desc, amount, issued, entity_ruc="20100000002", supplier="20600000001", kind=EIGHT_UIT):
    return ["MUNICIPALIDAD DISTRITAL Y", entity_ruc, "CUSCO", "Orden de Servicio", number, f"O/S-{number}-2026", desc, "SERVICIOS",
            "Comprometida", kind, amount, "Soles", supplier, "WIFI ANDINO EIRL", issued, issued, issued, issued]


class HistoricoFixture(unittest.TestCase):
    """Shared in-memory DB and CONOSCE-shaped xlsx builders (no tests)."""

    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, future=True)()
        self.folder = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        self.db.close()
        shutil.rmtree(self.folder, ignore_errors=True)

    def _xlsx(self, name: str, headers: list[str], rows: list[list]) -> tuple[conosce.SourceFile, Path]:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        path = self.folder / name
        workbook.save(path)
        return conosce.identify_file(name), path

    def _import(self, files) -> HistImportRun:
        run = import_service.create_run(self.db, "manual_upload")
        return import_service.import_files(self.db, run, files, today=TODAY)

    def _fixture_files(self):
        return [
            self._xlsx("CONOSCE_ADJUDICACIONES2025_0.xlsx", AWARD_HEADERS, [
                _award("9001", "1", "SERVICIO DE INTERNET DEDICADO POR 12 MESES", 120000.0, "20/10/2025"),
                _award("9002", "1", "SERVICIO DE INTERNET SATELITAL", 900000.0, "02/09/2025", entity="GOBIERNO REGIONAL Z", ruc="20100000003", code="000300"),
                _award("9003", "1", "SERVICIO DE LIMPIEZA", 50000.0, "02/09/2025"),
                _award("9004", "1", "ADQUISICION DE EQUIPOS DE TELECOMUNICACIONES", 70000.0, "02/09/2025"),
            ]),
            self._xlsx("CONOSCE_CONTRATOS2025_0.xlsx", CONTRACT_HEADERS, [
                ["000300", "9002", "INTERNET SATELITAL", "77", "77", "CONTRATO 5-2025", "1", 900000, 900000, 15000, 0, 0, 0, "Soles",
                 "20500000009", "20500000009", "SI", "https://prodapp2.seace.gob.pe/x", 1, 45900, 45900, 45910, 46300, 46320],
            ]),
            self._xlsx("CONOSCE_ORDENESCOMPRASEPTIEMBRE2026_0.xlsx", ORDER_HEADERS, [
                _order(1, "SERVICIO DE INTERNET MES DE SETIEMBRE", 12000.0, "05/09/2026"),
                _order(2, "UTILES DE ESCRITORIO", 900.0, "05/09/2026"),
                _order(3, "SERVICIO DE INTERNET", 3000.0, "06/09/2026", kind="Derivadas de procedimiento de selección"),
            ]),
            self._xlsx("CONOSCE_PAC2026_0.xlsx", PAC_HEADERS, [
                [2026, "000100", "20100000001", "UNIVERSIDAD NACIONAL X", 1, 7, "CONTRATACION DEL SERVICIO DE INTERNET", "Concurso Público Abreviado",
                 "Servicio", 1, "SERVICIO DE INTERNET", 1, "Servicio", "LIMA", "LIMA", "LIMA", "150101", "LIMA", "LIMA", "LIMA", "150101", 11, 46031],
                [2026, "000100", "20100000001", "UNIVERSIDAD NACIONAL X", 1, 8, "ADQUISICION DE MOBILIARIO", "Adjudicación Simplificada",
                 "Bien", 1, "MOBILIARIO", 1, "Unidad", "LIMA", "LIMA", "LIMA", "150101", "LIMA", "LIMA", "LIMA", "150101", 11, 46031],
            ]),
        ]


class HistoricoImportTests(HistoricoFixture):
    def test_full_pipeline(self) -> None:
        run = self._import(self._fixture_files())
        self.assertEqual(run.status, "completed", run.error)
        awards = {row.convocatoria_code: row for row in self.db.scalars(select(HistContracting).where(HistContracting.dataset == "adjudicacion")).all()}
        self.assertEqual(set(awards), {"9001", "9002", "9004"})  # cleaning service dropped
        self.assertEqual(awards["9004"].relevance, "revisar")
        self.assertEqual(awards["9002"].category, "Satelital (otros)")
        self.assertEqual(awards["9002"].government_level, "Gobierno Nacional")

        orders = self.db.scalars(select(HistContracting).where(HistContracting.dataset == "orden")).all()
        self.assertEqual([order.nomenclature for order in orders], ["O/S-1-2026"])  # off-rubro and derived orders dropped

        expiring = {e.contracting_id: e for e in self.db.scalars(select(HistExpiring)).all()}
        real = expiring[awards["9002"].id]
        self.assertTrue(real.is_real_date)
        self.assertEqual(real.end_date, conosce.to_date(46320))
        self.assertEqual(real.extras_amount, 15000)
        estimated = expiring[awards["9001"].id]
        self.assertEqual(estimated.date_source, "Estimada: 12 meses (descripción)")
        self.assertEqual(estimated.end_date, date(2026, 11, 4))  # 2025-10-20 + 15 d + 12 m
        self.assertEqual(estimated.bucket, "Vence ≤ 90 días")
        self.assertNotIn(awards["9004"].id, expiring)  # "revisar" rows are not tracked

        recurring = self.db.scalars(select(HistRecurring)).one()
        self.assertEqual(recurring.pattern, "Mensual / recurrente")

        pac = self.db.scalars(select(HistPacItem)).one()
        self.assertEqual(pac.situation, "Por convocar (mes previsto ≥ oct)")

        alerts = {(a.kind, a.priority) for a in self.db.scalars(select(HistAlert)).all()}
        self.assertIn(("vencimiento", "P1"), alerts)  # ends in 23 days
        self.assertIn(("pac", "P2"), alerts)  # planned for next month and the entity has no 2026 award yet
        self.assertTrue(any(kind == "recurrente" for kind, _ in alerts))

    def test_reimport_replaces_period_and_keeps_dismissals(self) -> None:
        self._import(self._fixture_files())
        alert = self.db.scalars(select(HistAlert).where(HistAlert.kind == "vencimiento", HistAlert.priority == "P1")).first()
        alert.status, alert.dismissed_due_date = "descartada", alert.due_date
        self.db.commit()
        self._import(self._fixture_files())
        self.assertEqual(self.db.scalar(select(func.count()).select_from(HistContracting).where(HistContracting.dataset == "adjudicacion")), 3)
        self.assertEqual(self.db.get(HistAlert, alert.id).status, "descartada")

    def test_item_awarded_next_year_survives_the_next_years_file(self) -> None:
        # In the 2025 awards file but with its buena pro in January 2026.
        late = self._xlsx("CONOSCE_ADJUDICACIONES2025_0.xlsx", AWARD_HEADERS, [_award("7001", "1", "SERVICIO DE INTERNET", 80000.0, "15/01/2026")])
        self._import([late])
        row = self.db.scalars(select(HistContracting)).one()
        self.assertEqual((row.year, row.source_period), (2026, "2025"))
        other = self._xlsx("CONOSCE_ADJUDICACIONES2026_0.xlsx", AWARD_HEADERS, [_award("7002", "1", "SERVICIO DE INTERNET", 50000.0, "10/03/2026")])
        self._import([other])
        self.assertEqual(sorted(self.db.scalars(select(HistContracting.convocatoria_code)).all()), ["7001", "7002"])

    def test_same_order_in_two_monthly_files_is_kept_once(self) -> None:
        august = self._xlsx("CONOSCE_ORDENESCOMPRAAGOSTO2026_0.xlsx", ORDER_HEADERS, [_order(9, "SERVICIO DE INTERNET", 1000.0, "30/08/2026")])
        september = self._xlsx("CONOSCE_ORDENESCOMPRASEPTIEMBRE2026_0.xlsx", ORDER_HEADERS, [_order(9, "SERVICIO DE INTERNET", 1200.0, "30/08/2026")])
        run = self._import([august, september])
        self.assertEqual(run.status, "completed", run.error)
        row = self.db.scalars(select(HistContracting)).one()
        self.assertEqual((row.amount, row.source_period, row.month), (1200.0, "2026-09", "2026-08"))

    def test_query_service_lists_filters_and_export(self) -> None:
        self._import(self._fixture_files())
        listing = query_service.list_expiring(self.db, query_service.Filters(buckets=["Vence ≤ 90 días"]))
        self.assertEqual(listing["total"], 2)  # estimated (23 d) and real contract end (13 d)
        self.assertEqual([item["days_to_end"] for item in listing["items"]], [13, 23])
        summary = query_service.summary(self.db, query_service.Filters(), TODAY)
        self.assertEqual(summary["totals"]["count"], 3)  # 2 ok awards + 1 order
        self.assertTrue(summary["runway"])
        content = query_service.export_xlsx(self.db, "vencimientos", query_service.Filters())
        self.assertTrue(content.startswith(b"PK"))
        detail = query_service.detail(self.db, "vencimientos", listing["items"][0]["id"])
        self.assertEqual(detail["record"]["entity_name"], "GOBIERNO REGIONAL Z")  # soonest end first
        self.assertEqual(detail["record"]["contract_number"], "CONTRATO 5-2025")

    def test_orchestration_due_and_fallback(self) -> None:
        from datetime import datetime

        self.assertFalse(orchestration.import_is_due(self.db, datetime(2026, 10, 8, 9)))
        self.assertTrue(orchestration.import_is_due(self.db, datetime(2026, 10, 9, 9)))
        failed = import_service.create_run(self.db, "azure_job")
        failed.status = "failed"
        self.db.commit()
        orchestration.record_job_result(self.db, failed)
        self.assertTrue(orchestration.needs_fallback(self.db))
        self.assertTrue(orchestration.manual_notice_due(self.db, pc_failed=True))
        self.assertFalse(orchestration.manual_notice_due(self.db))  # PC still has its grace period
        run = self._import(self._fixture_files())
        run.origin = "pc_script"
        self.db.commit()
        orchestration.record_job_result(self.db, run)
        self.assertFalse(orchestration.needs_fallback(self.db))


class AlertPreferenceTests(HistoricoFixture):
    def test_satellite_only_preference(self) -> None:
        from backend.app.models import HistAlertPreference
        from backend.app.services.historico.alerts_service import matches_preference, preference_conditions

        self._import(self._fixture_files())
        preference = HistAlertPreference(user_id=1, categories="Satelital (otros)", min_priority="P4")
        self.db.add(preference)
        self.db.commit()
        alerts = self.db.scalars(select(HistAlert).where(HistAlert.is_active.is_(True))).all()
        mine = [alert for alert in alerts if matches_preference(alert, preference)]
        self.assertTrue(mine)
        self.assertTrue(all(alert.category == "Satelital (otros)" for alert in mine))
        in_sql = self.db.scalars(select(HistAlert).where(HistAlert.is_active.is_(True), *preference_conditions(preference))).all()
        self.assertEqual({a.id for a in in_sql}, {a.id for a in mine})

    def test_min_priority_amount_and_keywords(self) -> None:
        from backend.app.models import HistAlertPreference
        from backend.app.services.historico.alerts_service import matches_preference

        self._import(self._fixture_files())
        alerts = self.db.scalars(select(HistAlert).where(HistAlert.is_active.is_(True))).all()
        only_critical = HistAlertPreference(user_id=1, min_priority="P1")
        self.assertTrue(all(alert.priority == "P1" for alert in alerts if matches_preference(alert, only_critical)))
        big = HistAlertPreference(user_id=1, min_amount=500000)
        self.assertTrue(all(alert.amount >= 500000 or alert.kind == "pac" for alert in alerts if matches_preference(alert, big)))
        keyword = HistAlertPreference(user_id=1, keywords="satelital")
        self.assertEqual({alert.ref_key for alert in alerts if matches_preference(alert, keyword)}, {"9002-1"})

    def test_pac_summary(self) -> None:
        self._import(self._fixture_files())
        summary = query_service.pac_summary(self.db, query_service.Filters(years=[2026]))
        self.assertEqual(summary["totals"], {"items": 1, "entities": 1, "already_awarded": 0, "to_call": 1})
        self.assertEqual(summary["by_month"], [{"key": 11, "count": 1}])


class ModuleAccessTests(unittest.TestCase):
    def test_require_module(self) -> None:
        from fastapi import HTTPException

        from backend.app.dependencies import require_module

        check = require_module("historico_peru")
        viewer = User(email="a@b.c", full_name="A", password_hash="x", role="viewer", module_access="radar")
        with self.assertRaises(HTTPException):
            check(viewer)
        viewer.module_access = "radar,historico_peru"
        self.assertIs(check(viewer), viewer)
        admin = User(email="d@b.c", full_name="D", password_hash="x", role="admin", module_access="radar")
        self.assertIs(check(admin), admin)


if __name__ == "__main__":
    unittest.main()
