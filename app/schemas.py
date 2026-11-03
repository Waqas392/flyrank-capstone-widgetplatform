"""Pydantic models for the owner (authenticated) API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

NAME_RE = r"^[a-z][a-z0-9_]{0,31}$"
WidgetType = Literal["signup_form", "contact_form", "cta_popover"]


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=NAME_RE)
    label: str = Field(min_length=1, max_length=100)
    type: Literal["text", "email", "textarea", "tel", "checkbox"] = "text"
    required: bool = True
    max_length: int = Field(255, ge=1, le=5000)
    placeholder: str | None = Field(None, max_length=100)


class Display(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["inline", "popover"] = "inline"
    delay_seconds: int = Field(0, ge=0, le=300)


def _check_fields(fields: list[FieldSpec] | None, honeypot: str | None) -> None:
    if fields is None:
        return
    if not 1 <= len(fields) <= 20:
        raise ValueError("fields must contain 1-20 entries")
    names = [f.name for f in fields]
    if len(set(names)) != len(names):
        raise ValueError("field names must be unique")
    if honeypot and honeypot in names:
        raise ValueError("a field may not use the honeypot field name")


class WidgetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: WidgetType
    title: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=1000)
    button_text: str = Field("Submit", min_length=1, max_length=60)
    fields: list[FieldSpec] | None = None
    display: Display | None = None
    honeypot_field: str | None = Field(None, pattern=NAME_RE)
    is_active: bool = True

    @model_validator(mode="after")
    def _v(self):
        _check_fields(self.fields, self.honeypot_field)
        return self


class WidgetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    button_text: str | None = Field(None, min_length=1, max_length=60)
    fields: list[FieldSpec] | None = None
    display: Display | None = None
    honeypot_field: str | None = Field(None, pattern=NAME_RE)
    is_active: bool | None = None

    @model_validator(mode="after")
    def _v(self):
        _check_fields(self.fields, self.honeypot_field)
        return self
