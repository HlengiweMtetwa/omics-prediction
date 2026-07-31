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


class ErrorResponse(BaseModel):
    detail: str
