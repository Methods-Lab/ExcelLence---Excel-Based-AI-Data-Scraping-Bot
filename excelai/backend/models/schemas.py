from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, HttpUrl


ColumnType = Literal["number", "currency", "date", "text", "percentage"]
SourceType = Literal["TEXT", "IMAGE", "URL"]


class ColumnSchema(BaseModel):
    name: str = Field(min_length=1)
    type: ColumnType = Field(default="text")


class UserBase(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserResponse(UserBase):
    pass


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TextExtractRequest(BaseModel):
    prompt: str = Field(min_length=1)


class UrlExtractRequest(BaseModel):
    url: HttpUrl
    clarification: str | None = None


class ExportRequest(BaseModel):
    columns: list[ColumnSchema]
    rows: list[list[Any]]
    filename: str | None = None


class ExtractResponse(BaseModel):
    columns: list[ColumnSchema]
    rows: list[list[Any]]
    confidence: float = Field(ge=0.0, le=1.0)
    source_type: SourceType
    warnings: list[str] = []
    table_title: str | None = None


class ImageExtractResponse(ExtractResponse):
    ocr_raw_text: str | None = None


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


class DetectedSubTable(BaseModel):
    id: str
    name: str
    estimated_rows: int = 0


class DetectedTopic(BaseModel):
    id: str
    name: str
    sub_tables: list[DetectedSubTable] = []


class TopicDetectRequest(BaseModel):
    content_type: Literal["image", "url"]
    content: str


class TopicDetectResponse(BaseModel):
    topics: list[DetectedTopic]
    scraped_content: str | None = None


class OcrResponse(BaseModel):
    text: str
    metadata: dict | None = None


class SelectedTopicsRequest(BaseModel):
    content: str
    selected_ids: list[str] = []
    calculated_columns: list[dict] | None = None
