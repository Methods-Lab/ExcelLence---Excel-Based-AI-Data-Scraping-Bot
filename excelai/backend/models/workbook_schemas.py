"""Structured 'workbook spec' contract — the heart of the Excel-skill engine.

Groq returns a *design* (charts/KPIs/narrative). Python expands that design into a
WorkbookSpec (injecting the real rows + computed numbers), and workbook_builder.py
renders the WorkbookSpec into a polished .xlsx with openpyxl.

Nothing here executes code — it is pure declarative data, which is what makes the
approach safe, deterministic, and testable.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CellType = Literal["text", "number", "currency", "date", "percentage"]
ChartType = Literal["bar", "line", "pie", "area"]
Aggregation = Literal["sum", "avg", "min", "max", "count", "first", "last", "growth"]


class ColumnSpec(BaseModel):
    name: str = Field(min_length=1)
    type: CellType = "text"
    width: int | None = None


class ChartSpec(BaseModel):
    """A chart that reads from a data sheet's header row + data rows."""
    type: ChartType = "bar"
    title: str = "Chart"
    category_column: str            # column name used for the X axis / pie labels
    value_columns: list[str] = []   # column name(s) used as the plotted series
    anchor: str | None = None       # e.g. "H2"; auto-placed when None


class ConditionalRule(BaseModel):
    column: str
    rule: Literal["color_scale", "data_bar", "greater_than", "less_than"] = "color_scale"
    value: float | None = None
    color: str | None = None        # hex WITHOUT the leading '#'


class KpiCard(BaseModel):
    label: str
    value: str                      # already formatted by Python (e.g. "$1.2M")
    delta: str | None = None        # e.g. "+12.4%"
    description: str | None = None


class SheetSpec(BaseModel):
    name: str = Field(min_length=1)
    columns: list[ColumnSpec] = []
    rows: list[list[Any]] = []
    formulas: dict[str, str] = {}              # {"D2": "=B2*C2"}
    charts: list[ChartSpec] = []
    conditional_formats: list[ConditionalRule] = []
    freeze_header: bool = True
    autofilter: bool = True


class DashboardSpec(BaseModel):
    name: str = "Dashboard"
    headline: str | None = None
    kpis: list[KpiCard] = []
    narrative: list[str] = []                  # bullet-point insights
    charts: list[ChartSpec] = []               # charts referencing source_sheet
    source_sheet: str | None = None            # which data sheet charts read from


class WorkbookSpec(BaseModel):
    title: str = "ExcelLence Workbook"
    theme: Literal["corporate", "dark", "light"] = "corporate"
    dashboard: DashboardSpec | None = None
    sheets: list[SheetSpec] = []


# ---- API request models -----------------------------------------------------

class WorkbookBuildRequest(BaseModel):
    columns: list[ColumnSpec]
    rows: list[list[Any]]
    intent: str | None = None                  # natural-language goal for the report
    source_type: str | None = None
    filename: str | None = None
    theme: Literal["corporate", "dark", "light"] = "corporate"
