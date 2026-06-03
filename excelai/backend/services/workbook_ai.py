"""Groq-powered report *designer* (cost-friendly).

Key cost trick: the LLM never sees or re-types the data rows. It only receives the
column schema, a tiny sample, and pre-computed statistics, then returns a DESIGN:
which charts, which KPIs (by column + aggregation), and a short narrative. Python
then injects the real rows and computes every number deterministically.

This keeps token usage tiny and eliminates LLM arithmetic errors / row truncation.
"""
from __future__ import annotations

import json
import os
from typing import Any

from backend.models.workbook_schemas import (
    ChartSpec,
    ColumnSpec,
    ConditionalRule,
    DashboardSpec,
    KpiCard,
    SheetSpec,
    WorkbookSpec,
)
from backend.services.workbook_builder import to_number
from backend.utils.helpers import safe_json_loads

MODEL_NAME = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

DESIGN_SYSTEM_PROMPT = """
You are ExcelLence's report designer. Given a table's COLUMN SCHEMA, a few SAMPLE ROWS,
and pre-computed STATS, you design a polished Excel report. You DO NOT output the data rows.

Return ONLY valid JSON in this exact shape:
{
  "title": "Short report title",
  "narrative": ["insight sentence 1", "insight sentence 2"],
  "kpis": [
    {"label": "Total Revenue", "column": "Revenue", "aggregation": "sum", "description": "..."}
  ],
  "charts": [
    {"type": "bar", "title": "Revenue by Region", "category_column": "Region", "value_columns": ["Revenue"]}
  ],
  "conditional_formats": [
    {"column": "Revenue", "rule": "color_scale"}
  ]
}

RULES:
- aggregation must be one of: sum, avg, min, max, count, first, last, growth.
- KPI "column" MUST be an exact column name that is numeric/currency/percentage. 3-6 KPIs.
- Chart "category_column" is a label/date/text column; "value_columns" are numeric columns.
- Choose chart type by intent: bar = compare categories, line = trend over time/date,
  pie = composition (use ONE value column, <=6 categories), area = cumulative trend. 2-4 charts.
- narrative: 3-6 concise, specific, data-driven sentences (reference the STATS, no fabrication).
- Use ONLY column names that exist. Return JSON only — no markdown, no commentary.
"""


