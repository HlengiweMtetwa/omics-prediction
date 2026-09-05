"""Pydantic request/response schemas for the API.

These are presentation-layer DTOs, distinct from the ai_wasteguard ORM
models - the API never returns ORM instances directly (avoids leaking
password hashes, internal FKs used only for joins, etc).
"""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8)
    institution: str | None = None
    role: str = "researcher"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    full_name: str
    email: str
    role: str
    institution: str | None


class ProjectCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    disease_focus: str | None = None
    amr_focus: bool = False


class ProjectResponse(BaseModel):
    id: str
    title: str
    description: str | None
    disease_focus: str | None
    amr_focus: bool
    status: str
    created_at: datetime


class SiteCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    country: str | None = None
    region: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    site_type: str | None = None


class SiteResponse(BaseModel):
    id: str
    project_id: str
    name: str
    country: str | None
    region: str | None
    latitude: float | None
    longitude: float | None
    site_type: str | None
    created_at: datetime


class SamplingEventCreateRequest(BaseModel):
    collected_at: datetime
    sample_matrix: str | None = None
    collector: str | None = None
    notes: str | None = None


class SamplingEventResponse(BaseModel):
    id: str
    site_id: str
    collected_at: datetime
    sample_matrix: str | None
    collector: str | None
    notes: str | None
    created_at: datetime


class SampleCreateRequest(BaseModel):
    sample_type: str | None = None
    replicate: int = Field(default=1, ge=1)
    lab_identifier: str | None = None


class SampleResponse(BaseModel):
    id: str
    sampling_event_id: str
    sample_type: str | None
    replicate: int
    lab_identifier: str | None
    analysis_status: str
    created_at: datetime


class UploadResponse(BaseModel):
    id: str
    sample_id: str
    original_filename: str
    file_type: str
    omics_type: str | None
    size_bytes: int
    checksum_sha256: str
    validation_status: str
    created_at: datetime


class JobCreateRequest(BaseModel):
    pipeline_name: str = "synthetic_omics_demo"


class JobResponse(BaseModel):
    id: str
    project_id: str
    pipeline_name: str
    status: str
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ReportResponse(BaseModel):
    id: str
    project_id: str
    report_type: str
    content_hash: str
    created_at: datetime


class ModelRegisterRequest(BaseModel):
    job_id: str
    name: str | None = None


class ModelResponse(BaseModel):
    id: str
    project_id: str
    job_id: str
    name: str
    algorithm: str
    target_variable: str
    metrics: str | None
    intended_use: str
    prohibited_use: str
    approval_status: str
    registered_by: str
    approved_by: str | None
    created_at: datetime
    approved_at: datetime | None


class ApprovedModelSummary(BaseModel):
    id: str
    name: str
    algorithm: str


class ActivityEvent(BaseModel):
    action: str
    resource_type: str | None
    details: str | None
    created_at: datetime


class DashboardResponse(BaseModel):
    active_projects: int
    sites: int
    samples: int
    jobs_queued: int
    jobs_running: int
    jobs_completed: int
    jobs_failed: int
    approved_models: list[ApprovedModelSummary]
    recent_activity: list[ActivityEvent]


class AdminUserResponse(BaseModel):
    id: str
    full_name: str
    email: str
    institution: str | None
    role: str
    status: str
    created_at: datetime
    last_login_at: datetime | None


class RoleChangeRequest(BaseModel):
    role: str


class ErrorResponse(BaseModel):
    detail: str
