"""Core ORM models: User, Project, Site, SamplingEvent, Sample.

This is a deliberately trimmed subset of the full data model described in
the project's design document (Part VI) - enough to support real
project/site/sample registries and authentication. Fields are added when a
concrete feature needs them, not speculatively.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_wasteguard.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    ADMINISTRATOR = "administrator"
    RESEARCHER = "researcher"
    LABORATORY_SCIENTIST = "laboratory_scientist"
    PUBLIC_HEALTH_OFFICIAL = "public_health_official"
    STUDENT = "student"
    VIEWER = "viewer"


class AccountStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.RESEARCHER)
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[AccountStatus] = mapped_column(Enum(AccountStatus), default=AccountStatus.ACTIVE)
    failed_login_count: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    projects: Mapped[list["Project"]] = relationship(back_populates="owner")


class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    disease_focus: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amr_focus: Mapped[bool] = mapped_column(default=False)
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), default=ProjectStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    owner: Mapped["User"] = relationship(back_populates="projects")
    sites: Mapped[list["Site"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    site_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped["Project"] = relationship(back_populates="sites")
    sampling_events: Mapped[list["SamplingEvent"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )


class SamplingEvent(Base):
    __tablename__ = "sampling_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sample_matrix: Mapped[str | None] = mapped_column(String(100), nullable=True)
    collector: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    site: Mapped["Site"] = relationship(back_populates="sampling_events")
    samples: Mapped[list["Sample"]] = relationship(
        back_populates="sampling_event", cascade="all, delete-orphan"
    )


class SampleAnalysisStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"


class Sample(Base):
    __tablename__ = "samples"
    __table_args__ = (UniqueConstraint("sampling_event_id", "replicate", name="uq_sample_event_replicate"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sampling_event_id: Mapped[str] = mapped_column(ForeignKey("sampling_events.id"))
    sample_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    replicate: Mapped[int] = mapped_column(default=1)
    lab_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    analysis_status: Mapped[SampleAnalysisStatus] = mapped_column(
        Enum(SampleAnalysisStatus), default=SampleAnalysisStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    sampling_event: Mapped["SamplingEvent"] = relationship(back_populates="samples")
    uploaded_files: Mapped[list["UploadedFile"]] = relationship(
        back_populates="sample", cascade="all, delete-orphan"
    )


class UploadValidationStatus(str, enum.Enum):
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sample_id: Mapped[str] = mapped_column(ForeignKey("samples.id"))
    uploader_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    file_type: Mapped[str] = mapped_column(String(20))
    omics_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    size_bytes: Mapped[int] = mapped_column()
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    validation_status: Mapped[UploadValidationStatus] = mapped_column(
        Enum(UploadValidationStatus), default=UploadValidationStatus.PENDING
    )
    validation_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    sample: Mapped["Sample"] = relationship(back_populates="uploaded_files")
    uploader: Mapped["User"] = relationship()
