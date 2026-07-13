from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=8)
    role: str = "viewer"


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class UserOut(ORMModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class SearchProfileCreate(BaseModel):
    name: str
    keyword: str = "satelital"
    source: str = "seace_public_browser"
    year: str = "2026"
    version: str = "Seace 3"
    max_results: int = 50
    is_active: bool = True


class SearchProfileOut(ORMModel):
    id: int
    name: str
    keyword: str
    source: str
    year: str
    version: str
    max_results: int
    is_active: bool


class RunStart(BaseModel):
    search_profile_id: int | None = None
    source: str = "seace_public_browser"
    keyword: str = "satelital"
    year: str = "2026"
    month: str | None = None
    years: list[str] | None = None
    months: list[str] | None = None
    version: str = "Seace 3"
    max_results: int = 25
    max_details: int = 15
    enrich_details: bool = False


class ScrapeRunOut(ORMModel):
    id: int
    source: str
    status: str
    rows_found: int
    diagnostics: str
    error_message: str
    started_at: datetime | None
    finished_at: datetime | None


class OpportunityOut(ORMModel):
    id: int
    source: str
    external_id: str
    entity: str
    nomenclature: str
    object_type: str
    description: str
    region: str
    amount: float
    currency: str
    status: str
    priority: str
    score: int
    reasons: str
    detail_url: str
    requirement_pdf_url: str
    requirement_pdf_local: str
    publication_date: datetime | None
    consultation_deadline: datetime | None
    quote_deadline: datetime | None
    proposal_deadline: datetime | None


class OpportunitySnapshotOut(ORMModel):
    id: int
    opportunity_id: int
    run_id: int | None
    previous_hash: str
    content_hash: str
    change_type: str
    created_at: datetime


class OpportunityImportIn(BaseModel):
    source: str = "seace_public_browser"
    rows: list[dict[str, Any]]


class OpportunityImportResult(BaseModel):
    imported: int


class DocumentOut(ORMModel):
    id: int
    opportunity_id: int | None
    title: str
    document_type: str
    source_url: str
    filename: str
    mime_type: str
    status: str
    error_message: str
    created_at: datetime


class AlertRuleCreate(BaseModel):
    name: str
    channel: str = "email"
    destination: str
    min_priority: str = "A"
    hours_before_deadline: int = 48
    is_active: bool = True


class AlertRuleOut(ORMModel):
    id: int
    name: str
    channel: str
    destination: str
    min_priority: str
    hours_before_deadline: int
    is_active: bool


class AlertOut(ORMModel):
    id: int
    opportunity_id: int
    rule_id: int
    alert_type: str
    status: str
    message: str
    sent_at: datetime | None
