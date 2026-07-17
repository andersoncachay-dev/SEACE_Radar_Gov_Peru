from __future__ import annotations

import unittest

from fastapi import Response

from backend.app.routers.runs import _disable_progress_cache


class RunProgressCacheTests(unittest.TestCase):
    def test_progress_responses_cannot_be_cached(self) -> None:
        response = Response()

        _disable_progress_cache(response)

        self.assertEqual(
            response.headers["cache-control"],
            "no-store, no-cache, must-revalidate, max-age=0",
        )
        self.assertEqual(response.headers["pragma"], "no-cache")
        self.assertEqual(response.headers["expires"], "0")


if __name__ == "__main__":
    unittest.main()
