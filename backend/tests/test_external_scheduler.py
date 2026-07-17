from datetime import UTC, datetime
from types import SimpleNamespace

from backend.app.services import scheduler_service


def test_external_scheduler_uses_country_cron_offsets(monkeypatch):
    monkeypatch.setattr(
        scheduler_service,
        "settings",
        SimpleNamespace(external_scheduler_enabled=True, external_scheduler_interval_minutes=15),
    )
    now = datetime(2026, 7, 15, 13, 1, tzinfo=UTC)

    assert scheduler_service.external_scheduler_next_run("peru", now) == datetime(2026, 7, 15, 13, 15, tzinfo=UTC)
    assert scheduler_service.external_scheduler_next_run("chile", now) == datetime(2026, 7, 15, 13, 5, tzinfo=UTC)


def test_external_scheduler_can_be_disabled(monkeypatch):
    monkeypatch.setattr(
        scheduler_service,
        "settings",
        SimpleNamespace(external_scheduler_enabled=False, external_scheduler_interval_minutes=15),
    )

    assert scheduler_service.external_scheduler_next_run("peru") is None
