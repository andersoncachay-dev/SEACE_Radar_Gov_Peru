from __future__ import annotations

import unittest
from datetime import date

from backend.app.services.historico import conosce
from backend.app.services.historico.alerts_service import expiring_priority, recurring_priority
from backend.app.services.historico.classify import DEFAULT_RULES, Classifier, government_level, process_group
from backend.app.services.historico.derive import (
    PATTERN_MONTHLY,
    PATTERN_PERIOD,
    PATTERN_REPEATED,
    PATTERN_SINGLE,
    ContractDates,
    OrderPoint,
    end_of_term,
    expiring_bucket,
    next_purchase,
    pac_situation,
    parse_term,
    recurring_bucket,
)


class TermParsingTests(unittest.TestCase):
    def test_months_days_years_and_period(self) -> None:
        self.assertEqual(parse_term("SERVICIO DE INTERNET POR 24 MESES").months, 24)
        self.assertEqual(parse_term("por un plazo de doce (12) meses").months, 12)
        self.assertEqual(parse_term("plazo de 365 días calendario").days, 365)
        self.assertEqual(parse_term("servicio por dos años").months, 24)
        self.assertEqual(parse_term("conectividad para el periodo 2026").period_year, 2026)

    def test_no_term_or_implausible_values(self) -> None:
        self.assertIsNone(parse_term("ADQUISICION DE ROUTER"))
        self.assertIsNone(parse_term("entrega en 5 dias"))  # delivery time, not a service term


class EndOfTermTests(unittest.TestCase):
    def test_real_contract_date_wins(self) -> None:
        term = end_of_term(date(2024, 9, 26), "internet 24 meses", ContractDates(date(2024, 10, 12), date(2026, 10, 12), date(2026, 10, 12)))
        self.assertTrue(term.is_real)
        self.assertEqual(term.end, date(2026, 10, 12))
        self.assertEqual(term.source, "Contrato SEACE (vigencia actualizada)")

    def test_default_is_buena_pro_plus_15_days_plus_12_months(self) -> None:
        # Matches CP-ABR-1-2025-SEDAPAL-1 in the v9 workbook: buena pro
        # 2025-09-29 -> start 2025-10-14 -> end 2026-10-14.
        term = end_of_term(date(2025, 9, 29), "SERVICIO DE CONTINGENCIA ACCESO INTERNET")
        self.assertEqual(term.start, date(2025, 10, 14))
        self.assertEqual(term.end, date(2026, 10, 14))
        self.assertEqual(term.source, "Estimada: 12 meses desde buena pro")

    def test_term_from_description(self) -> None:
        term = end_of_term(date(2026, 1, 1), "SERVICIO DE INTERNET POR 24 MESES")
        self.assertEqual(term.end, date(2028, 1, 16))
        self.assertEqual(term.source, "Estimada: 24 meses (descripción)")
        self.assertEqual(end_of_term(date(2026, 2, 1), "internet periodo 2026").end, date(2026, 12, 31))

    def test_buckets(self) -> None:
        self.assertEqual(expiring_bucket(-1), "Vencido")
        self.assertEqual(expiring_bucket(0), "Vence ≤ 90 días")
        self.assertEqual(expiring_bucket(91), "Vence 91–180 días")
        self.assertEqual(expiring_bucket(365), "Vence 181–365 días")
        self.assertEqual(expiring_bucket(366), "Vence > 1 año")
        self.assertEqual(recurring_bucket(-3), "Atrasada (sin compra reciente)")
        self.assertEqual(recurring_bucket(30), "≤ 30 días")


class RecurringTests(unittest.TestCase):
    def test_monthly_pattern_from_four_distinct_months(self) -> None:
        orders = [OrderPoint(date(2026, m, 5), "servicio de internet") for m in (5, 6, 7, 8)]
        forecast = next_purchase(orders)
        self.assertEqual(forecast.pattern, PATTERN_MONTHLY)
        self.assertEqual(forecast.next_date.month, 9)

    def test_monthly_pattern_from_text(self) -> None:
        forecast = next_purchase([OrderPoint(date(2026, 9, 1), "SERVICIO DE INTERNET MES DE SETIEMBRE")])
        self.assertEqual(forecast.pattern, PATTERN_MONTHLY)

    def test_period_repeated_and_single(self) -> None:
        self.assertEqual(next_purchase([OrderPoint(date(2026, 1, 10), "internet por 3 meses")]).pattern, PATTERN_PERIOD)
        repeated = next_purchase([OrderPoint(date(2026, 1, 10), "internet"), OrderPoint(date(2026, 4, 10), "internet")])
        self.assertEqual(repeated.pattern, PATTERN_REPEATED)
        self.assertEqual(repeated.next_date, date(2026, 7, 9))  # last order + the 90-day typical gap
        self.assertEqual(next_purchase([OrderPoint(date(2026, 1, 10), "internet")]).pattern, PATTERN_SINGLE)


class ClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = Classifier(DEFAULT_RULES)

    def test_categories_follow_keyword_priority(self) -> None:
        self.assertEqual(self.classifier.classify("INTERNET SATELITAL STARLINK", is_order=True).category, "Satelital - Starlink")
        self.assertEqual(self.classifier.classify("internet mediante fibra óptica", is_order=True).category, "Fibra óptica")
        self.assertEqual(self.classifier.classify("servicio de internet dedicado", is_order=True).category, "Internet (sin especificar)")

    def test_goods_with_equipment_terms(self) -> None:
        match = self.classifier.classify("ADQUISICION DE ROUTER PARA INTERNET", is_order=True, object_type="BIENES")
        self.assertEqual(match.category, "Equipamiento")

    def test_orders_drop_weak_matches_awards_go_to_review(self) -> None:
        self.assertEqual(self.classifier.classify("equipos de telecomunicaciones", is_order=True).relevance, "drop")
        self.assertEqual(self.classifier.classify("equipos de telecomunicaciones", is_order=False).relevance, "revisar")
        self.assertEqual(self.classifier.classify("internet y seguros patrimoniales", is_order=False).relevance, "revisar")
        self.assertEqual(self.classifier.classify("limpieza de oficinas", is_order=False).relevance, "drop")

    def test_whole_words_only(self) -> None:
        self.assertEqual(self.classifier.classify("INTERNETWORKING LAB", is_order=True).relevance, "drop")

    def test_process_group_and_government_level(self) -> None:
        self.assertEqual(process_group("Concurso Público de Servicios"), "Concurso Público")
        self.assertEqual(process_group("Concurso Público Abreviado"), "Concurso Público Abreviado")
        self.assertEqual(process_group("Adjudicación Simplificada - Ley N° 31728"), "Adjudicación Simplificada")
        self.assertEqual(process_group("Régimen Especial"), "Otros procedimientos")
        self.assertEqual(government_level("GOBIERNO REGIONAL"), "Gobierno Regional")
        self.assertEqual(government_level("", "UGEL SAN ROMAN"), "Gobierno Regional")
        self.assertEqual(government_level("", "MUNICIPALIDAD DISTRITAL DE MORROPE"), "Gobierno Local")


class ConosceTests(unittest.TestCase):
    def test_setiembre_and_septiembre_resolve_to_the_same_file(self) -> None:
        for name in ("CONOSCE_ORDENESCOMPRASEPTIEMBRE2026_0.xlsx", "CONOSCE_ORDENESCOMPRASETIEMBRE2026_0 (1).xlsx"):
            source = conosce.identify_file(name)
            self.assertEqual((source.dataset, source.year, source.month), ("ordenes", 2026, 9))
        self.assertTrue(conosce.order_file(2026, 9).url.endswith("CONOSCE_ORDENESCOMPRASEPTIEMBRE2026_0.xlsx"))

    def test_identify_yearly_files(self) -> None:
        self.assertEqual(conosce.identify_file("CONOSCE_ADJUDICACIONES_CD2026_0.xlsx").dataset, "directa")
        self.assertEqual(conosce.identify_file("CONOSCE_ADJUDICACIONES2025_0.xlsx").dataset, "adjudicaciones")
        self.assertIsNone(conosce.identify_file("CONOSCE_ADJUDICACIONES_SIE2025_0.xlsx"))
        self.assertEqual(conosce.identify_file("entidades_contratantes.csv").dataset, "entidades")

    def test_catalogue_covers_every_month_up_to_today(self) -> None:
        files = conosce.catalogue(date(2026, 10, 12))
        orders = [f for f in files if f.dataset == "ordenes"]
        self.assertEqual(len(orders), 12 * 3 + 10)
        self.assertEqual(files[0].dataset, "entidades")

    def test_date_coercion(self) -> None:
        self.assertEqual(conosce.to_date("09/06/2026"), date(2026, 6, 9))
        self.assertEqual(conosce.to_date(46307), date(2026, 10, 12))
        self.assertEqual(conosce.to_date("2026-09-02 00:00:00"), date(2026, 9, 2))
        self.assertEqual(conosce.to_text(20131379944.0), "20131379944")


class PriorityTests(unittest.TestCase):
    def test_expiring_priorities(self) -> None:
        self.assertEqual(expiring_priority(10, 50_000), "P1")
        self.assertEqual(expiring_priority(60, 50_000), "P2")
        self.assertEqual(expiring_priority(150, 600_000), "P2")
        self.assertEqual(expiring_priority(150, 50_000), "P3")
        self.assertEqual(expiring_priority(300, 50_000), "P4")
        self.assertIsNone(expiring_priority(-5, 50_000))
        self.assertIsNone(expiring_priority(400, 50_000))

    def test_recurring_priorities(self) -> None:
        self.assertEqual(recurring_priority(10, PATTERN_MONTHLY), "P2")
        self.assertEqual(recurring_priority(-10, PATTERN_MONTHLY), "P3")
        self.assertIsNone(recurring_priority(10, PATTERN_SINGLE))

    def test_pac_situation(self) -> None:
        self.assertEqual(pac_situation(10, 2026, date(2026, 10, 12)), "Por convocar (mes previsto ≥ oct)")
        self.assertEqual(pac_situation(9, 2026, date(2026, 10, 12)), "Mes previsto ya pasó")


if __name__ == "__main__":
    unittest.main()
