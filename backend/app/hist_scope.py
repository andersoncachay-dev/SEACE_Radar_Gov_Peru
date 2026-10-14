"""Country scoping for the Histórico tables (Histórico Perú, Histórico Chile).

Every hist_* model carries a ``country`` column through ``HistScoped``. A
session is pinned to one country with ``use_country(db, "chile")``; from then
on every ORM SELECT / UPDATE / DELETE that touches a HistScoped table in that
session is filtered to that country (``with_loader_criteria``), and new rows
added through the ORM are stamped with it. A session that was never pinned
works on Peru, so all pre-existing Histórico Perú code paths behave exactly as
before.

Core ``insert(Model)`` with a list of dicts bypasses ``before_flush``: callers
must put ``country`` in the rows (see import_service._flush).
"""
from __future__ import annotations

from sqlalchemy import String, event
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria

DEFAULT_COUNTRY = "peru"
HIST_COUNTRIES = ("peru", "chile")
_INFO_KEY = "hist_country"


class HistScoped:
    country: Mapped[str] = mapped_column(String(10), default=DEFAULT_COUNTRY, server_default=DEFAULT_COUNTRY, index=True, nullable=False)


def use_country(db: Session, country: str) -> Session:
    if country not in HIST_COUNTRIES:
        raise ValueError(f"País de Histórico no soportado: {country}")
    db.info[_INFO_KEY] = country
    return db


def current_country(db: Session) -> str:
    return db.info.get(_INFO_KEY, DEFAULT_COUNTRY)


@event.listens_for(Session, "do_orm_execute")
def _scope_statement(state) -> None:
    if not (state.is_select or state.is_update or state.is_delete):
        return
    if state.is_column_load or state.is_relationship_load:
        return
    country = current_country(state.session)
    state.statement = state.statement.options(
        with_loader_criteria(HistScoped, lambda cls: cls.country == country, include_aliases=True)
    )


@event.listens_for(Session, "before_flush")
def _stamp_new_rows(session: Session, _context, _instances) -> None:
    country = current_country(session)
    for obj in session.new:
        if isinstance(obj, HistScoped):
            obj.country = country