def _normalize_columns(columns: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for i, col in enumerate(columns or []):
        if isinstance(col, dict):
            normalized.append({"name": str(col.get("name") or f"Column {i + 1}"), "type": col.get("type") or "text"})
        elif hasattr(col, "name"):
            normalized.append({"name": col.name, "type": getattr(col, "type", "text") or "text"})
        else:
            normalized.append({"name": str(col), "type": "text"})
    return normalized


def compute_stats(columns: list[dict[str, Any]], rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for i, col in enumerate(columns):
        nums = [n for r in rows if i < len(r) and (n := to_number(r[i])) is not None]
        is_numeric_type = col["type"] in ("number", "currency", "percentage")
        mostly_numeric = rows and len(nums) >= max(1, int(len(rows) * 0.6))
        if nums and (is_numeric_type or mostly_numeric):
            first, last = nums[0], nums[-1]
            stats[col["name"]] = {
                "type": col["type"],
                "sum": sum(nums),
                "avg": sum(nums) / len(nums),
                "min": min(nums),
                "max": max(nums),
                "count": len(nums),
                "first": first,
                "last": last,
                "growth": ((last - first) / first) if first else None,
            }
    return stats


def _agg_value(stats: dict, column: str | None, aggregation: str) -> float | None:
    if not column or column not in stats:
        return None
    return stats[column].get(aggregation)


def _human_money(value: float) -> str:
    sign = "-" if value < 0 else ""
    v = abs(value)
    if v >= 1_000_000_000:
        return f"{sign}${v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"{sign}${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{sign}${v / 1_000:.1f}K"
    return f"{sign}${v:,.0f}"


def _format_value(value: float | None, column_type: str, aggregation: str) -> str:
    if value is None:
        return "—"
    if aggregation == "count":
        return f"{int(value):,}"
    if aggregation == "growth":
        return f"{value * 100:+.1f}%"
    if column_type == "currency":
        return _human_money(value)
    if column_type == "percentage":
        return f"{value * 100:.1f}%"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def _default_design(columns: list[dict[str, Any]], stats: dict) -> dict[str, Any]:
    """Guaranteed polished design when Groq is unavailable or fails."""
    numeric = [c["name"] for c in columns if c["name"] in stats]
    label_cols = [c["name"] for c in columns if c["name"] not in stats]
    date_cols = [c["name"] for c in columns if c["type"] == "date"]
    category = (date_cols or label_cols or [c["name"] for c in columns])[0]

    charts: list[dict[str, Any]] = []
    if numeric:
        chart_type = "line" if date_cols else "bar"
        charts.append({"type": chart_type, "title": f"{numeric[0]} by {category}",
                       "category_column": category, "value_columns": numeric[:2]})
        if len(numeric) >= 1 and label_cols:
            charts.append({"type": "pie", "title": f"{numeric[0]} composition",
                           "category_column": label_cols[0], "value_columns": [numeric[0]]})

    kpis = [{"label": f"Total {name}", "column": name, "aggregation": "sum"} for name in numeric[:3]]
    narrative = [f"{name}: total {stats[name]['sum']:,.0f}, average {stats[name]['avg']:,.2f}." for name in numeric[:3]]
    return {"title": "Data Report", "narrative": narrative, "kpis": kpis,
            "charts": charts, "conditional_formats": [{"column": n, "rule": "color_scale"} for n in numeric[:1]]}


def _generate_design(columns: list[dict[str, Any]], sample_rows: list[list[Any]], stats: dict, intent: str | None) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return _default_design(columns, stats)
    try:
        from groq import Groq

        client = Groq(api_key=api_key)
        user_payload = {
            "intent": intent or "Build a clear, professional summary report.",
            "columns": columns,
            "sample_rows": sample_rows[:8],
            "stats": {k: {kk: vv for kk, vv in v.items()} for k, v in stats.items()},
        }
        response = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0.2,
            max_tokens=2000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": DESIGN_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, default=str)},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        design = safe_json_loads(raw)
        if not isinstance(design, dict) or not design.get("kpis") and not design.get("charts"):
            return _default_design(columns, stats)
        return design
    except Exception:
        return _default_design(columns, stats)


def _valid_chart(chart: dict, column_names: set[str]) -> bool:
    return (
        chart.get("category_column") in column_names
        and bool(chart.get("value_columns"))
        and any(v in column_names for v in chart.get("value_columns", []))
    )


def build_polished_spec(
    columns: list[Any],
    rows: list[list[Any]],
    intent: str | None = None,
    theme: str = "corporate",
    title: str | None = None,
) -> WorkbookSpec:
    norm_cols = _normalize_columns(columns)
    column_names = {c["name"] for c in norm_cols}
    stats = compute_stats(norm_cols, rows)
    design = _generate_design(norm_cols, rows, stats, intent)

    charts = [ChartSpec(**c) for c in design.get("charts", []) if _valid_chart(c, column_names)]
    cond_formats = [
        ConditionalRule(**cf) for cf in design.get("conditional_formats", [])
        if cf.get("column") in column_names
    ]

    data_sheet = SheetSpec(
        name="Data",
        columns=[ColumnSpec(**c) for c in norm_cols],
        rows=rows,
        charts=[],  # charts live on the dashboard for a cleaner data sheet
        conditional_formats=cond_formats,
    )

    kpi_cards: list[KpiCard] = []
    for kpi in design.get("kpis", []):
        column = kpi.get("column")
        aggregation = kpi.get("aggregation", "sum")
        column_type = stats.get(column, {}).get("type", "number") if column else "number"
        value = _agg_value(stats, column, aggregation)
        growth = _agg_value(stats, column, "growth")
        kpi_cards.append(KpiCard(
            label=kpi.get("label", "KPI"),
            value=_format_value(value, column_type, aggregation),
            delta=_format_value(growth, column_type, "growth") if growth is not None else None,
            description=kpi.get("description"),
        ))

    dashboard = DashboardSpec(
        name="Dashboard",
        headline=design.get("title") or title or "Executive Dashboard",
        kpis=kpi_cards,
        narrative=[str(n) for n in design.get("narrative", []) if str(n).strip()],
        charts=charts,
        source_sheet="Data",
    )

    return WorkbookSpec(
        title=title or design.get("title") or "ExcelLence Workbook",
        theme=theme if theme in ("corporate", "dark", "light") else "corporate",
        dashboard=dashboard,
        sheets=[data_sheet],
    )
