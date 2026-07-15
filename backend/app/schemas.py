from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, TypeAdapter, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=512)
    password: str = Field(min_length=8, max_length=128)


class MessageOut(BaseModel):
    message: str


class UserCreate(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=2, max_length=120)
    last_name: str = Field(min_length=2, max_length=160)
    position: str = Field(min_length=2, max_length=160)
    address: str = Field(min_length=4, max_length=255)
    phone_peru: str = Field(default="", max_length=32)
    phone_chile: str = Field(default="", max_length=32)
    access_profile: str = "peru"
    password: str = Field(min_length=8)
    role: str = "viewer"

    @model_validator(mode="after")
    def validate_profile_contact(self):
        if self.access_profile not in {"peru", "chile", "both"}:
            raise ValueError("El perfil debe ser Peru, Chile o ambos")
        if self.role not in {"viewer", "admin"}:
            raise ValueError("El rol debe ser usuario o administrador")
        if self.access_profile in {"peru", "both"} and not self.phone_peru.strip():
            raise ValueError("El celular de Peru es obligatorio para este perfil")
        if self.access_profile in {"chile", "both"} and not self.phone_chile.strip():
            raise ValueError("El celular de Chile es obligatorio para este perfil")
        return self


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    first_name: str | None = Field(default=None, min_length=2, max_length=120)
    last_name: str | None = Field(default=None, min_length=2, max_length=160)
    position: str | None = Field(default=None, min_length=2, max_length=160)
    address: str | None = Field(default=None, min_length=4, max_length=255)
    phone_peru: str | None = Field(default=None, max_length=32)
    phone_chile: str | None = Field(default=None, max_length=32)
    access_profile: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)

    @model_validator(mode="after")
    def validate_permissions(self):
        if self.access_profile is not None and self.access_profile not in {"peru", "chile", "both"}:
            raise ValueError("El perfil debe ser Peru, Chile o ambos")
        if self.role is not None and self.role not in {"viewer", "admin"}:
            raise ValueError("El rol debe ser usuario o administrador")
        return self


class UserOut(ORMModel):
    id: int
    email: str
    full_name: str
    first_name: str
    last_name: str
    position: str
    address: str
    phone_peru: str
    phone_chile: str
    access_profile: str
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


class RadarKeywordCreate(BaseModel):
    keyword: str = Field(min_length=2, max_length=80)


class RadarKeywordOut(BaseModel):
    id: int | None = None
    country: str
    keyword: str
    is_default: bool = False


class LegalDocumentUpdate(BaseModel):
    content: str = Field(min_length=100, max_length=30000)


class LegalDocumentOut(BaseModel):
    key: str
    title: str
    content: str
    updated_at: datetime


class AppSettingsUpdate(BaseModel):
    version_label: str = Field(min_length=3, max_length=80)


class AppSettingsOut(BaseModel):
    version_label: str
    updated_at: datetime | None = None


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
    commercial_mode: str = "active"


class ScrapeRunOut(ORMModel):
    id: int
    source: str
    status: str
    rows_found: int
    progress: int = 0
    progress_message: str = ""
    cancel_requested: bool = False
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
    buyer_ruc: str
    ocid: str
    tender_id: str
    ocds_source_id: str
    release_id: str
    documents_count: int
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
    name: str = Field(min_length=3, max_length=160)
    channel: str = "email"
    destination: str = Field(min_length=3, max_length=255)
    keywords: str = Field(default="", max_length=1000)
    min_priority: str = "A"
    is_active: bool = True

    @model_validator(mode="after")
    def validate_channel_destination(self):
        self.channel = self.channel.strip().lower()
        self.destination = self.destination.strip()
        self.keywords = self.keywords.strip()
        if self.channel not in {"email", "whatsapp", "in_app"}:
            raise ValueError("El canal debe ser email, WhatsApp o notificacion interna")
        if self.min_priority not in {"A", "B", "C"}:
            raise ValueError("La prioridad minima debe ser A, B o C")
        if self.channel == "email":
            TypeAdapter(EmailStr).validate_python(self.destination)
        if self.channel == "whatsapp" and not re.fullmatch(r"\+(?:51|56)\d{9}", self.destination):
            raise ValueError("WhatsApp requiere un celular valido de Peru (+51) o Chile (+56)")
        if self.channel == "in_app":
            self.destination = "GovRadar"
        return self


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=160)
    channel: str | None = None
    destination: str | None = Field(default=None, min_length=3, max_length=255)
    keywords: str | None = Field(default=None, max_length=1000)
    min_priority: str | None = None
    is_active: bool | None = None


class AlertRuleOut(ORMModel):
    id: int
    name: str
    channel: str
    destination: str
    keywords: str
    min_priority: str
    is_active: bool


class AlertOut(ORMModel):
    id: int
    opportunity_id: int
    rule_id: int
    alert_type: str
    status: str
    message: str
    attempt_count: int
    next_attempt_at: datetime | None
    last_attempt_at: datetime | None
    last_error: str
    provider_message_id: str
    sent_at: datetime | None
