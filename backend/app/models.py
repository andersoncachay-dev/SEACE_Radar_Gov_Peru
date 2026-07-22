from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
    access_profile: Mapped[str] = mapped_column(String(20), default="peru", nullable=False)
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
    alert_atender_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alert_urgente_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
