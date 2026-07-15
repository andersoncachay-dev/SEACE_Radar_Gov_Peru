from __future__ import annotations

import unittest

from backend.app.services.run_service import _mercado_publico_modes


class ChileRunModesTests(unittest.TestCase):
    def test_uses_only_licitaciones_while_large_purchases_are_disabled(self):
        self.assertEqual(
            _mercado_publico_modes(False),
            [("licitaciones", "mercado_publico_browser")],
        )

    def test_can_restore_large_purchases_with_feature_flag(self):
        self.assertEqual(
            _mercado_publico_modes(True),
            [
                ("licitaciones", "mercado_publico_browser"),
                ("grandes_compras", "mercado_publico_grandes_compras"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
