"""SQLAlchemy models for all 9 tables (8 study tables + users for login).

database/schema.sql is the source of truth (constraints, triggers, indexes).
These models mirror it column for column; they never create tables.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Study(Base):
    __tablename__ = "studies"

    study_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_code: Mapped[str] = mapped_column(String(30), unique=True)
    title: Mapped[str] = mapped_column(String(150))
    study_type: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    participants: Mapped[list["Participant"]] = relationship(back_populates="study")


class StaffMember(Base):
    __tablename__ = "staff_members"

    staff_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    staff_code: Mapped[str] = mapped_column(String(20), unique=True)
    display_label: Mapped[str] = mapped_column(String(60))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")

    user: Mapped["User | None"] = relationship(back_populates="staff", uselist=False)


class User(Base):
    """Login account: one per staff member. The role lives on staff_members."""
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    staff_code: Mapped[str] = mapped_column(ForeignKey("staff_members.staff_code"), unique=True)

    staff: Mapped[StaffMember] = relationship(back_populates="user")


class Participant(Base):
    __tablename__ = "participants"

    participant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.study_id"))
    participant_code: Mapped[str] = mapped_column(String(10))
    consent_status: Mapped[str] = mapped_column(String(10))
    coordinator_code: Mapped[str] = mapped_column(ForeignKey("staff_members.staff_code"))
    reviewer_code: Mapped[str] = mapped_column(ForeignKey("staff_members.staff_code"))
    consent_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    study: Mapped[Study] = relationship(back_populates="participants")
    visits: Mapped[list["Visit"]] = relationship(back_populates="participant")


class Visit(Base):
    __tablename__ = "visits"

    visit_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.participant_id"))
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    visit_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), server_default="SCHEDULED")
    coordinator_code: Mapped[str] = mapped_column(ForeignKey("staff_members.staff_code"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    participant: Mapped[Participant] = relationship(back_populates="visits")
    notes: Mapped[list["VisitNote"]] = relationship(back_populates="visit")
    summaries: Mapped[list["AiSummary"]] = relationship(back_populates="visit")


class VisitNote(Base):
    __tablename__ = "visit_notes"

    note_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.visit_id"))
    observation_text: Mapped[str] = mapped_column(Text)
    follow_up_actions: Mapped[list] = mapped_column(JSONB, server_default="[]")
    author_code: Mapped[str] = mapped_column(ForeignKey("staff_members.staff_code"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    visit: Mapped[Visit] = relationship(back_populates="notes")


class AiSummary(Base):
    __tablename__ = "ai_summaries"

    summary_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.visit_id"))
    generated_draft: Mapped[dict | None] = mapped_column(JSONB)
    model_id: Mapped[str] = mapped_column(String(80))
    deployment_name: Mapped[str] = mapped_column(String(80))
    generation_status: Mapped[str] = mapped_column(String(10))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    visit: Mapped[Visit] = relationship(back_populates="summaries")
    review: Mapped["SummaryReview | None"] = relationship(back_populates="summary", uselist=False)


class SummaryReview(Base):
    __tablename__ = "summary_reviews"

    review_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    summary_id: Mapped[int] = mapped_column(ForeignKey("ai_summaries.summary_id"), unique=True)
    final_text: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(String(10))
    reviewer_code: Mapped[str] = mapped_column(ForeignKey("staff_members.staff_code"))
    reviewer_comment: Mapped[str | None] = mapped_column(String(1000))
    follow_up_flag: Mapped[bool] = mapped_column(Boolean, server_default="false")
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    summary: Mapped[AiSummary] = relationship(back_populates="review")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(40))
    actor_code: Mapped[str] = mapped_column(ForeignKey("staff_members.staff_code"))
    old_value: Mapped[str | None] = mapped_column(String(60))
    new_value: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())