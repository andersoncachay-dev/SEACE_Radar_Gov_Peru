from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    last_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    position: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    address: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    phone_peru: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    phone_chile: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    phone_argentina: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    access_profile: Mapped[str] = mapped_column(String(40), default="peru", nullable=False)
    # Comma-separated module_access.VALID_MODULES, independent of the
    # per-country access_profile above.
    module_access: Mapped[str] = mapped_column(String(80), default="radar", nullable=False)
    historico_digest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="viewer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    search_profiles: Mapped[list["SearchProfile"]] = relationship(back_populates="owner")
    opportunity_view_states: Mapped[list["OpportunityViewState"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class PasswordResetToken(TimestampMixin, Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SearchProfile(TimestampMixin, Base):
    __tablename__ = "search_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    keyword: Mapped[str] = mapped_column(String(255), default="satelital", nullable=False)
    source: Mapped[str] = mapped_column(String(80), default="seace_public_browser", nullable=False)
    year: Mapped[str] = mapped_column(String(10), default="2026", nullable=False)
    version: Mapped[str] = mapped_column(String(40), default="Seace 3", nullable=False)
    max_results: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    owner: Mapped[User | None] = relationship(back_populates="search_profiles")
    runs: Mapped[list["ScrapeRun"]] = relationship(back_populates="search_profile")


class OpportunityViewState(TimestampMixin, Base):
    __tablename__ = "opportunity_view_states"
    __table_args__ = (UniqueConstraint("owner_id", "scope", name="uq_opportunity_view_states_owner_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(80), nullable=False)
    state_json: Mapped[str] = mapped_column(Text, nullable=False)

    owner: Mapped[User] = relationship(back_populates="opportunity_view_states")


class RadarKeyword(TimestampMixin, Base):
    __tablename__ = "radar_keywords"
    __table_args__ = (UniqueConstraint("country", "normalized_keyword", name="uq_radar_keywords_country_normalized"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    keyword: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_keyword: Mapped[str] = mapped_column(String(80), nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class LegalDocument(TimestampMixin, Base):
    __tablename__ = "legal_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class AppSetting(TimestampMixin, Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ScrapeRun(TimestampMixin, Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    search_profile_id: Mapped[int | None] = mapped_column(ForeignKey("search_profiles.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rows_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_message: Mapped[str] = mapped_column(String(255), default="En cola", nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    diagnostics: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)

    search_profile: Mapped[SearchProfile | None] = relationship(back_populates="runs")


class Opportunity(TimestampMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_opportunities_source_external_id"),
        Index("ix_opportunities_archive_lookup", "is_archived", "archive_country", "archive_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    external_id: Mapped[str] = mapped_column(String(180), nullable=False)
    entity: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    nomenclature: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    object_type: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    record_type: Mapped[str] = mapped_column(String(40), default="proceso", nullable=False)
    expediente: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    contracting_unit: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    financial_service: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    region: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    buyer_ruc: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    ocid: Mapped[str] = mapped_column(String(220), default="", nullable=False)
    tender_id: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    ocds_source_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    release_id: Mapped[str] = mapped_column(String(220), default="", nullable=False)
    documents_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source_status: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    contract_duration: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    priority: Mapped[str] = mapped_column(String(10), default="C", nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reasons: Mapped[str] = mapped_column(Text, default="", nullable=False)
    detail_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    requirement_pdf_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    requirement_pdf_local: Mapped[str] = mapped_column(Text, default="", nullable=False)
    publication_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    opening_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consultation_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    quote_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    proposal_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    schedule_source: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    schedule_validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    archive_country: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    archive_key: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    archive_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)


class OpportunitySnapshot(TimestampMixin, Base):
    __tablename__ = "opportunity_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("scrape_runs.id"), nullable=True)
    previous_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    change_type: Mapped[str] = mapped_column(String(40), default="upsert", nullable=False)
    raw_payload: Mapped[str] = mapped_column(Text, default="", nullable=False)


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    source_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    local_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    filename: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="registered", nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)


class AlertRule(TimestampMixin, Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), default="email", nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    keywords: Mapped[str] = mapped_column(Text, default="", nullable=False)
    min_priority: Mapped[str] = mapped_column(String(10), default="A", nullable=False)
    hours_before_deadline: Mapped[int] = mapped_column(Integer, default=48, nullable=False)
    country: Mapped[str] = mapped_column(String(10), default="both", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("opportunity_id", "rule_id", "alert_type", name="uq_alert_once"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    rule_id: Mapped[int] = mapped_column(ForeignKey("alert_rules.id"), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TrackingArea(TimestampMixin, Base):
    __tablename__ = "tracking_areas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TrackingResponsible(TimestampMixin, Base):
    __tablename__ = "tracking_responsibles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    country_scope: Mapped[str] = mapped_column(String(10), default="ambos", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    areas: Mapped[list["TrackingArea"]] = relationship(secondary="tracking_area_responsibles", viewonly=True, order_by="TrackingArea.sort_order")


class TrackingAreaResponsible(TimestampMixin, Base):
    __tablename__ = "tracking_area_responsibles"
    __table_args__ = (UniqueConstraint("area_id", "responsible_id", name="uq_tracking_area_responsible"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("tracking_areas.id", ondelete="CASCADE"), index=True, nullable=False)
    responsible_id: Mapped[int] = mapped_column(ForeignKey("tracking_responsibles.id", ondelete="CASCADE"), index=True, nullable=False)


class TrackingPhase(TimestampMixin, Base):
    __tablename__ = "tracking_phases"
    __table_args__ = (Index("ix_tracking_phases_country_key", "country", "key", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country: Mapped[str] = mapped_column(String(10), default="peru", nullable=False)
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TrackingStageTemplate(TimestampMixin, Base):
    __tablename__ = "tracking_stage_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phase_id: Mapped[int] = mapped_column(ForeignKey("tracking_phases.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_outcome_step: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_informational: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    areas: Mapped[list["TrackingArea"]] = relationship(secondary="tracking_stage_template_areas", viewonly=True, order_by="TrackingArea.sort_order")


class TrackingStageTemplateArea(TimestampMixin, Base):
    __tablename__ = "tracking_stage_template_areas"
    __table_args__ = (UniqueConstraint("stage_template_id", "area_id", name="uq_tracking_stage_template_area"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage_template_id: Mapped[int] = mapped_column(ForeignKey("tracking_stage_templates.id", ondelete="CASCADE"), index=True, nullable=False)
    area_id: Mapped[int] = mapped_column(ForeignKey("tracking_areas.id", ondelete="CASCADE"), index=True, nullable=False)


class OpportunityTracking(TimestampMixin, Base):
    __tablename__ = "opportunity_trackings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    current_phase_id: Mapped[int | None] = mapped_column(ForeignKey("tracking_phases.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    quotation_outcome: Mapped[str] = mapped_column(String(10), default="pendiente", nullable=False)
    quotation_outcome_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    quotation_outcome_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    co_responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    stages: Mapped[list["OpportunityTrackingStage"]] = relationship(viewonly=True, order_by="OpportunityTrackingStage.sort_order")


class OpportunityTrackingStage(TimestampMixin, Base):
    __tablename__ = "opportunity_tracking_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tracking_id: Mapped[int] = mapped_column(ForeignKey("opportunity_trackings.id", ondelete="CASCADE"), index=True, nullable=False)
    phase_id: Mapped[int] = mapped_column(ForeignKey("tracking_phases.id"), nullable=False)
    stage_template_id: Mapped[int | None] = mapped_column(ForeignKey("tracking_stage_templates.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_outcome_step: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pendiente", nullable=False)
    outcome: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    is_informational: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alert_atender_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alert_urgente_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_time_alert_status: Mapped[str] = mapped_column(String(20), default="", nullable=False)

    areas: Mapped[list["TrackingArea"]] = relationship(secondary="opportunity_tracking_stage_areas", viewonly=True, order_by="TrackingArea.sort_order")
    assignees: Mapped[list["TrackingResponsible"]] = relationship(secondary="opportunity_tracking_stage_assignees", viewonly=True, order_by="TrackingResponsible.full_name")


class OpportunityTrackingStageArea(TimestampMixin, Base):
    __tablename__ = "opportunity_tracking_stage_areas"
    __table_args__ = (UniqueConstraint("stage_id", "area_id", name="uq_tracking_stage_area"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage_id: Mapped[int] = mapped_column(ForeignKey("opportunity_tracking_stages.id", ondelete="CASCADE"), index=True, nullable=False)
    area_id: Mapped[int] = mapped_column(ForeignKey("tracking_areas.id"), nullable=False)


class OpportunityTrackingStageAssignee(TimestampMixin, Base):
    __tablename__ = "opportunity_tracking_stage_assignees"
    __table_args__ = (UniqueConstraint("stage_id", "responsible_id", name="uq_tracking_stage_assignee"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage_id: Mapped[int] = mapped_column(ForeignKey("opportunity_tracking_stages.id", ondelete="CASCADE"), index=True, nullable=False)
    responsible_id: Mapped[int] = mapped_column(ForeignKey("tracking_responsibles.id"), nullable=False)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("tracking_areas.id"), nullable=True)
    assigned_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notification_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    notification_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notification_error: Mapped[str] = mapped_column(Text, default="", nullable=False)


class OpportunityReview(TimestampMixin, Base):
    __tablename__ = "opportunity_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="standby", nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class OpportunityReviewComment(TimestampMixin, Base):
    __tablename__ = "opportunity_review_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True, nullable=False)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)


# --- Histórico Perú (CONOSCE open data, refreshed monthly) -----------------
# Only rows matching an active HistKeyword are persisted; derived tables
# (hist_expirings, hist_recurrings) and hist_alerts are rebuilt on every import.


class HistImportRun(TimestampMixin, Base):
    __tablename__ = "hist_import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin: Mapped[str] = mapped_column(String(30), default="manual_upload", nullable=False)  # azure_job | pc_script | manual_upload | reprocess
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True, nullable=False)  # queued | running | completed | failed
    triggered_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data_cut_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    files_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    counts_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)


class HistKeyword(TimestampMixin, Base):
    __tablename__ = "hist_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="Internet (sin especificar)", nullable=False)
    # include: matches count as the rubro; review: kept but flagged "revisar";
    # exclude: a match removes the row (known false-positive phrases).
    kind: Mapped[str] = mapped_column(String(20), default="include", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)  # lower wins for category assignment
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class HistEntity(TimestampMixin, Base):
    __tablename__ = "hist_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ruc: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(20), default="", index=True, nullable=False)  # CODCONSUCODE / CODIGOENTIDAD
    name: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    government_level: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    department: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    province: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    district: Mapped[str] = mapped_column(String(80), default="", nullable=False)


class HistContracting(TimestampMixin, Base):
    """One purchase order <= 8 UIT, or one awarded item > 8 UIT."""

    __tablename__ = "hist_contractings"
    __table_args__ = (
        UniqueConstraint("dataset", "source_key", name="uq_hist_contracting_source"),
        Index("ix_hist_contracting_period", "year", "month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset: Mapped[str] = mapped_column(String(20), nullable=False)  # orden | adjudicacion
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)
    # The CONOSCE file the row came from ("2025" yearly, "2026-09" monthly).
    # A re-import replaces by this, never by year/month: an item in the 2025
    # awards file can have its buena pro in 2026.
    source_period: Mapped[str] = mapped_column(String(7), default="", index=True, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    event_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)  # emisión / buena pro
    process_group: Mapped[str] = mapped_column(String(60), default="", index=True, nullable=False)
    procedure: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    nomenclature: Mapped[str] = mapped_column(String(200), default="", index=True, nullable=False)
    convocatoria_code: Mapped[str] = mapped_column(String(30), default="", index=True, nullable=False)
    item_number: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    entity_code: Mapped[str] = mapped_column(String(20), default="", index=True, nullable=False)
    entity_ruc: Mapped[str] = mapped_column(String(20), default="", index=True, nullable=False)
    entity_name: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    department: Mapped[str] = mapped_column(String(80), default="", index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="", index=True, nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    reference_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    supplier_ruc: Mapped[str] = mapped_column(String(20), default="", index=True, nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    direct_cause: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    object_type: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    government_level: Mapped[str] = mapped_column(String(40), default="", index=True, nullable=False)
    relevance: Mapped[str] = mapped_column(String(30), default="ok", index=True, nullable=False)  # ok | revisar
    import_run_id: Mapped[int | None] = mapped_column(ForeignKey("hist_import_runs.id", ondelete="SET NULL"), nullable=True)


class HistContract(TimestampMixin, Base):
    __tablename__ = "hist_contracts"
    __table_args__ = (Index("ix_hist_contract_item", "entity_code", "convocatoria_code", "item_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    entity_code: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    convocatoria_code: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    item_number: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    contract_number: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    amount_item: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    amount_additional: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    amount_reduction: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    amount_extension: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    amount_complementary: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    contractor_ruc: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    signed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date_updated: Mapped[date | None] = mapped_column(Date, nullable=True)


class HistExpiring(TimestampMixin, Base):
    """Derived: awarded item > 8 UIT with its (real or estimated) end date."""

    __tablename__ = "hist_expirings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contracting_id: Mapped[int] = mapped_column(ForeignKey("hist_contractings.id", ondelete="CASCADE"), unique=True, nullable=False)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("hist_contracts.id", ondelete="SET NULL"), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    date_source: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    is_real_date: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    days_to_end: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bucket: Mapped[str] = mapped_column(String(30), default="", index=True, nullable=False)
    monthly_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    extras_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    possibly_renewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class HistRecurring(TimestampMixin, Base):
    """Derived: entity + supplier with <= 8 UIT orders in the last 12 months."""

    __tablename__ = "hist_recurrings"
    __table_args__ = (UniqueConstraint("entity_ruc", "supplier_ruc", name="uq_hist_recurring_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_ruc: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    department: Mapped[str] = mapped_column(String(80), default="", index=True, nullable=False)
    government_level: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    supplier_ruc: Mapped[str] = mapped_column(String(20), nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    orders_12m: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    months_12m: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    amount_12m_supplier: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    amount_12m_entity: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    suppliers_12m: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_order_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    last_order_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_order_id: Mapped[int | None] = mapped_column(ForeignKey("hist_contractings.id", ondelete="SET NULL"), nullable=True)
    pattern: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    next_purchase_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    days_to_next: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bucket: Mapped[str] = mapped_column(String(30), default="", index=True, nullable=False)


class HistPacItem(TimestampMixin, Base):
    __tablename__ = "hist_pac_items"
    __table_args__ = (UniqueConstraint("year", "entity_code", "reference_number", "item_number", name="uq_hist_pac_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    entity_code: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    entity_ruc: Mapped[str] = mapped_column(String(20), default="", index=True, nullable=False)
    entity_name: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    department: Mapped[str] = mapped_column(String(80), default="", index=True, nullable=False)
    government_level: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    version: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    reference_number: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    process_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    process_type: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    process_group: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    object_type: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    item_number: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    item_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    unit: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    item_department: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    province: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    district: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    planned_month: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    situation: Mapped[str] = mapped_column(String(60), default="", index=True, nullable=False)
    already_awarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    relevance: Mapped[str] = mapped_column(String(30), default="ok", nullable=False)


class HistAlert(TimestampMixin, Base):
    __tablename__ = "hist_alerts"
    __table_args__ = (UniqueConstraint("kind", "ref_key", name="uq_hist_alert_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # vencimiento | recurrente | pac
    ref_key: Mapped[str] = mapped_column(String(160), nullable=False)
    expiring_id: Mapped[int | None] = mapped_column(ForeignKey("hist_expirings.id", ondelete="SET NULL"), nullable=True)
    recurring_id: Mapped[int | None] = mapped_column(ForeignKey("hist_recurrings.id", ondelete="SET NULL"), nullable=True)
    pac_item_id: Mapped[int | None] = mapped_column(ForeignKey("hist_pac_items.id", ondelete="SET NULL"), nullable=True)
    priority: Mapped[str] = mapped_column(String(4), default="P4", index=True, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    entity_name: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    department: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="nueva", index=True, nullable=False)  # nueva | vista | en_gestion | descartada
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    dismissed_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    first_seen_import_id: Mapped[int | None] = mapped_column(ForeignKey("hist_import_runs.id", ondelete="SET NULL"), nullable=True)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
