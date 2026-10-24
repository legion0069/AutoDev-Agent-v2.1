"""Typed API contracts for projects and dashboard data."""

from __future__ import annotations

from datetime import time
from typing import Any, Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=10_000)
    tech_stack: list[str] = Field(min_length=1, max_length=20)
    days: int = Field(ge=1, le=365)
    working_hours: int = Field(default=3, ge=1, le=24)
    daily_commit_target: int = Field(default=4, ge=1, le=8)
    repository: str = Field(default="", max_length=500)
    mode: Literal["autonomous", "approval"] = "autonomous"
    schedule_enabled: bool = True
    schedule_time: str = "09:00"
    timezone: str = "UTC"

    @field_validator("project_name", "description")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("This field must not be blank.")
        return value

    @field_validator("tech_stack")
    @classmethod
    def validate_tech_stack(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("At least one non-empty technology is required.")
        return normalized

    @field_validator("repository")
    @classmethod
    def validate_repository(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return value
        if value.startswith("git@github.com:"):
            repository_path = value.partition(":")[2].strip("/")
            if (
                len(repository_path.split("/")) != 2
                or any(char.isspace() for char in value)
            ):
                raise ValueError("Repository must include a GitHub owner and repository.")
            return value
        parsed = urlparse(value)
        repository_path = [part for part in parsed.path.split("/") if part]
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or len(repository_path) != 2
            or any(char.isspace() for char in value)
        ):
            raise ValueError("Repository must be a GitHub HTTPS or SSH URL.")
        return value

    @field_validator("schedule_time")
    @classmethod
    def validate_schedule_time(cls, value: str) -> str:
        try:
            return time.fromisoformat(value).isoformat(timespec="minutes")
        except ValueError as exc:
            raise ValueError("Schedule time must use 24-hour HH:MM format.") from exc

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Timezone must be a valid IANA timezone.") from exc
        return value


class ProjectScheduleRequest(BaseModel):
    enabled: bool
    schedule_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    timezone: str = Field(min_length=1, max_length=100)

    @field_validator("schedule_time")
    @classmethod
    def validate_schedule_time(cls, value: str) -> str:
        try:
            time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Schedule time must use 24-hour HH:MM format.") from exc
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Timezone must be a valid IANA timezone.") from exc
        return value


class ProjectActionRequest(BaseModel):
    project_id: str | None = None


class ProjectSummary(BaseModel):
    project_id: str
    project_name: str
    status: str
    current_day: int
    total_days: int
    completed_days: int
    progress_percent: float
    remaining_days: int
    commits_today: int
    current_milestone: str | None = None
    current_commit_number: int = 0
    files_changed: list[str] = Field(default_factory=list)
    review_status: str = "pending"
    push_status: str = "not_configured"
    current_task: str | None = None
    started_at: str | None = None
    elapsed_seconds: float = 0.0
    updated_at: str
    repository: str = ""
    error: str | None = None
    schedule_enabled: bool = False
    schedule_time: str = "09:00"
    timezone: str = "UTC"
    next_run_at: str | None = None
    last_run_at: str | None = None


class ApiMessage(BaseModel):
    message: str
    project: ProjectSummary | None = None


class LogEvent(BaseModel):
    event_id: int
    timestamp: str
    level: str = "info"
    event: str = "log"
    message: str
    day: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)
