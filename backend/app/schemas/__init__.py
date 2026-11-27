from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
MonitorName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Password = Annotated[str, Field(min_length=8, max_length=256)]
Event = Literal["down", "recovered", "ssl"]
Window = Literal["24h", "7d", "30d"]
MonitorStatus = Literal["pending", "up", "down", "degraded", "paused"]
Interval = Literal[60, 300, 600, 900, 1800, 3600]


class View(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Register(BaseModel):
    name: Name
    email: EmailStr
    password: Password


class Login(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(max_length=256)]


class ProfileUpdate(BaseModel):
    name: Name


class PasswordUpdate(BaseModel):
    current_password: Annotated[str, Field(max_length=256)]
    new_password: Password


class UserView(View):
    id: UUID
    name: str
    email: str
    role: str
    is_active: bool
    is_demo: bool
    created_at: datetime


class Access(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserView


class MonitorInput(BaseModel):
    name: MonitorName
    url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)]
    type: Literal["http", "keyword"] = "http"
    interval_seconds: Interval = 300
    timeout_seconds: Annotated[int, Field(ge=5, le=30)] = 10
    expected_status_code: Annotated[int, Field(ge=100, le=599)] = 200
    keyword: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    response_threshold_ms: Annotated[int, Field(ge=100, le=30000)] = 2000
    notifications_enabled: bool = True

    @model_validator(mode="after")
    def require_keyword(self):
        if self.type == "keyword" and (self.keyword is None or not self.keyword.strip()):
            raise ValueError("Укажите ключевое слово")
        if self.type == "http":
            self.keyword = None
        return self


class MonitorPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: MonitorName | None = None
    url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)] | None = None
    type: Literal["http", "keyword"] | None = None
    interval_seconds: Interval | None = None
    timeout_seconds: Annotated[int, Field(ge=5, le=30)] | None = None
    expected_status_code: Annotated[int, Field(ge=100, le=599)] | None = None
    keyword: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    response_threshold_ms: Annotated[int, Field(ge=100, le=30000)] | None = None
    notifications_enabled: bool | None = None

    @model_validator(mode="after")
    def reject_null_fields(self):
        if any(getattr(self, field) is None for field in self.model_fields_set - {"keyword"}):
            raise ValueError("Только ключевое слово может быть пустым")
        return self


class MonitorView(MonitorInput, View):
    id: UUID
    status: MonitorStatus
    is_active: bool
    is_synthetic: bool
    consecutive_failures: int
    last_checked_at: datetime | None
    next_check_at: datetime
    last_response_time_ms: int | None
    ssl_expires_at: datetime | None
    ssl_valid: bool | None
    ssl_hostname_valid: bool | None
    created_at: datetime


class MonitorRow(MonitorView):
    uptime: float | None


class CheckView(View):
    id: UUID
    status: str
    http_status_code: int | None
    response_time_ms: int | None
    error_message: str | None
    checked_at: datetime


class IncidentView(View):
    id: UUID
    monitor_id: UUID
    monitor_name: str
    status: Literal["ongoing", "resolved"]
    reason: str
    http_status_code: int | None
    started_at: datetime
    resolved_at: datetime | None
    duration_seconds: int | None


class StatusPageInput(BaseModel):
    title: MonitorName
    slug: Annotated[str, Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    description: Annotated[str, Field(max_length=500)] = ""
    is_public: bool = False
    monitor_ids: Annotated[list[UUID], Field(max_length=200)] = Field(default_factory=list)


class StatusPagePatch(BaseModel):
    title: MonitorName | None = None
    slug: Annotated[str, Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")] | None = None
    description: Annotated[str, Field(max_length=500)] | None = None
    is_public: bool | None = None
    monitor_ids: Annotated[list[UUID], Field(max_length=200)] | None = None

    @model_validator(mode="after")
    def reject_null_fields(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Поля статус-страницы не могут иметь значение null")
        return self


class StatusPageView(StatusPageInput):
    id: UUID
    updated_at: datetime


class ChannelUpdate(BaseModel):
    is_active: bool
    events: set[Event]


class AdminUpdate(BaseModel):
    is_active: bool
